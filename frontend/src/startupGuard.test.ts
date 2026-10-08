import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';

function guard(fetchMock?: typeof fetch) {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)![1];
  const report = { textContent: '' }; const message = { textContent: '' };
  const panel = { hidden: false, setAttribute: vi.fn(), querySelector: () => ({ textContent: '' }) };
  const listeners: Record<string, (event: any) => void> = {};
  const win: any = { isSecureContext: true, addEventListener: (name: string, listener: (event: any) => void) => { listeners[name] = listener; } };
  if (fetchMock) { win.fetch = fetchMock; win.AbortController = AbortController; }
  Object.defineProperty(win, 'localStorage', { get() { throw new Error('secret-token'); } });
  Object.defineProperty(win, 'sessionStorage', { get() { throw new Error('secret-token'); } });
  let timeout: () => void = () => {};
  runInNewContext(script, { window: win, navigator: { userAgent: 'Chrome/154.0.8037.57' },
    document: { getElementById: (id: string) => id === 'texa-startup' ? panel : id === 'texa-startup-report' ? report : message,
      querySelector: () => ({ content: 'test-build' }) },
    setTimeout: (callback: () => void) => { timeout = callback; return 1; }, clearTimeout: vi.fn() });
  return { win, listeners, report, panel, timeout };
}
it('remains visible before JS/React is ready and hides on a committed mount', () => {
  const g = guard(); expect(g.report.textContent).toContain('chrome=154');
  expect(g.report.textContent).toContain('sessionStorage=blocked');
  expect(g.panel.hidden).toBe(false); g.win.texaStartup.ready(); expect(g.panel.hidden).toBe(true);
});
it('reports script resource failures without URL secrets and preserves the first failure', () => {
  const g = guard(); g.listeners.error({ target: { tagName: 'SCRIPT', src: 'https://host/assets/app-123.js?token=secret-token#access_token=secret-token' } });
  g.win.texaStartup.fail('module-init', new Error('secret-token'));
  expect(g.report.textContent).toContain('stage=asset-load');
  expect(g.report.textContent).toContain('asset=app-123.js');
  expect(g.report.textContent).not.toContain('secret-token');
  g.win.texaStartup.ready(); expect(g.panel.hidden).toBe(false);
});
it.each(['react-render', 'module-init'])('shows %s without raw error or stack', (stage) => {
  const g = guard(); g.win.texaStartup.fail(stage, new TypeError('private-api-key'));
  expect(g.report.textContent).toContain(`stage=${stage}`);
  expect(g.report.textContent).toContain('error=TypeError');
  expect(g.report.textContent).not.toContain('private-api-key');
});
it('captures uncaught errors and unhandled initialization rejections', () => {
  const g = guard(); g.listeners.unhandledrejection({ reason: new SyntaxError('private-api-key') });
  expect(g.report.textContent).toContain('stage=unhandled-rejection');
  expect(g.report.textContent).not.toContain('private-api-key');
});
it('shows stalled startup and recovers when a slow mount finally succeeds', () => {
  const g = guard(); g.timeout(); expect(g.report.textContent).toContain('startup-timeout');
  g.win.texaStartup.ready(); expect(g.panel.hidden).toBe(true);
});

it('probes only same-origin static assets without credentials and exposes Android response metadata', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('css-body', { headers: { 'content-type': 'text/css' } }));
  const g = guard(fetchMock);
  g.listeners.error({ target: { tagName: 'LINK', rel: 'stylesheet', href: 'https://host/assets/vendor.css?token=secret-token' } });
  await vi.waitFor(() => expect(g.report.textContent).toContain('probeBytes=8'));
  expect(fetchMock).toHaveBeenCalledWith('/assets/vendor.css', expect.objectContaining({ credentials: 'omit', cache: 'no-store' }));
  expect(g.report.textContent).toContain('probeStatus=200');
  expect(g.report.textContent).toContain('probeType=text/css');
  expect(g.report.textContent).not.toContain('secret-token');
  g.win.texaStartup.ready(); expect(g.report.textContent).toContain('appMounted=true');
});
it('distinguishes a network failure from an HTTP error response', async () => {
  const g = guard(vi.fn().mockRejectedValue(new TypeError('private-key')));
  g.listeners.error({ target: { tagName: 'SCRIPT', src: 'https://host/assets/app.js' } });
  await vi.waitFor(() => expect(g.report.textContent).toContain('probeError=network-or-body-read'));
  expect(g.report.textContent).not.toContain('private-key');
});
