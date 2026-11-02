"""One durable receipt per model request, shared by text and visual import review."""
import json
import time
from copy import deepcopy
from pathlib import Path

from llm.factory import create_vision_completion, vision_without_thinking, vision_image_token_reservation
from llm.pricing import import_rates, usage_cost
from utils.json_io import atomic_write_json
from utils.thinking_filter import strip_thinking


def validate_review_response(result):
    if not isinstance(result, dict):
        raise ValueError('校对结果须为JSON对象')
    required = {'edits': ('block_id','find','replace'), 'blocks': ('block_id',),
                'splits': ('block_id','segments'), 'groups': ('keep','merge'), 'metadata': ('block_id','evidence')}
    for key, fields in required.items():
        values = result.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v,dict) or any(f not in v for f in fields) for v in values):
            raise ValueError('校对结果字段不符合约定')
        if 'block_id' in fields and any(not isinstance(v['block_id'],str) for v in values):
            raise ValueError('校对来源ID须为字符串')
    for item in result.get('blocks', []):
        if (item.get('unit_id') is not None and not isinstance(item['unit_id'],str)
                or item.get('group_members') is not None and (not isinstance(item['group_members'],list) or any(not isinstance(b,str) for b in item['group_members']))):
            raise ValueError('题目归属字段不符合约定')
    for edit in result.get('edits', []):
        if any(not isinstance(edit[k],str) for k in ('block_id','find','replace')):
            raise ValueError('文字修正须为字符串')
    for split in result.get('splits', []):
        if not isinstance(split['segments'],list) or any(not isinstance(s,dict) or not isinstance(s.get('starts_with'),str) for s in split['segments']):
            raise ValueError('分段结果不符合约定')
    for item in result.get('metadata', []):
        if not isinstance(item['evidence'],list) or any(not isinstance(e,dict) or not isinstance(e.get('block_id'),str) or not isinstance(e.get('quote'),str) for e in item['evidence']):
            raise ValueError('题目属性依据不符合约定')
    for item in result.get('groups', []):
        if not isinstance(item['keep'],str) or not isinstance(item['merge'],list) or any(not isinstance(b,str) for b in item['merge']):
            raise ValueError('题解配对不符合约定')
    if not isinstance(result.get('unresolved', []),list):
        raise ValueError('未完成项须为列表')
    if 'page_blocks' in result and (not isinstance(result['page_blocks'],list) or any(not isinstance(b,dict) or not isinstance(b.get('text'),str) for b in result['page_blocks'])):
        raise ValueError('原页转录格式不正确')
    return result


class ReviewSession:
    def __init__(self, resolved, directory, identity, *, max_cost_cny=3, complete=None, check_cancelled=lambda: None, retry_failed=False):
        self.resolved = vision_without_thinking(resolved)
        self.rates = import_rates(resolved)
        self.path = Path(directory) / 'semantic_review.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        previous = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if previous and previous.get('identity') != identity:
            # Keep receipts from older prompt/source versions available for audit.
            atomic_write_json(self.path.with_name(f'semantic_review.previous-{time.time_ns()}.json'), previous)
        self.ledger = previous if previous.get('identity') == identity else dict(identity=identity, calls=[])
        self.maximum = max_cost_cny
        self.complete = complete or create_vision_completion
        self.check_cancelled = check_cancelled
        self.retry_failed = retry_failed
        self.new_calls = 0
        self.reused_calls = 0

    def call(self, key, system, content, *, max_tokens=8000):
        self.check_cancelled()
        old = next((c for c in reversed(self.ledger['calls']) if c['key'] == key), None)
        if old:
            if old['status'] == 'completed':
                self.reused_calls += 1
                return deepcopy(old['result'])
            if not self.retry_failed:
                raise ValueError('上次请求未完整完成，已保留回执；请检查连接后显式重新整理')
        content = [dict(type='text', text=content)] if isinstance(content, str) else content
        reserve_tokens = len(system.encode()) + sum(len(x.get('text', '').encode()) for x in content)
        reserve_tokens += sum(x['type'] == 'image_url' for x in content) * vision_image_token_reservation(self.resolved)
        reserve = ((reserve_tokens * self.rates['input_price'] + max_tokens * self.rates['output_price']) / 1_000_000) if self.rates else None
        spent = sum(c.get('cost_cny') or c.get('reserved_cny') or 0 for c in self.ledger['calls'])
        if reserve is not None and spent + reserve > self.maximum:
            raise ValueError('已达到本次整理费用上限，已完成的内容已保留')
        if sum(c.get('reserved_tokens', 0) for c in self.ledger['calls']) + reserve_tokens > 2_000_000:
            raise ValueError('本次整理内容超过处理上限，请缩小物理页范围')
        entry = dict(key=key, status='in_flight', reserved_cny=reserve, reserved_tokens=reserve_tokens,
                     rates=self.rates, sent_at=time.time(),attempt=1+sum(c['key']==key for c in self.ledger['calls']))
        self.ledger['calls'].append(entry); atomic_write_json(self.path, self.ledger)
        self.new_calls += 1
        started = time.monotonic()
        try:
            response = self.complete(self.resolved, messages=[dict(role='system', content=system), dict(role='user', content=content)],
                                     max_tokens=max_tokens, timeout=120, stream=False)
            entry['elapsed_seconds'] = round(time.monotonic() - started, 3)
            usage = getattr(response, 'usage', None)
            entry['usage'] = usage.model_dump() if hasattr(usage, 'model_dump') else (usage if isinstance(usage, dict) else {})
            entry['cost_cny'] = usage_cost(entry['usage'], self.rates)
            entry['model'] = getattr(response, 'model', self.resolved.model)
            entry['request_id'] = getattr(response, 'id', None)
            choice = response.choices[0]
            entry['finish_reason'] = getattr(choice,'finish_reason','stop')
            if getattr(choice, 'finish_reason', 'stop') != 'stop':
                entry['partial_output'] = strip_thinking(choice.message.content or '')
                raise ValueError('整理结果未完整返回')
            raw = strip_thinking(choice.message.content or '').strip()
            if raw.startswith('```'): raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0]
            result = validate_review_response(json.loads(raw))
            entry.update(result=result, status='completed')
        except Exception as exc:
            entry['status'] = 'failed'
            entry['error_type'] = type(exc).__name__
            reason = ('模型输出达到长度上限，请缩小范围' if entry.get('finish_reason') == 'length'
                      else '模型未返回可用的JSON校对结果' if isinstance(exc, (ValueError, TypeError, KeyError))
                      else '模型连接或服务请求失败，请检查网络与模型设置')
            entry['failure_reason'] = reason
            atomic_write_json(self.path, self.ledger)
            raise ValueError(reason + '；已保留用量，未自动重试') from None
        atomic_write_json(self.path, self.ledger)
        self.check_cancelled()
        return deepcopy(entry['result'])

    def report(self):
        calls = self.ledger['calls']
        return dict(model=self.resolved.model, calls=len(calls),
                    new_calls=self.new_calls,reused_calls=self.reused_calls,
                    prompt_tokens=sum(c.get('usage', {}).get('prompt_tokens', 0) for c in calls),
                    completion_tokens=sum(c.get('usage', {}).get('completion_tokens', 0) for c in calls),
                    estimated_cost_cny=sum(c.get('cost_cny') or c.get('reserved_cny') or 0 for c in calls) if self.rates else None,
                    usage_unknown=any(not c.get('usage') for c in calls),
                    failures=[dict(key=c['key'],reason=c.get('failure_reason','请求未完成'),error_type=c.get('error_type',''))
                              for c in calls if c['status'] != 'completed' and not any(n['key']==c['key'] and n['status']=='completed' for n in calls)],
                    model_seconds=sum(c.get('elapsed_seconds', 0) for c in calls), rates=self.rates)
