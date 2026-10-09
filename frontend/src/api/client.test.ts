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

describe('photo multipart transport', () => {
  it.each(['complete', 'missing-boundary', 'upload-error', 'answer-error', 'http-error', 'timeout'])(
    'handles %s without resending the photo', async scenario => {
      const { mistakeSolutionStream, setConnectionToken, IMAGE_SOLUTION_TIMEOUT_MS } = await import('./client');
      vi.useFakeTimers();
      const headers: Record<string, string> = {};
      class FakeXhr {
        static latest: FakeXhr;
        upload = { onprogress: null as null | ((event: { loaded: number; total: number; lengthComputable: boolean }) => void), onload: null as null | (() => void) };
        responseText = '';
        status = 200;
        onprogress: null | (() => void) = null;
        onload: null | (() => void) = null;
        onerror: null | (() => void) = null;
        open = vi.fn(); send = vi.fn(); abort = vi.fn();
        setRequestHeader(key: string, value: string) { headers[key] = value; }
        constructor() { FakeXhr.latest = this; }
      }
      vi.stubGlobal('XMLHttpRequest', FakeXhr);
      vi.stubGlobal('window', { setTimeout, clearTimeout, localStorage: { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() } });
      setConnectionToken('test-photo-token');
      const onEvent = vi.fn(), onError = vi.fn(), onUpload = vi.fn();
      try {
        const payload = new FormData();
        payload.append('file', new Blob(['photo']), 'photo.jpg');
        mistakeSolutionStream('/mistakes/solve-image-stream', payload, onEvent, onError, onUpload);
        expect(FakeXhr.latest.send).toHaveBeenCalledExactlyOnceWith(payload);
        expect(headers['x-kaoyan-token']).toBe('test-photo-token');
        expect(headers['content-type']).toBeUndefined();
        FakeXhr.latest.upload.onprogress?.({ loaded: 5, total: 10, lengthComputable: true });
        expect(onUpload).toHaveBeenCalledWith(5, 10);
        if (scenario === 'upload-error') FakeXhr.latest.onerror?.();
        else if (scenario === 'timeout') await vi.advanceTimersByTimeAsync(IMAGE_SOLUTION_TIMEOUT_MS);
        else {
          FakeXhr.latest.upload.onload?.();
          if (scenario === 'answer-error') FakeXhr.latest.onerror?.();
          else {
            FakeXhr.latest.status = scenario === 'http-error' ? 413 : 200;
            FakeXhr.latest.responseText = scenario === 'http-error' ? JSON.stringify({ detail: '图片过大' }) : scenario === 'complete' ? `data: ${JSON.stringify({ execution_event: event() })}\n\n` : '';
            FakeXhr.latest.onprogress?.();
            await FakeXhr.latest.onload?.();
          }
        }
        await vi.waitFor(() => scenario === 'complete' ? expect(onEvent).toHaveBeenCalledOnce() : expect(onError).toHaveBeenCalledOnce());
        if (scenario === 'complete') expect(onError).not.toHaveBeenCalled();
        else expect(onError.mock.calls[0][0].message).toContain({
          'missing-boundary': '结束边界', 'upload-error': '照片上传失败', 'answer-error': '照片已上传', 'http-error': '图片过大', timeout: '照片上传超时',
        }[scenario]!);
        expect(FakeXhr.latest.send).toHaveBeenCalledOnce();
      } finally { setConnectionToken(''); vi.useRealTimers(); vi.unstubAllGlobals(); }
    },
  );
});
