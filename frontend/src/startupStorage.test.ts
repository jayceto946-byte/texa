import { expect, it, vi } from 'vitest';
import { readStoredTexaTheme, applyTexaTheme } from './theme';
it('survives denied storage getters and still authenticates from page memory', async () => {
  const win = { location: { hostname: 'phone.example.ts.net', hash: '', pathname: '/', search: '' } };
  Object.defineProperty(win, 'localStorage', { get() { throw new DOMException('blocked', 'SecurityError'); } });
  Object.defineProperty(win, 'sessionStorage', { get() { throw new DOMException('blocked', 'SecurityError'); } });
  vi.stubGlobal('window', win);
  try {
    expect(readStoredTexaTheme()).toBe('mineral');
    const root = { dataset: {} as DOMStringMap, style: { setProperty: vi.fn() } as unknown as CSSStyleDeclaration };
    expect(() => applyTexaTheme('mineral', root)).not.toThrow();
    const client = await import('./api/client');
    client.setConnectionToken('test-only-token');
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);
    Object.assign(win, { setTimeout, clearTimeout });
    await client.get('/system/remote-ready');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/system/remote-ready');
    expect(fetchMock.mock.calls[0][1].headers.get('X-Kaoyan-Token')).toBe('test-only-token');
  } finally { vi.unstubAllGlobals(); }
});
it('renders existing Session provider when local storage is denied', async () => {
  const win = {};
  Object.defineProperty(win, 'localStorage', { get() { throw new DOMException('blocked', 'SecurityError'); } });
  vi.stubGlobal('window', win);
  try {
    const { createElement } = await import('react');
    const { renderToString } = await import('react-dom/server');
    const { ChatProvider } = await import('./contexts/ChatContext');
    expect(renderToString(createElement(ChatProvider, { children: createElement('span', {}, 'Session ready') }))).toContain('Session ready');
  } finally { vi.unstubAllGlobals(); }
});
