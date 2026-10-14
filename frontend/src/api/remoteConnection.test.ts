import { afterEach, expect, it, vi } from 'vitest';
import type { ExecutionStreamEnvelope } from '../types';

function storage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) };
}
function browser(hostname = 'texa.example.ts.net', hash = '') {
  const localStorage = storage(); const sessionStorage = storage();
  const win = { location: { hostname, hash, pathname: '/', search: '', origin: `https://${hostname}` },
    localStorage, sessionStorage, history: { replaceState: vi.fn() }, setTimeout, clearTimeout, dispatchEvent: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal('window', win); return win;
}
afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it('uses same-origin API on a phone and strips desktop bootstrap secrets', async () => {
  const win = browser(undefined, '#access_token=s0-test-secret&api_base=http://127.0.0.1:9999/api');
  win.localStorage.setItem('kaoyan_api_token', 'old-secret');
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetchMock);
  const { get } = await import('./client'); await get('/books');
  expect(fetchMock.mock.calls[0][0]).toBe('/api/books');
  expect(fetchMock.mock.calls[0][1].headers.get('X-Kaoyan-Token')).toBe('s0-test-secret');
  expect(win.localStorage.getItem('kaoyan_api_token')).toBeNull();
  expect(win.sessionStorage.getItem('kaoyan_desktop_api_base')).toBeNull();
  expect(win.history.replaceState).toHaveBeenCalledWith(null, '', '/');
});
it('rejects stale phone credentials with a reconnect event', async () => {
  const win = browser(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '访问令牌无效或缺失。' }), { status: 401 })));
  const { get, setConnectionToken } = await import('./client'); setConnectionToken('s0-test-secret');
  await expect(get('/chat/conversations')).rejects.toThrow('访问令牌无效');
  expect(win.sessionStorage.getItem('kaoyan_api_token')).toBeNull();
  expect(win.dispatchEvent).toHaveBeenCalledOnce();
});
it('preserves the Electron cross-origin dev bootstrap', async () => {
  const win = browser('127.0.0.1', '#access_token=desktop-test&api_base=http://127.0.0.1:9999/api');
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetchMock);
  const { get } = await import('./client'); await get('/books');
  expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:9999/api/books');
  expect(win.localStorage.getItem('kaoyan_api_token')).toBe('desktop-test');
});
it.each(['closed', 'broken'])('reports %s SSE without a terminal event as failure', async (mode) => {
  browser();
  const body = new ReadableStream({ start(controller) { if (mode === 'closed') controller.close(); else controller.error(new TypeError('network lost')); } });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
  const { chatStream } = await import('./client'); const onEvent = vi.fn();
  const error = await new Promise<Error>((resolve) => chatStream('question', 'book', '数学', 'conv', 'turn', onEvent, resolve));
  expect(error.message).toMatch(/terminal|network|连接已中断/); expect(onEvent).not.toHaveBeenCalled();
});
it('marks a browser offline event as failure and removes its listener', async () => {
  const win = browser();
  vi.stubGlobal('fetch', vi.fn((_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    queueMicrotask(() => win.addEventListener.mock.calls.find(([name]) => name === 'offline')?.[1]());
  })));
  const { chatStream } = await import('./client');
  const onEvent = vi.fn();
  const error = await new Promise<Error>((resolve) => chatStream('question', 'book', '数学', 'conv', 'turn', onEvent, resolve));
  expect(error.message).toContain('回答尚未确认完成');
  expect(onEvent).not.toHaveBeenCalled();
  expect(win.removeEventListener).toHaveBeenCalledWith('offline', expect.any(Function));
});

it('preserves fragmented delayed SSE, Chinese text and Session identity without replaying the question', async () => {
  browser();
  const base = { schema: 'texa.execution/v1', request_id: 'req-network', task_id: 'task-network', run_id: 'run-network', conversation_id: 'conv-network', turn_id: 'turn-network', operation_id: 'answer', phase: 'generation', status: 'running', summary: '生成中', label: '生成回答', kind: 'generation', elapsed_ms: 1 };
  const envelopes = [
    { execution_event: { ...base, seq: 1, type: 'output_delta', payload: { text: '保持会话与公式 $x^2$。', replace: false } } },
    { execution_event: { ...base, seq: 2, type: 'final', phase: 'final', status: 'completed', payload: { task_status: 'completed' } } },
  ];
  const bytes = new TextEncoder().encode(envelopes.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''));
  const body = new ReadableStream<Uint8Array>({ async start(controller) {
    // Small delayed fragments emulate transport chunking, not a measured DERP link.
    for (let i = 0; i < bytes.length; i += 17) {
      controller.enqueue(bytes.slice(i, i + 17));
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    controller.close();
  } });
  const fetchMock = vi.fn().mockResolvedValue(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }));
  vi.stubGlobal('fetch', fetchMock);
  const { chatStream } = await import('./client'); const received: ExecutionStreamEnvelope[] = [];
  await new Promise<void>((resolve, reject) => chatStream('question', '', '', 'conv-network', 'turn-network', event => {
    received.push(event); if (event.execution_event.type === 'final') resolve();
  }, reject));
  expect(received).toHaveLength(2);
  expect(received[0].execution_event.payload.text).toBe('保持会话与公式 $x^2$。');
  expect(received.every(event => event.execution_event.conversation_id === 'conv-network')).toBe(true);
  expect(fetchMock).toHaveBeenCalledOnce();
});
