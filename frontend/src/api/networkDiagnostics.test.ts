import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('./client', () => mocks);
let win: EventTarget;
let doc: EventTarget & { visibilityState: string };
const data = { observation: { path: 'derp' }, target_selected: true };
beforeEach(() => {
  vi.resetModules(); mocks.get.mockReset(); mocks.post.mockReset();
  win = new EventTarget();
  Object.assign(win, { sessionStorage: { getItem: () => null, setItem: vi.fn() } });
  doc = Object.assign(new EventTarget(), { visibilityState: 'visible' });
  vi.stubGlobal('window', win); vi.stubGlobal('document', doc); vi.stubGlobal('navigator', { onLine: true });
  mocks.get.mockResolvedValue({ data }); mocks.post.mockResolvedValue({ data: { ...data, probe_result: 'relay_observed' } });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const flush = async () => { for (let n = 0; n < 15; n++) await Promise.resolve(); };

it('Auto observes once on restore and never sends active probes or learning writes', async () => {
  const { installNetworkRecovery } = await import('./networkDiagnostics');
  const stop = installNetworkRecovery();
  await flush();
  win.dispatchEvent(new Event('online')); doc.dispatchEvent(new Event('visibilitychange'));
  await flush();
  expect(mocks.get).toHaveBeenCalledOnce(); expect(mocks.post).not.toHaveBeenCalled();
  stop();
  vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 120000);
  win.dispatchEvent(new Event('online')); await flush();
  expect(mocks.get).toHaveBeenCalledOnce();
});
it('Prefer Direct coalesces wakeup and network change and retains relay fallback', async () => {
  let now = 100000; vi.spyOn(Date, 'now').mockImplementation(() => now);
  const { installNetworkRecovery, setNetworkStrategy } = await import('./networkDiagnostics');
  setNetworkStrategy('prefer_direct');
  const stop = installNetworkRecovery(); await flush();
  expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/system/network-diagnostics/probe', {}, 15000);
  win.dispatchEvent(new Event('online')); await flush();
  expect(mocks.post).toHaveBeenCalledOnce();
  now += 61000;
  mocks.get.mockResolvedValue({ data: { ...data, observation: { path: 'direct' } } });
  doc.dispatchEvent(new Event('visibilitychange')); await flush();
  expect(mocks.get).toHaveBeenCalledTimes(2); expect(mocks.post).toHaveBeenCalledOnce();
  stop();
});
it('does not send keepalive while hidden or offline', async () => {
  doc.visibilityState = 'hidden';
  const { installNetworkRecovery } = await import('./networkDiagnostics');
  const stop = installNetworkRecovery(); await flush();
  expect(mocks.get).not.toHaveBeenCalled();
  doc.visibilityState = 'visible'; vi.stubGlobal('navigator', { onLine: false });
  doc.dispatchEvent(new Event('visibilitychange')); await flush();
  expect(mocks.get).not.toHaveBeenCalled(); stop();
});
it('retries only a failed read once and never replays probe POST', async () => {
  const { queryNetwork } = await import('./networkDiagnostics');
  mocks.get.mockRejectedValueOnce(new TypeError('network changed'));
  expect(await queryNetwork()).toEqual(data); expect(mocks.get).toHaveBeenCalledTimes(2);
  mocks.post.mockRejectedValueOnce(new TypeError('lost connection'));
  await expect(queryNetwork(true)).rejects.toThrow('lost connection');
  expect(mocks.post).toHaveBeenCalledOnce();
});
it('does not confuse a pending passive read with an explicit probe result', async () => {
  const { queryNetwork } = await import('./networkDiagnostics');
  const read = queryNetwork(); const probe = queryNetwork(true);
  await expect(probe).resolves.toHaveProperty('probe_result', 'relay_observed'); await read;
  expect(mocks.get).toHaveBeenCalledOnce(); expect(mocks.post).toHaveBeenCalledOnce();
});
it('does not initiate a probe if the phone becomes hidden while status is pending', async () => {
  let resolveRead!: (value: { data: typeof data }) => void;
  mocks.get.mockImplementation(() => new Promise(resolve => { resolveRead = resolve; }));
  const { installNetworkRecovery, setNetworkStrategy } = await import('./networkDiagnostics');
  setNetworkStrategy('prefer_direct'); const stop = installNetworkRecovery();
  doc.visibilityState = 'hidden'; resolveRead({ data }); await flush();
  expect(mocks.post).not.toHaveBeenCalled(); stop();
});
