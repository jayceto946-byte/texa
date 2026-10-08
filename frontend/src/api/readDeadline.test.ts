import { afterEach, expect, it, vi } from 'vitest';

function browser() {
  vi.stubGlobal('window', { location: { hostname: 'localhost', hash: '', origin: 'http://localhost' }, setTimeout, clearTimeout });
}
afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it('times out a stalled JSON body after headers without reporting success', async () => {
  browser();
  let streamController: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(controller) { streamController = controller; } });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { headers: { 'Content-Type': 'application/json' } })));
  const { get } = await import('./client');
  await expect(get('/chat/conversations', 10)).rejects.toThrow('读取响应正文，HTTP 200');
  streamController!.close();
});
it('keeps JSON and an SSE response readable without buffering the stream', async () => {
  browser();
  const fetchMock = vi.fn().mockResolvedValueOnce(new Response('{"success":true}', { headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fetchMock);
  const { get, apiFetch } = await import('./client');
  expect(await get('/books/list')).toEqual({ success: true });
  const stream = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('data: first\n\n')); } });
  fetchMock.mockResolvedValueOnce(new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }));
  const response = await apiFetch('/chat/stream');
  const reader = response.body!.getReader();
  expect(new TextDecoder().decode((await reader.read()).value)).toBe('data: first\n\n');
  await reader.cancel();
});
