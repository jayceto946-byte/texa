"""Opt-in, paid native-runtime smoke test with isolated synthetic learning data."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-paid', action='store_true', help='Authorize API calls and export of synthetic test inputs')
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--image', type=Path, help='Optional public/synthetic textbook image; never supply private materials without consent')
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error('--allow-paid is required')
    if not args.env.is_file() or (args.image and not args.image.is_file()):
        parser.error('Input file does not exist')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='texa-online-') as directory:
        os.environ['ENV_PATH'] = str(args.env.resolve())
        os.environ['DATA_DIR'] = directory
        # Explicit overrides prevent existing storage env from touching user records.
        for key, name in [('PROGRESS_PATH', 'progress'), ('MISTAKE_PATH', 'mistakes'),
                          ('EXERCISE_PATH', 'exercises')]:
            os.environ[key] = str(Path(directory) / name)
        import config  # Load .env before resolving roles.
        from llm.configuration import resolve_model_role
        from llm.tool_capability import verify_tool_capability
        from backend.services.goals.execution import summarize_goal
        from backend.services.agent_runtime.contracts import RunCommand
        from backend.services.agent_runtime.store import RuntimeStore
        from backend.services.agent_runtime.multi_step import BoundedAgentRunner
        from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
        from backend.services.agent_runtime.chat_binding import generate_answer
        from backend.tools.registry import ToolRegistry, ToolContext
        from memory.learning_events import LearningEvent, LearningEventStore
        from llm.agent_adapter import NativeToolAdapter
        resolved = resolve_model_role('reasoning')
        report = {'schema': 'texa.online-smoke/v1', 'model': resolved.model,
                  'provider': resolved.provider.provider_id, 'synthetic_data': True,
                  'accuracy_certification': False, 'results': []}
        def check(name, action):
            started = time.monotonic()
            try:
                result = action()
                record = {'case': name, 'ok': result is not False, 'result': result}
            except Exception as error:
                record = {'case': name, 'ok': False, 'error_type': type(error).__name__}
            record['seconds'] = round(time.monotonic() - started, 2)
            report['results'].append(record)
            print(json.dumps({'case': name, 'ok': record['ok'], 'seconds': record['seconds']}), flush=True)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        check('native_tool_capability', lambda: verify_tool_capability(resolved))
        check('goal_summary', lambda: summarize_goal('理解导数的几何意义，通过一道简单例题检查理解；没有教材，不安排期限。'))
        def runtime():
            root = Path(directory)
            store = RuntimeStore(root / 'runtime.db')
            events = LearningEventStore(root / 'learning.db')
            events.append(LearningEvent(event_type='chat_qa', book_name='default'))
            registry = ToolRegistry()
            register_recent_progress_runtime(registry, events)
            metadata = registry.runtime_tool('get_recent_progress').runtime_metadata()
            command = RunCommand('smoke', 'smoke', 'smoke', '', '',
                '先用 get_recent_progress 查询我的学习记录，再总结查询结果。', 'owner',
                budget_calls=2, budget_model_calls=4,
                required_outputs=[{'id': 'answer', 'kind': 'content', 'required': True}],
                trigger_kind='goal', trigger_id='smoke')
            run_id = store.create(command)['run']['id']
            result = BoundedAgentRunner(store, registry, NativeToolAdapter(resolved, registry),
                (metadata,)).run_offline(run_id, 'owner', context=ToolContext(book_name='default'),
                answer_state={'user_input': command.goal, 'intent': 'qa', 'use_textbook_context': False,
                              'answer_mode': 'global_general', 'book_name': 'default'},
                answer_generator=generate_answer)
            if result['task']['status'] != 'completed' or result['consumed_calls'] < 1:
                raise RuntimeError('runtime release gate did not pass')
            return {'status': result['task']['status'], 'calls': result['consumed_calls'],
                    'model_calls': result['consumed_model_calls'],
                    'answer': result['task']['artifacts'].get('final_answer')}
        check('bounded_goal_runtime', runtime)
        if args.image:
            from backend.services.multimodal_bridge import VisionModelBridge
            check('public_image_ir', lambda: VisionModelBridge().analyze(args.image,
                user_question='识别图中公式与实体关系；不清楚的内容明确说明。', subject='数学').to_dict())
        return 0 if all(item['ok'] for item in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
