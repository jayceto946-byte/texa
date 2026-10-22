/** Production renderer + preload + real remote service over Electron IPC.
 * Tailscale/Windows and API responses are isolated fixtures; no real network configuration.
 * NODE_PATH=<Playwright packages> node scripts/qa-remote-connection-electron.mjs
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname, join } from 'node:path';
import { tmpdir } from 'node:os';

const { _electron } = createRequire(import.meta.url)('playwright');
const out = resolve(process.env.TEXA_QA_OUT || 'docs/qa/remote-connection-2026-10-22');
mkdirSync(out, { recursive: true });
const isolated = mkdtempSync(join(tmpdir(), 'texa-remote-electron-'));
const fixture = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], {
  env: { ...process.env, TEXA_VISUAL_PORT: '18183' }, stdio: 'ignore',
});
const server = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (pathname === '/api/chat/conversations') return reply({ items: [], has_more: false, next_cursor: null });
    if (pathname === '/api/system/network-diagnostics') return reply({
      observation: { path: 'unknown', error_code: 'peer_ambiguous', source: 'tailscale_status', sampled_at: '2026-10-22T14:00:00Z' },
      target_selected: false, history: [], samples: [], last_probe: null, probe_cooldown_seconds: 0,
    });
    if (pathname.startsWith('/api/') || pathname === '/health') {
      const upstream = await fetch('http://127.0.0.1:18183' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(upstream.status, { 'Content-Type': 'application/json' }); res.end(await upstream.text()); return;
    }
    const file = resolve('frontend/dist', extname(pathname) ? '.' + pathname : 'index.html');
    const dist = resolve('frontend/dist');
    if (!file.startsWith(dist + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream');
    res.end(readFileSync(file));
  } catch (error) { res.writeHead(500).end(String(error)); }
});

// Keep real Windows path discovery and error translation, replacing only CLI execution.
const harness = join(isolated, 'main.cjs');
writeFileSync(harness, `
const { app, BrowserWindow, ipcMain } = require('electron');
const { createRemoteConnection } = require(${JSON.stringify(resolve('desktop/remote-connection.cjs'))});
app.setPath('userData', ${JSON.stringify(isolated)});
const fixture = globalThis.texaRemoteFixture = { mode: 'normal', config: null, calls: [], copied: '', reset() { this.mode = 'normal'; this.config = null; this.calls = []; this.copied = ''; } };
const service = createRemoteConnection({ statePath: ${JSON.stringify(join(isolated, 'remote.json'))}, platform: 'win32', env: ${JSON.stringify({ ProgramW6432: String.raw`D:\Apps With Spaces` })}, getTarget: () => 'http://127.0.0.1:49200', isReady: () => true,
  run: async (file, args) => {
    fixture.calls.push({ file, args });
    if (fixture.mode === 'missing' || file !== ${JSON.stringify(String.raw`D:\Apps With Spaces\Tailscale\tailscale.exe`)}) throw Object.assign(new Error('missing'), { code: 'ENOENT' });
    if (args[0] === 'status') return JSON.stringify({ BackendState: 'Running', Self: { DNSName: 'my-pc.my-tailnet.ts.net.' } });
    if (args[1] === 'status') return JSON.stringify(fixture.config);
    if (fixture.mode === 'https') throw Object.assign(new Error('Serve requires setup'), { stderr: 'Serve is not enabled on your tailnet. https://login.tailscale.com/f/serve?secret=do-not-show' });
    if (fixture.mode === 'permission') throw Object.assign(new Error('access is denied'), { code: 1 });
    await new Promise(r => setTimeout(r, 120));
    fixture.config = args.includes('off') ? null : { Web: { 'my-pc.my-tailnet.ts.net:443': { Handlers: { '/': { Proxy: 'http://127.0.0.1:49200' } } } } };
    return '';
  }
});
ipcMain.handle('remote-s0:status', () => service.status());
ipcMain.handle('remote-s0:set-enabled', (_, enabled) => service.setEnabled(enabled));
ipcMain.handle('remote-s0:copy-url', async () => { const status = await service.status(); fixture.copied = status.url; return status.enabled; });
ipcMain.handle('remote-s0:copy-token', () => true);
ipcMain.handle('setup:get-complete', () => true);
ipcMain.on('appearance:get', event => { event.returnValue = null; });
ipcMain.handle('backend:status', () => ({ status: 'ready' }));
ipcMain.handle('window:is-fullscreen', () => false);
ipcMain.handle('window:is-maximized', () => false);
ipcMain.handle('updates:status', () => ({ status: 'idle', currentVersion: 'qa' }));
app.whenReady().then(() => {
  const window = new BrowserWindow({ width: 1280, height: 820, webPreferences: { preload: ${JSON.stringify(resolve('desktop/preload.cjs'))}, contextIsolation: true, sandbox: true } });
  window.loadURL('http://127.0.0.1:18182/settings');
});
`);

let app, page;
const results = { platform: 'macOS Electron; Windows CLI/Serve fixtures; no native Windows or real Tailscale changes', checks: [], errors: [] };
function check(ok, name) { results.checks.push({ name, pass: !!ok }); if (!ok) throw new Error(name); }
async function shot(name) { await page.screenshot({ path: resolve(out, name + '.png'), animations: 'disabled', scale: 'css' }); }
async function remotePage() {
  await page.goto('http://127.0.0.1:18182/settings');
  await page.locator('.app-shell').waitFor();
  await page.getByRole('button', { name: '手机连接', exact: true }).click();
  await page.getByRole('heading', { name: '连接这台电脑', exact: true }).waitFor();
}
try {
  await new Promise(r => server.listen(18182, '127.0.0.1', r));
  for (let n = 0; n < 40; n++) {
    try { await fetch('http://127.0.0.1:18183/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); }
  }
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [harness] });
  page = await app.firstWindow(); page.setDefaultTimeout(10000);
  page.on('pageerror', error => results.errors.push(String(error)));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => { globalThis.texaRemoteFixture.reset(); BrowserWindow.getAllWindows()[0].setContentSize(...size); }, [width, height]);
    await remotePage();
    await page.getByText('手机连接未开启', { exact: true }).waitFor();
    const enable = page.getByRole('button', { name: '开启手机连接', exact: true });
    check(await enable.isEnabled(), width + ' first-run null config allows enable');
    await enable.click();
    await page.getByRole('button', { name: '关闭手机连接', exact: true }).waitFor();
    check(await page.getByRole('link', { name: 'my-pc.my-tailnet.ts.net' }).getAttribute('href') === 'https://my-pc.my-tailnet.ts.net/', width + ' own user address generated');
    await page.getByRole('button', { name: '复制地址', exact: true }).click();
    check(await app.evaluate(() => globalThis.texaRemoteFixture.copied) === 'https://my-pc.my-tailnet.ts.net/', width + ' copy uses generated address');
    await shot(width + '-enabled');
    await page.getByRole('button', { name: '关闭手机连接', exact: true }).click();
    await page.getByText('手机连接未开启', { exact: true }).waitFor();

    await app.evaluate(() => { globalThis.texaRemoteFixture.mode = 'https'; });
    await page.getByRole('button', { name: '开启手机连接', exact: true }).click();
    await page.getByRole('link', { name: '打开 Tailscale HTTPS 设置', exact: true }).waitFor();
    check(await page.getByRole('link', { name: '打开 Tailscale HTTPS 设置' }).getAttribute('href') === 'https://login.tailscale.com/admin/dns', width + ' HTTPS setup recovery offered');
    check(!/do-not-show|f\/serve|请确认 Tailscale 已登录/.test(await page.locator('.remote-connection').innerText()), width + ' sanitized actionable failure');
    check(await page.locator('.remote-connection').evaluate(el => el.scrollWidth <= el.clientWidth + 1), width + ' long failure text fits');
    check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), width + ' no page overflow');
    await shot(width + '-https-required');
    await app.evaluate(() => { globalThis.texaRemoteFixture.mode = 'normal'; });
    await page.getByRole('button', { name: '刷新手机连接状态' }).click();
    await page.getByText('手机连接未开启', { exact: true }).waitFor();
    check(await page.getByRole('link', { name: '打开 Tailscale HTTPS 设置' }).count() === 0, width + ' refresh clears stale failure');
    await page.getByRole('button', { name: '开启手机连接', exact: true }).click();
    await page.getByRole('button', { name: '关闭手机连接', exact: true }).waitFor();
    check(await app.evaluate(() => globalThis.texaRemoteFixture.calls.some(call => call.args.includes('http://127.0.0.1:49200'))), width + ' actual target reaches CLI');
  }
  await app.evaluate(() => { globalThis.texaRemoteFixture.reset(); globalThis.texaRemoteFixture.mode = 'permission'; });
  await remotePage(); await page.getByRole('button', { name: '开启手机连接', exact: true }).click();
  await page.getByText('当前用户无权执行 Tailscale 操作', { exact: false }).waitFor();
  check(true, 'permission failure survives IPC with recovery text'); await shot('permission');
  await app.evaluate(() => { globalThis.texaRemoteFixture.mode = 'missing'; });
  await page.getByRole('button', { name: '刷新手机连接状态' }).click();
  await page.getByText('未找到 Tailscale 命令行程序', { exact: false }).waitFor();
  check(true, 'missing CLI distinguished from logged out'); await shot('missing-cli');
  const back = page.getByRole('button', { name: '返回设置', exact: true });
  if (await back.isVisible()) await back.click();
  await page.getByRole('button', { name: '高级与诊断', exact: true }).click();
  await page.getByText('开发诊断 · Network Diagnostics', { exact: true }).click();
  await page.getByText('自动识别唯一 Android、iPhone 或 iPad', { exact: false }).waitFor();
  check(await page.getByRole('button', { name: '检测并尝试优化', exact: true }).isDisabled(), 'ambiguous mobile peers cannot be probed');
  await shot('ambiguous-diagnostics');
  check(results.errors.length === 0, 'no renderer exceptions');
} catch (error) { results.errors.push(String(error)); process.exitCode = 1; await shot('failure').catch(() => {}); }
finally {
  writeFileSync(resolve(out, 'results.json'), JSON.stringify(results, null, 2));
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {});
  server.close(); fixture.kill(); console.log(JSON.stringify(results));
}
