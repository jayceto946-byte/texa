"""Actual embedding-input identity and lossless, token-bounded dense views.

Dense views are encoding windows, not independently displayable math or source
chunks. The lexical catalog and vector raw_content retain the complete source
chunk; a hit on any window hydrates that same authoritative chunk.
"""
from copy import deepcopy
import hashlib
import json

VIEW_SCHEMA = 'texa.embedding-views/v1'
WINDOW_OVERLAP_CHARS = 64


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class EmbeddingInputError(ValueError):
    pass


class EmbeddingInputContract:
    def __init__(self, identity, count_tokens):
        self._identity = json.loads(canonical_json(identity))
        limit = self._identity.get('max_length')
        if type(limit) is not int or limit < 4:
            raise EmbeddingInputError('嵌入模型没有可验证的 token 上限')
        self.max_length = limit
        self._count_tokens = count_tokens
        self.contract_id = sha256(canonical_json(self._identity))

    @property
    def identity(self):
        return deepcopy(self._identity)

    def count(self, text):
        count = self._count_tokens(text)
        if type(count) is not int or count < 0:
            raise EmbeddingInputError('嵌入 tokenizer 返回了无效长度')
        return count

    def require_fitting(self, texts):
        for index, text in enumerate(texts):
            count = self.count(text)
            if count > self.max_length:
                raise EmbeddingInputError(f'嵌入输入 {index} 为 {count} token，超过模型上限 {self.max_length}；已拒绝静默截断')

    def windows(self, text):
        if not text:
            raise EmbeddingInputError('嵌入输入为空')
        result, start = [], 0
        while start < len(text):
            if len(result) >= 8192:
                raise EmbeddingInputError('单个来源块的向量窗口超出安全预算')
            end = len(text)
            if self.count(text[start:end]) > self.max_length:
                low, high = start + 1, end
                end = start
                while low <= high:
                    middle = (low + high) // 2
                    if self.count(text[start:middle]) <= self.max_length:
                        end, low = middle, middle + 1
                    else:
                        high = middle - 1
                if end == start:
                    raise EmbeddingInputError('嵌入模型无法编码最小 Unicode 来源范围')
                # Prefer a real prose boundary, while retaining exact offsets.
                lower = start + max(1, (end-start)//2)
                for separator in ('\n\n', '\n', '。', '；', '，', ' '):
                    at = text.rfind(separator, lower, end)
                    candidate = at + len(separator)
                    if at >= lower and self.count(text[start:candidate]) <= self.max_length:
                        end = candidate
                        break
            value = text[start:end]
            count = self.count(value)
            if not value or count > self.max_length:
                raise EmbeddingInputError('向量窗口未满足实际 tokenizer 预算')
            result.append(dict(start=start, end=end, token_count=count, sha256=sha256(value)))
            if end == len(text):
                break
            start = max(start + 1, end - min(WINDOW_OVERLAP_CHARS, (end-start)//4))
        return result


def require_contract(embeddings):
    contract = getattr(embeddings, 'input_contract', None)
    if not isinstance(contract, EmbeddingInputContract):
        raise EmbeddingInputError('嵌入服务未提供模型、tokenizer 和输入长度合同，候选索引未发布')
    return contract


def embedding_text(row):
    return str(row.get('retrieval_text') or row.get('content') or '')


def prepare_embedding_views(chunks, contract):
    result = []
    for original in chunks:
        row = dict(original)
        text = embedding_text(row)
        row.update(embedding_view_schema=VIEW_SCHEMA, embedding_contract_id=contract.contract_id,
                   embedding_input_sha256=sha256(text),
                   embedding_views=[] if row.get('retrieval_excluded') else contract.windows(text))
        result.append(row)
    validate_embedding_views(result, contract)
    return result


def validate_embedding_views(chunks, contract):
    windows = 0
    for row in chunks:
        if row.get('retrieval_excluded'):
            continue
        text = embedding_text(row)
        views = row.get('embedding_views')
        if (row.get('embedding_view_schema') != VIEW_SCHEMA
                or row.get('embedding_contract_id') != contract.contract_id
                or row.get('embedding_input_sha256') != sha256(text)
                or not isinstance(views, list) or not views):
            raise EmbeddingInputError('向量窗口身份与实际输入不一致')
        covered = 0
        previous_start = -1
        for view in views:
            if not isinstance(view, dict):
                raise EmbeddingInputError('向量窗口范围无效')
            start, end = view.get('start'), view.get('end')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or start > covered or start <= previous_start):
                raise EmbeddingInputError('向量窗口存在空洞或顺序错误')
            value = text[start:end]
            count = contract.count(value)
            if count > contract.max_length or view.get('token_count') != count or view.get('sha256') != sha256(value):
                raise EmbeddingInputError('向量窗口被截断或内容已改变')
            covered = max(covered, end)
            previous_start = start
            windows += 1
        if covered != len(text):
            raise EmbeddingInputError('向量窗口没有覆盖完整嵌入输入')
    return dict(schema=VIEW_SCHEMA, contract_id=contract.contract_id, vector_count=windows,
                silent_truncations=0, input_coverage='complete')


def onnx_contract(asset_dir, runtime_tokenizer, *, verified_manifest=None):
    from tokenizers import Tokenizer
    from ingestion.embedding_assets import validate_asset_dir
    manifest = verified_manifest if verified_manifest is not None else validate_asset_dir(asset_dir, full_hash=True)
    tokenizer = Tokenizer.from_str(runtime_tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()
    identity = {key: manifest[key] for key in ('model_name', 'model_version', 'onnx_graph_version',
        'embedding_dimension', 'dtype', 'pooling', 'normalization', 'max_length', 'tokenizer_version')}
    identity.update(backend='onnxruntime_fp32', tokenizer_effective_sha256=sha256(tokenizer.to_str()),
                    assets={item['path']: item['sha256'] for item in manifest['expected_files']},
                    document_overflow='reject', query_overflow='right_truncate', special_tokens=True)
    return EmbeddingInputContract(identity, lambda text: len(tokenizer.encode(text).ids))


def torch_contract(model):
    """Development reference backend; identity covers actual weights/configs."""
    digest = hashlib.sha256()
    for name, value in sorted(model.state_dict().items()):
        tensor = value.detach().cpu().contiguous()
        digest.update(name.encode())
        digest.update(str(tensor.dtype).encode())
        digest.update(str(tuple(tensor.shape)).encode())
        digest.update(tensor.numpy().tobytes())
    tokenizer = model.tokenizer
    backend = getattr(tokenizer, 'backend_tokenizer', None)
    tokenizer_state = backend.to_str() if backend is not None else canonical_json(tokenizer.get_vocab())
    configs = [module.get_config_dict() for module in model._modules.values() if hasattr(module, 'get_config_dict')]
    first = model._first_module()
    lowercase = bool(getattr(first, 'do_lower_case', False))
    prompt = (getattr(model, 'prompts', {}) or {}).get(getattr(model, 'default_prompt_name', None), '')
    identity = dict(backend='sentence_transformers', model_weights_sha256=digest.hexdigest(),
                    tokenizer_sha256=sha256(tokenizer_state), modules=configs,
                    max_length=int(model.max_seq_length), normalization='normalize_embeddings=True',
                    special_tokens=True, document_overflow='reject', query_overflow='reference_default',
                    strip_text=True, lowercase=lowercase, default_prompt_sha256=sha256(prompt))
    def count(text):
        value = (prompt + text).strip()
        return len(tokenizer.encode(value.lower() if lowercase else value, add_special_tokens=True, truncation=False))
    return EmbeddingInputContract(identity, count)
