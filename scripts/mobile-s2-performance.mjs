/** Controlled S2 browser benchmark. Only synthetic fixtures; no user API/model calls.
 * NODE_PATH=<bundled node_modules> node scripts/mobile-s2-performance.mjs <dist> <output> <cert-dir>
 * Requires Playwright and a local disposable TLS certificate (see validation README).
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:https';
import { createServer as createHttpServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname, dirname } from 'node:path';
import { gzipSync } from 'node:zlib';
import { spawn } from 'node:child_process';
const require = createRequire(import.meta.url);
const { chromium, _electron } = require('playwright');
const [dist, output, certDir] = process.argv.slice(2);
if (!certDir) throw new Error('Arguments: dist output cert-dir');
const fixturePort = 18029;
const child = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: String(fixturePort) }, stdio: 'ignore' });
let streamRequests = 0;
let bookRequests = 0;
await new Promise(r => setTimeout(r, 300));
const handler = async (req, res) => {
  const path = new URL(req.url, 'https://texa.test').pathname;
  if (path === '/api/system/remote-ready') {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ success: true, data: { ready: true, token_required: true } })); return;
  }
  if (path === '/api/chat/stream') {
    streamRequests++;
    res.setHeader('Content-Type', 'text/event-stream');
    for (let seq = 1; seq <= 21; seq++) {
      const type = seq === 21 ? 'error' : 'output_delta';
      res.write(`data: ${JSON.stringify({ execution_event: {
        schema: 'texa.execution/v1', seq, request_id: 'fixture-request', task_id: 'fixture-task', run_id: 'fixture-run',
        conversation_id: 'visual-session-0', turn_id: 'fixture-turn', operation_id: 'generate', type, phase: 'generate',
        status: type === 'error' ? 'failed' : 'running', summary: type === 'error' ? 'fixture interruption' : '',
        label: '生成', kind: 'system', elapsed_ms: seq * 150,
        payload: type === 'error' ? { error_code: 'fixture_interruption' } : { text: `保留片段${seq}。$x^2$\n\n`, replace: false },
      } })}\n\n`);
      await new Promise(r => setTimeout(r, 150));
    }
    res.end(); return;
  }
  if (path.startsWith('/api/') || path === '/health') {
    if (path === '/api/books/list') bookRequests++;
    const started = performance.now();
    const upstream = await fetch(`http://127.0.0.1:${fixturePort}${req.url}`, { method: req.method });
    let bytes = Buffer.from(await upstream.arrayBuffer());
    if (path === '/api/chat/conversations') {
      const data = JSON.parse(bytes.toString());
      data.data = { items: data.data.map(item => ({ ...item, management: { state: 'active', pinned: false, revision: 0 } })), next_cursor: null, has_more: false };
      bytes = Buffer.from(JSON.stringify(data));
    }
    if (path.endsWith('/management')) bytes = Buffer.from(JSON.stringify({ success: true, data: { state: 'active', pinned: false, revision: 0 } }));
    if (/^\/api\/chat\/conversations\/visual-session-\d+$/.test(path)) {
      const data = JSON.parse(bytes.toString());
      data.data.messages = Array.from({ length: 100 }, (_, i) => ({ ...data.data.messages[i % 2], id: `fixture-message-${i}`, turn_id: `fixture-turn-${Math.floor(i / 2)}` }));
      bytes = Buffer.from(JSON.stringify(data));
    }
    res.statusCode = upstream.status;
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Server-Timing', `texa_read;dur=${(performance.now() - started).toFixed(1)}`);
    res.setHeader('Cache-Control', 'no-store');
    if (bytes.length >= 1024) { bytes = gzipSync(bytes); res.setHeader('Content-Encoding', 'gzip'); }
    res.end(bytes); return;
  }
  const file = resolve(dist, path === '/' ? 'index.html' : `.${path}`);
  if (!file.startsWith(resolve(dist) + '/')) { res.writeHead(403); res.end(); return; }
  try {
    let bytes = readFileSync(file);
    const ext = extname(file);
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml' })[ext] || 'application/octet-stream');
    if (['.js', '.css'].includes(ext)) { bytes = gzipSync(bytes); res.setHeader('Content-Encoding', 'gzip'); }
    res.setHeader('Cache-Control', path.startsWith('/assets/') ? 'public,max-age=31536000,immutable' : 'no-store');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
};
const server = createServer({ key: readFileSync(resolve(certDir, 'key.pem')), cert: readFileSync(resolve(certDir, 'cert.pem')) }, handler);
await new Promise(r => server.listen(18429, '127.0.0.1', r));
let browser;
const results = { fixture: true, network: { latencyMs: 400, downBytesPerSec: 625000, upBytesPerSec: 125000 }, cold: [], warm: [], errors: [] };
try {
  browser = await chromium.launch({ executablePath: process.env.TEXA_BENCH_BROWSER, headless: true, args: ['--host-resolver-rules=MAP texa.test 127.0.0.1', '--no-proxy-server'] });
  for (let n = 0; n < Number(process.env.TEXA_BENCH_RUNS || 5); n++) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    page.on('pageerror', e => results.errors.push(e.message));
    await page.addInitScript(() => {
      // Fixed scope avoids measuring a race between first-run auto-selection and
      // the automation's history click. Restore the same synthetic Session next.
      localStorage.setItem('kaoyan_subject', 'S2 fixture unclassified');
      window.__longTasks = [];
      new PerformanceObserver(list => window.__longTasks.push(...list.getEntries().map(e => e.duration))).observe({ type: 'longtask', buffered: true });
      document.addEventListener('click', event => {
        if (event.target.closest('.context-session-row')) window.__sessionClick = performance.now();
      }, true);
    });
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 625000, uploadThroughput: 125000 });
    await page.goto('https://texa.test:18429', { waitUntil: 'domcontentloaded' });
    await page.locator('.composer-textarea').waitFor();
    await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    await page.locator('.context-session-row').first().click();
    await page.locator('[data-message-id="fixture-message-0"]').waitFor();
    // A mounted message can still contain the lazy Markdown fallback.
    await page.waitForFunction(() => document.querySelectorAll('.markdown-body').length >= 100);
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    results.cold.push(await page.evaluate(() => ({
      canvasMs: performance.now(), font: getComputedStyle(document.body).fontFamily,
      paint: performance.getEntriesByType('paint').map(e => ({ name: e.name, startTime: e.startTime })),
      longTasks: window.__longTasks,
      resources: performance.getEntriesByType('resource').map(e => ({ name: new URL(e.name).pathname, requestStart: e.requestStart, responseStart: e.responseStart, responseEnd: e.responseEnd, ttfbMs: e.responseStart - e.requestStart, transferMs: e.responseEnd - e.responseStart, encodedBytes: e.encodedBodySize, wireBytes: e.transferSize, appHeaderMs: e.serverTiming.find(t => t.name === 'texa_read')?.duration ?? null })),
    })));
    for (let w = 0; w < 4; w++) {
      await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
      const index = w % 2 ? 0 : 1;
      await page.locator('.context-session-row').nth(index).click();
      await page.locator('.context-sidebar-scrim').waitFor({ state: 'hidden' });
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      results.warm.push(await page.evaluate(() => {
        const end = performance.now();
        const resource = performance.getEntriesByType('resource').filter(e => /\/api\/chat\/conversations\/visual-session-\d+$/.test(new URL(e.name).pathname)).at(-1);
        return { clickToReadableMs: end - window.__sessionClick, requestToBodyMs: resource.responseEnd - resource.requestStart, bodyToReadableMs: end - resource.responseEnd, appHeaderMs: resource.serverTiming.find(t => t.name === 'texa_read')?.duration ?? null, encodedBytes: resource.encodedBodySize };
      }));
    }
    if (n === Number(process.env.TEXA_BENCH_RUNS || 5) - 1) {
      await page.locator('.composer-textarea').fill('S2 fixture question');
      await page.getByRole('button', { name: '发送问题', exact: true }).click();
      await page.getByText('保留片段1。', { exact: false }).last().waitFor();
      const top = await page.evaluate(() => { const el = document.querySelector('.learning-workspace-scroll'); el.scrollTop = 120; el.dispatchEvent(new Event('scroll')); return el.scrollTop; });
      await page.waitForTimeout(4000);
      results.stream = await page.evaluate(initialTop => ({ initialTop, finalTop: document.querySelector('.learning-workspace-scroll').scrollTop, partialVisible: document.body.innerText.includes('保留片段20'), errorVisible: document.body.innerText.includes('这次回答没有完成') }), top);
      const beforeSource = await page.evaluate(() => document.querySelector('.learning-workspace-scroll').scrollTop);
      await page.getByRole('button', { name: '查看来源 · 3', exact: true }).first().evaluate(el => el.click());
      await page.getByRole('button', { name: '关闭详情面板', exact: true }).click();
      results.sourceReturn = { beforeTop: beforeSource, afterTop: await page.evaluate(() => document.querySelector('.learning-workspace-scroll').scrollTop) };
      await page.screenshot({ path: resolve(dirname(output), 'phone-reading.png') });
      results.layouts = [];
      for (const width of [375, 390, 430, 760, 1024, 1280]) {
        await page.setViewportSize({ width, height: width > 760 ? 820 : 844 });
        await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
        results.layouts.push(await page.evaluate(() => ({ width: innerWidth, bodyWidth: document.body.scrollWidth,
          inputFontPx: getComputedStyle(document.querySelector('.composer-textarea')).fontSize,
          scopeVisible: document.querySelector('.learning-header-scope-selector').getBoundingClientRect().height > 0,
          controls: [...document.querySelectorAll('.composer-tools button, .composer-send')].filter(el => el.getBoundingClientRect().height > 0).map(el => ({ label: el.getAttribute('aria-label') || el.title, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })),
        })));
        await page.screenshot({ path: resolve(dirname(output), `reading-${width}.png`) });
      }
      if (process.env.TEXA_BENCH_DIAGNOSTICS === '1') {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('https://texa.test:18429/?texa_perf=1', { waitUntil: 'domcontentloaded' });
        await page.locator('.composer-textarea').waitFor();
        await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
        await page.locator('.context-session-row').first().click();
        await page.waitForFunction(() => document.querySelectorAll('.markdown-body').length >= 100);
        await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
        await page.locator('.composer-textarea').fill('S2 diagnostic fixture');
        await page.getByRole('button', { name: '发送问题', exact: true }).click();
        await page.getByText('回答尚未完成', { exact: false }).last().waitFor();
        const downloadPromise = page.waitForEvent('download');
        await page.getByRole('button', { name: '导出仅含耗时与尺寸的性能记录', exact: true }).click();
        const download = await downloadPromise;
        const target = resolve(dirname(output), 'diagnostics.json');
        await download.saveAs(target);
        const exported = readFileSync(target, 'utf8');
        results.diagnostics = { validJson: Boolean(JSON.parse(exported).resources), schema: JSON.parse(exported).schema, metricKinds: [...new Set((JSON.parse(exported).metrics || []).map(m => m.kind))], privatePathsAbsent: !/\/api\/|visual-session|fixture-message|kaoyan_api_token/.test(exported) };
      }
    }
    await context.close();
  }
  if (process.env.TEXA_BENCH_ELECTRON === '1') {
    const localServer = createHttpServer(handler);
    await new Promise(r => localServer.listen(18439, '127.0.0.1', r));
    const userData = resolve(certDir, 'electron-data');
    mkdirSync(userData, { recursive: true });
    writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
    let electron;
    try {
      electron = await _electron.launch({ executablePath: process.env.TEXA_BENCH_ELECTRON_PATH,
        args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18439', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18439' },
      });
      const page = await electron.firstWindow();
      await page.locator('.composer-textarea').waitFor({ timeout: 30000 });
      await page.locator('.context-session-row').first().click();
      await page.locator('[data-message-id="fixture-message-0"]').waitFor();
      await page.waitForFunction(() => document.querySelectorAll('.markdown-body').length >= 100);
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      results.electron = await page.evaluate(() => ({ isElectron: window.kaoyanDesktop?.isElectron, font: getComputedStyle(document.body).fontFamily, messageCount: document.querySelectorAll('[data-message-id]').length, renderedMarkdownCount: document.querySelectorAll('.markdown-body').length, renderedMathCount: document.querySelectorAll('.katex').length, bodyWidth: document.body.scrollWidth, viewport: innerWidth }));
      const beforeStreams = streamRequests;
      const beforeBooks = bookRequests;
      await page.locator('.composer-textarea').fill('输入法验收夹具');
      await page.locator('.composer-textarea').evaluate(el => {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 229, bubbles: true }));
        window.dispatchEvent(new Event('books:changed'));
      });
      await page.waitForTimeout(250);
      results.electron.imeSubmissions = streamRequests - beforeStreams;
      results.electron.bookReadsOnInvalidation = bookRequests - beforeBooks;
      await page.screenshot({ path: resolve(dirname(output), 'electron-reading.png') });
    } finally { await electron?.close(); localServer.close(); }
  }
} finally {
  await browser?.close(); server.close(); child.kill();
  mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(results, null, 2));
}
console.log(JSON.stringify({ coldCanvasMs: results.cold.map(r => r.canvasMs), warmMs: results.warm.map(r => r.clickToReadableMs), stream: results.stream, errors: results.errors }));
