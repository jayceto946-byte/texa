"""Small model interface and local-only MLX implementation; no scorer/gold imports.

Optional subprocess bridge reuses an EXISTING Python runtime, not a model server.
"""
import importlib.metadata
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol


class ModelAdapter(Protocol):
    def load(self, config: dict) -> dict: ...
    def generate(self, messages: list, generation_config: dict) -> dict: ...
    def close(self) -> dict: ...


def snapshot_identity(path):
    path = Path(path).expanduser().resolve(strict=True)
    config = json.loads((path / 'config.json').read_text())
    text = config.get('text_config', config)
    # Architecture/config values, never directory-name inference.
    qwen = config.get('model_type') == 'qwen3_5' and text.get('hidden_size') == 1024 and text.get('num_hidden_layers') == 24
    qwen3 = (config.get('model_type') == 'qwen3' and text.get('hidden_size') == 1024
             and text.get('num_hidden_layers') == 28 and text.get('vocab_size') == 151936
             and text.get('intermediate_size') == 3072
             and config.get('architectures') == ['Qwen3ForCausalLM'])
    gemma = (config.get('model_type') == 'gemma3_text' and text.get('hidden_size') == 1152
             and text.get('num_hidden_layers') == 26 and text.get('vocab_size') == 262144
             and config.get('architectures') == ['Gemma3ForCausalLM'])
    if not (qwen or qwen3 or gemma):
        raise ValueError('snapshot is not a supported Qwen3.5-0.8B, Qwen3-0.6B or Gemma3-1B architecture')
    quant = config.get('quantization')
    if not isinstance(quant, dict) or quant.get('bits') != 8:
        raise ValueError('snapshot config does not declare actual 8bit quantization')
    if config.get('quantization_config', quant) != quant:
        raise ValueError('conflicting quantization configs')
    if not list(path.glob('model*.safetensors')):
        raise ValueError('local model weights missing; downloads are disabled')
    return {'local_path': str(path), 'model_type': config['model_type'], 'architectures': config.get('architectures'),
            'text_config_identity': {key: text.get(key) for key in ('hidden_size', 'num_hidden_layers', 'vocab_size', 'intermediate_size')},
            'quantization': quant, 'declared_weight_dtype': text.get('dtype', text.get('torch_dtype')),
            'revision': None, 'revision_reason': 'local LM Studio snapshot has no verified revision',
            'identity_basis': 'config architecture/size plus loaded quantized modules; no upstream revision attestation'}


class MLXAdapter:
    def load(self, config):
        self.config = config
        identity = snapshot_identity(config['model_path'])
        import mlx.core as mx
        from mlx_lm import load, stream_generate
        from mlx_lm.sample_utils import make_sampler
        from mlx.utils import tree_flatten
        for library, expected in config.get('required_versions', {}).items():
            if importlib.metadata.version(library) != expected:
                raise RuntimeError('locked library version differs: ' + library)
        self.mx, self.stream_generate, self.make_sampler = mx, stream_generate, make_sampler
        if not hasattr(mx, 'synchronize'):
            raise RuntimeError('installed MLX has no reliable synchronization API')
        if hasattr(mx, 'reset_peak_memory'):
            mx.reset_peak_memory()
        started = time.perf_counter()
        # Path must exist, so mlx-lm cannot fall through to hub download.
        adapter_path = config.get('adapter_path')
        if adapter_path is not None:
            adapter_path = str(Path(adapter_path).expanduser().resolve(strict=True))
        adapter_hashes = ({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(Path(adapter_path).iterdir()) if p.is_file()}
                          if adapter_path is not None else {})
        self.model, self.tokenizer = load(Path(identity['local_path']), adapter_path=adapter_path, lazy=False)
        # Gemma IT terminates at end_of_turn (Gemma 3 technical report).
        # Older MLX conversions may omit generation_config.json and expose only
        # tokenizer <eos>. Register the native turn terminator before generation;
        # never trim or repair the generated raw text afterward.
        if identity['model_type'] == 'gemma3_text':
            self.tokenizer.add_eos_token('<end_of_turn>')
        mx.eval(self.model.parameters())
        mx.synchronize()
        load_ms = (time.perf_counter() - started) * 1000
        modules = [(name, module) for name, module in self.model.named_modules() if hasattr(module, 'bits')]
        if not modules or any(module.bits != 8 for _, module in modules):
            raise ValueError('loaded modules do not uniformly verify 8bit quantization')
        if any(module.group_size != identity['quantization']['group_size'] for _, module in modules):
            raise ValueError('loaded group size differs from snapshot')
        dtypes = sorted({str(value.dtype) for _, value in tree_flatten(self.model.parameters())})
        seed = config.get('seed', 0)
        if seed is not None:
            mx.random.seed(seed)
        template = config.get('template', {'enable_thinking': False})
        if set(template) - {'enable_thinking'}:
            raise ValueError('only enable_thinking template option is supported')
        template_text = self.tokenizer.chat_template or ''
        if template and 'enable_thinking' not in template_text:
            raise ValueError('tokenizer template does not support requested thinking setting')
        self.template = template
        physical = None
        if sys.platform == 'darwin':
            physical = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True).strip())
        hardware = subprocess.check_output(['sysctl', '-n', 'hw.model'], text=True).strip() if sys.platform == 'darwin' else platform.machine()
        return {**identity, 'adapter_path': adapter_path, 'adapter_files_sha256': adapter_hashes, 'model_id': config['model_id'], 'verified_quantized_modules': len(modules),
                'weight_dtypes': dtypes, 'load_ms': load_ms, 'seed': seed, 'seed_supported': True,
                'template_settings': {**template, 'add_generation_prompt': True, 'tokenize': False},
                'libraries': {key: importlib.metadata.version(key) for key in ('mlx', 'mlx-lm', 'transformers')},
                'device': {'platform': platform.platform(), 'machine': platform.machine(), 'hardware_model': hardware,
                           'physical_memory_bytes': physical, 'mlx': mx.device_info()},
                'python': sys.version, 'generated_token_counting': 'mlx-lm stream generation_tokens, includes EOS on stop',
                'synchronization_api': 'mlx.core.synchronize after stream completion',
                'load_surface': ('mlx-lm text-only Qwen3.5; model sanitizer excludes visual weights'
                                 if identity['model_type'] == 'qwen3_5' else 'mlx-lm native ' + identity['model_type'] + ' text'),
                'thinking_setting_supported': 'enable_thinking' in template_text,
                'thinking_setting': template.get('enable_thinking', 'not_applicable'),
                'eos_token_ids': sorted(self.tokenizer.eos_token_ids),
                'chat_template': template_text,
                'chat_template_sha256': hashlib.sha256(template_text.encode()).hexdigest(),
                'tokenizer_class': type(self.tokenizer).__name__,
                'model_class': type(self.model).__module__ + '.' + type(self.model).__name__}

    def generate(self, messages, generation_config):
        started = time.perf_counter()
        raw, last, rendered = '', None, None
        try:
            rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **self.template)
            tokens = self.tokenizer.encode(rendered, add_special_tokens=False)
            # Fresh implicit prompt cache for every generation; no cross-case reuse.
            for response in self.stream_generate(self.model, self.tokenizer, tokens,
                    max_tokens=generation_config['max_new_tokens'], sampler=self.make_sampler(temp=0.0)):
                raw += response.text
                last = response
            self.mx.synchronize()
            elapsed = (time.perf_counter() - started) * 1000
            return {'raw_output': raw, 'status': 'ok', 'error': None,
                    'finish_reason': last.finish_reason if last else None,
                    'generated_tokens': last.generation_tokens if last else 0,
                    'token_count_reason': None, 'request_ms': elapsed,
                    'rendered_prompt': rendered, 'template_settings': self.template,
                    'template_prefix_is_part_of_rendered_prompt': True}
        except Exception as error:
            return {'raw_output': raw if last is not None else None, 'status': 'error',
                    'error': type(error).__name__ + ': ' + str(error), 'finish_reason': None,
                    'generated_tokens': last.generation_tokens if last else None,
                    'token_count_reason': 'partial stream' if last else 'generation failed before tokens',
                    'request_ms': (time.perf_counter() - started) * 1000,
                    'rendered_prompt': rendered, 'template_settings': self.template}

    def close(self):
        peak = self.mx.get_peak_memory() if hasattr(self, 'mx') and hasattr(self.mx, 'get_peak_memory') else None
        import resource  # MLX-only measurement; offline replay works on Windows.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'peak_process_rss': {'bytes': rss if sys.platform == 'darwin' else rss * 1024,
                                    'api': 'resource.getrusage(RUSAGE_SELF).ru_maxrss',
                                    'scope': 'inference process lifetime, includes load and warmup'},
                'peak_mlx_allocator': {'bytes': peak, 'reason': None if peak is not None else 'API unavailable',
                                       'api': 'mlx.core.get_peak_memory', 'scope': 'run includes load and warmup'},
                'peaks_are_not_additive': True}


class ProcessAdapter:
    """Use a user-approved, preexisting MLX interpreter; scoring stays Python 3.10."""
    def __init__(self, python):
        self.python = python
        self.process = None

    def _call(self, command):
        self.process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise RuntimeError('MLX worker terminated unexpectedly (see inference-stderr.log)')
        result = json.loads(response)
        if 'worker_error' in result:
            raise RuntimeError(result['worker_error'])
        return result

    def load(self, config):
        self.stderr = open(config['_stderr_path'], 'w', encoding='utf-8')
        environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        self.process = subprocess.Popen([self.python, '-u', str(Path(__file__).resolve()), '--worker'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, env=environment)
        return self._call({'op': 'load', 'config': config})

    def generate(self, messages, generation_config):
        return self._call({'op': 'generate', 'messages': messages, 'generation_config': generation_config})

    def close(self):
        result = {'memory_reason': 'worker unavailable'}
        try:
            if self.process and self.process.poll() is None:
                result = self._call({'op': 'close'})
                self.process.wait(timeout=10)
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
            if self.process:
                self.process.stdin.close(); self.process.stdout.close()
            if hasattr(self, 'stderr'):
                self.stderr.close()
        return result


class FakeAdapter:
    """Test double; scripted raw only, never a gold-aware inference path."""
    def __init__(self, outputs, metadata=None):
        self.outputs = iter(outputs)
        self.metadata = metadata or {}
        self.calls = []

    def load(self, config):
        return {'model_id': 'fake-self-test', 'load_ms': 0, 'libraries': {}, **self.metadata}

    def generate(self, messages, generation_config):
        self.calls.append((messages, generation_config))
        raw = next(self.outputs)
        if isinstance(raw, Exception):
            raise raw
        return {'raw_output': raw, 'status': 'ok', 'error': None, 'finish_reason': 'stop',
                'generated_tokens': None, 'token_count_reason': 'fake adapter has no tokenizer',
                'request_ms': 1.0, 'rendered_prompt': json.dumps(messages, ensure_ascii=False),
                'template_settings': {'fake': True}}

    def close(self):
        return {'memory_reason': 'fake adapter, not a deployment measurement'}


def worker():
    import contextlib
    adapter = MLXAdapter()
    for line in sys.stdin:
        command = json.loads(line)
        try:
            # Libraries may print during load; protocol stdout must remain JSONL.
            with contextlib.redirect_stdout(sys.stderr):
                if command['op'] == 'load':
                    result = adapter.load(command['config'])
                elif command['op'] == 'generate':
                    result = adapter.generate(command['messages'], command['generation_config'])
                elif command['op'] == 'close':
                    result = adapter.close()
                else:
                    raise ValueError('unknown worker operation')
        except Exception as error:
            result = {'worker_error': type(error).__name__ + ': ' + str(error)}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
        if command['op'] == 'close':
            break


if __name__ == '__main__':
    if sys.argv[1:] != ['--worker']:
        raise SystemExit('internal MLX worker only')
    worker()
