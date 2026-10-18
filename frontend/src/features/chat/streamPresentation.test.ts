import { expect, it } from 'vitest';
import { createExecutionLifecycle, mergeExecutionLifecycle } from '../../utils/chatActivities';
import { streamFailure, streamPresentation } from './streamPresentation';
import { isNearReadingBottom } from './useReadingScroll';

it('keeps exact partial math text after canonical errors and transport failures', () => {
  const content = '$$\\frac{1}{2}$$\n\n未完成推导';
  const lifecycle = mergeExecutionLifecycle(createExecutionLifecycle(content), {
    schema: 'texa.execution/v1', seq: 1, request_id: 'r', task_id: 't', run_id: 'run', conversation_id: 'c', turn_id: 'turn',
    operation_id: 'generate', type: 'error', phase: 'generate', status: 'failed', summary: '网络中断', label: '失败', kind: 'system', elapsed_ms: 1, payload: {},
  });
  expect(streamPresentation(lifecycle, '')).toEqual({ content, streamError: '网络中断' });
  expect(streamFailure('', content, '断线')).toEqual({ content, streamError: '断线' });
  expect(streamFailure('', '', '未接受')).toEqual({ content: '', streamError: '未接受' });
});

it('follows only at the reading bottom, including short content', () => {
  expect(isNearReadingBottom({ scrollHeight: 1000, scrollTop: 300, clientHeight: 500 })).toBe(false);
  expect(isNearReadingBottom({ scrollHeight: 1000, scrollTop: 460, clientHeight: 500 })).toBe(true);
  expect(isNearReadingBottom({ scrollHeight: 200, scrollTop: 0, clientHeight: 500 })).toBe(true);
});

it('does not resurrect text explicitly retracted by an empty replacement', () => {
  const lifecycle = { ...createExecutionLifecycle(''), hasOutput: true, terminalType: 'error' as const, errorMessage: '撤回' };
  expect(streamPresentation(lifecycle, '旧内容')).toEqual({ content: '', streamError: '撤回' });
});

it('retains a budget failure delivery while marking the task failed', () => {
  const base = { schema: 'texa.execution/v1' as const, request_id: 'r', task_id: 't', run_id: 'run',
    conversation_id: 'c', turn_id: 'turn', operation_id: 'output', phase: 'generate',
    label: '回答', kind: 'system', elapsed_ms: 1 };
  let lifecycle = mergeExecutionLifecycle(createExecutionLifecycle('未完成的模型草稿'), {
    ...base, seq: 3, type: 'output_delta', status: 'running', summary: '交付未完成状态',
    payload: { text: '任务未完成：预算已用尽。已计算（未独立核验）：1024。', replace: true },
  });
  lifecycle = mergeExecutionLifecycle(lifecycle, {
    ...base, seq: 4, type: 'error', status: 'failed', summary: '任务未完成',
    payload: { error_code: 'tool_budget_exhausted', task_status: 'failed' },
  });
  expect(lifecycle.taskStatus).toBe('failed');
  expect(lifecycle.errorCode).toBe('tool_budget_exhausted');
  expect(streamPresentation(lifecycle, '旧草稿')).toEqual({
    content: '任务未完成：预算已用尽。已计算（未独立核验）：1024。', streamError: '任务未完成',
  });
});
