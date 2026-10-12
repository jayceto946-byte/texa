/** Synthetic UI acceptance: NODE_PATH=<bundled modules> node scripts/mobile-network-s2-smoke.mjs */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const output = resolve('docs/validation/mobile-network-s2');
mkdirSync(output, { recursive: true });
const fixture = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18039' }, stdio: 'ignore' });
let state = 'derp', probes = 0;
const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  if (path.startsWith('/api')) {
    res.setHeader('Content-Type', 'application/json');
    if (path.startsWith('/api/system/network-diagnostics')) {
      const probe = req.method === 'POST'; if (probe) { probes++; state = 'direct'; }
      const observation = { path: state, home_derp: 'sfo', source: 'tailscale_status', sampled_at: '2026-10-11T07:00:00Z' };
      res.end(JSON.stringify({ success: true, data: { observation, target_selected: state !== 'unknown', changed_at: observation.sampled_at,
        last_probe: probes ? { ...observation, source: 'tailscale_ping_disco', rtt_ms: 43 } : null,
        history: [{ ...observation, previous_path: 'derp' }], samples: [], probe_cooldown_seconds: 0,
        ...(probe ? { probe_result: 'direct_observed' } : {}) } })); return;
    }
    if (path === '/api/system/remote-ready') { res.end(JSON.stringify({ success: true, data: { ready: true, token_required: true } })); return; }
    const upstream = await fetch(`http://127.0.0.1:18039${req.url}`);
    let body = await upstream.json();
    if (path === '/api/chat/conversations') body.data = {items: body.data.map(item => ({...item, management: {state: 'active', pinned: false, revision: 0}})), next_cursor: null, has_more: false};
    if (path.endsWith('/management')) body.data = {state: 'active', pinned: false, revision: 0};
    res.end(JSON.stringify(body)); return;
  }
  const dist = resolve('frontend/dist'); let file = resolve(dist, `.${path}`);
  if (file !== dist && !file.startsWith(dist + '/')) { res.writeHead(403).end(); return; }
  if (!extname(file)) file = resolve(dist, 'index.html');
  try {
    const bytes = readFileSync(file);
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' })[extname(file)] || 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(18439, '127.0.0.1', r));
let browser; const results = { fixture: true, errors: [], sizes: [] };
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.TEXA_BENCH_BROWSER || chromium.executablePath() });
  for (const [width, height] of [[390, 844], [760, 820], [1024, 768], [1280, 820]]) {
    state = 'derp'; probes = 0;
    const page = await browser.newPage({ viewport: { width, height } });
    await page.addInitScript(() => localStorage.setItem('texa:setup-complete:v3', '1'));
    page.on('pageerror', error => results.errors.push(error.message));
    await page.goto('http://127.0.0.1:18439/settings');

    await page.getByRole('button', { name: '高级与诊断', exact: true }).click();
    await page.getByText('最近观察到连接路径', { exact: false }).waitFor();
    await page.getByText('开发诊断 · Network Diagnostics', { exact: true }).click();
    await page.getByText('当前路径估计：DERP', { exact: false }).waitFor();
    await page.getByRole('button', { name: '检测并尝试优化', exact: true }).click();
    await page.getByText('本次检测已观察到直连。', { exact: true }).waitFor();
    await page.getByText('当前路径估计：Direct', { exact: false }).waitFor();
    const section = page.locator('section.settings-section').filter({ has: page.getByRole('heading', { name: '网络连接', exact: true }) });
    await section.screenshot({ path: `${output}/network-${width}.png` });
    const overflow = await section.evaluate(el => el.scrollWidth > el.clientWidth + 1);
    if (overflow || probes !== 1) throw new Error(`UI overflow/probe count at ${width}`);
    state = 'unknown'; await page.getByRole('button', { name: '重新读取连接', exact: true }).click();
    await page.getByText('连接状态待确认', { exact: false }).waitFor();
    if (!await page.getByRole('button', { name: '检测并尝试优化', exact: true }).isDisabled()) throw new Error('Unavailable probe must be disabled');
    results.sizes.push({ width, height, overflow, probes, unavailableHandled: true }); await page.close();
  }
  writeFileSync(`${output}/ui-results.json`, JSON.stringify(results, null, 2)); console.log(JSON.stringify(results));
} finally { await browser?.close(); await new Promise(r => server.close(r)); fixture.kill(); }
