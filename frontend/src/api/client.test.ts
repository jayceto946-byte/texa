import { describe, expect, it, vi } from 'vitest';

import type { ExecutionEvent } from '../types';
import { consumeSseLine, interruptChatTask, interruptFigureTask } from './client';

it('addresses Chat and Figure interruption to the exact active run', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true }), {
    headers: { 'Content-Type': 'application/json' },
  }));
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('window', { setTimeout, clearTimeout, localStorage: { getItem: () => null } });
  try {
    await interruptChatTask('task-chat', 'partial', 'run-chat');
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ success: true })));
    await interruptFigureTask('task-figure', 'partial', 'run-figure');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ run_id: 'run-chat', partial_output: 'partial' });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({ run_id: 'run-figure' });
  } finally {
    vi.unstubAllGlobals();
  }
});

function event(overrides: Partial<ExecutionEvent> = {}): ExecutionEvent {
  return {
    schema: 'texa.execution/v1', request_id: 'req-1', task_id: 'task-1', run_id: 'run-1',
    conversation_id: 'conversation-1', turn_id: 'turn-1', seq: 1, operation_id: 'answer',
    type: 'final', phase: 'final', status: 'completed', summary: '回答完成', label: '完成回答',
    kind: 'generation', elapsed_ms: 10, payload: { task_status: 'completed' }, ...overrides,
  };
}

describe('canonical execution SSE parser', () => {
  it('accepts a legacy-free event with a domain result sidecar', () => {
    const onEvent = vi.fn();
    const boundary = consumeSseLine(`data: ${JSON.stringify({
      execution_event: event(),
      result: { linked_concepts: [{ name: '矩阵的秩' }] },
    })}`, onEvent);

    expect(boundary).toBe(true);
    expect(onEvent).toHaveBeenCalledOnce();
    expect(onEvent.mock.calls[0][0].result?.linked_concepts?.[0].name).toBe('矩阵的秩');
  });

  it.each(['stage', 'activity', 'chunk', 'replace', 'done', 'message', 'error_code', 'run_id', 'status'])(
    'rejects removed top-level %s lifecycle projection',
    (field) => {
      const onEvent = vi.fn();
      const boundary = consumeSseLine(`data: ${JSON.stringify({
        execution_event: event(),
        [field]: field === 'replace' || field === 'done' ? false : 'legacy',
      })}`, onEvent);

      expect(boundary).toBe(false);
      expect(onEvent).not.toHaveBeenCalled();
    },
  );
});
