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
