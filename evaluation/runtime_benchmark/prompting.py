"""Model boundary: only task/input become text; case IDs remain bookkeeping."""
from .scoring import read_json

PROMPT_VERSION = 'frozen-wire-schema-canonical-input/v0.1'
BUDGETS = {'policy_select': 128, 'goal_summary': 384,
           'question_understanding': 384, 'reference_resolve': 256}


class PromptBuilder:
    def __init__(self, benchmark):
        self.tasks = read_json(benchmark.root / 'prompts/tasks.json')
        self.schemas = {task: read_json(benchmark.root / f'schemas/{task}.output.schema.json') for task in BUDGETS}
        self.canonical = benchmark.scorer.canonical

    def build(self, case):
        if set(case) != {'id', 'task', 'input'}:
            raise ValueError('PromptBuilder accepts only id/task/input')
        task = case['task']
        return [{'role': 'system', 'content': self.tasks['wire'] + '\n' + self.tasks[task] +
                 '\noutput schema:\n' + self.canonical(self.schemas[task])},
                {'role': 'user', 'content': self.canonical(case['input'])}]


def smoke_case():
    # Independent synthetic example; never part of quality denominators.
    return {'id': 'synthetic-warmup', 'task': 'policy_select', 'input': {
        'request': '请直接解释什么是极限，不查询我的学习记录。',
        'context': {'resolved_query': '请直接解释什么是极限，不查询我的学习记录。', 'goal': None,
                    'constraints': {'answer_mode': 'global_general', 'subject': '数学', 'book_name': 'fixture'}},
        'admissible_actions': [{'id': 'warm-answer', 'kind': 'generate_answer', 'args': {}},
                               {'id': 'warm-progress', 'kind': 'call_tool',
                                'args': {'tool_id': 'get_recent_progress', 'input': {'days': 7, 'limit': 12,
                                                                                  'subject': '数学', 'book_name': 'fixture'}}}],
        'missing_inputs': [], 'previous_result': None}}
