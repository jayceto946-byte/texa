/** Actual crop/composer -> FastAPI/SSE -> DeepSeek SDK mock -> persisted image. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { Readable } from 'node:stream';
import { mkdirSync, readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const require = createRequire(import.meta.url);
const { _electron } = require(process.env.TEXA_QA_PLAYWRIGHT);
const out = resolve('docs/qa/visual-provider-crop-2026-10-23');
const temp = mkdtempSync('/private/tmp/texa-provider-crop-');
writeFileSync(resolve(temp, 'empty.env'), '');
mkdirSync(resolve(temp, 'electron'));
writeFileSync(resolve(temp, 'electron/setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
const apiPort = 18277, uiPort = 18278, fixturePort = 18279;
const logs = [];
const requests = [];
const api = spawn(resolve('venv310/bin/python'), [resolve(out, 'server.py')], { env: { ...process.env,
  PYTHONPATH: process.cwd(), ENV_PATH: resolve(temp, 'empty.env'), DATA_DIR: resolve(temp, 'data'),
  TEXA_QA_API_PORT: String(apiPort), KAOYAN_TRUSTED_ORIGINS: `http://127.0.0.1:${uiPort}`,
}, stdio: ['ignore', 'pipe', 'pipe'] });
api.stdout.on('data', data => logs.push(data.toString())); api.stderr.on('data', data => logs.push(data.toString()));
const fixture = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: String(fixturePort) }, stdio: 'ignore' });
const result = { platform: 'real macOS Electron; real crop UI and isolated FastAPI; fake DeepSeek HTTP responses; no paid calls', checks: [], errors: [] };
const check = (ok, name) => { result.checks.push({ name, pass: !!ok }); if (!ok) throw Error(name); };
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path === '/api/system/settings/subjects') return reply([{ name: '数学', children: ['高数'] }]);
    if (path === '/api/mistakes/chat-sources/query') return reply([]);
    if (path === '/api/focus') return reply({ revision: 0, tasks: [], total: 0, next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', remaining_seconds: 0, active_ms: 0, server_time: Date.now() / 1000 });
    if (path.startsWith('/api/') || path === '/health') {
      const real = path.startsWith('/api/mistakes/solve-image-stream') || path.startsWith('/api/mistakes/tasks/') || path.startsWith('/api/chat/') || path.startsWith('/api/qa/');
      const target = `http://127.0.0.1:${real ? apiPort : fixturePort}${req.url}`;
      const headers = { ...req.headers }; delete headers.host;
      const upstream = await fetch(target, { method: req.method, headers, ...(req.method !== 'GET' && req.method !== 'HEAD' ? { body: req, duplex: 'half' } : {}) });
      requests.push({ path: req.url, method: req.method, status: upstream.status });
      if (upstream.status >= 400) { const body = await upstream.text(); logs.push(`${req.url}: ${upstream.status} ${body}\n`); res.writeHead(upstream.status, { 'Content-Type': 'application/json' }); res.end(body); return; }
      res.writeHead(upstream.status, { 'Content-Type': upstream.headers.get('content-type') || 'application/json', 'Cache-Control': 'no-store' });
      Readable.fromWeb(upstream.body).pipe(res); return;
    }
    const file = resolve('/private/tmp/texa-photo-provider-frontend', extname(path) ? '.' + path : 'index.html');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream');
    res.end(readFileSync(file));
  } catch (error) { logs.push(`proxy error ${req.url}: ${String(error)}\n`); res.writeHead(500); res.end(String(error)); }
});
let app, page;
async function state() { const response = await fetch(`http://127.0.0.1:${apiPort}/api/qa/state`); const value = await response.json(); if (!response.ok || !value.vision_sizes) throw Error('fixture state unavailable'); return value; }
async function imageSize(selector) { return page.locator(selector).evaluate(img => [img.naturalWidth, img.naturalHeight]); }
try {
  await new Promise(r => server.listen(uiPort, '127.0.0.1', r));
  let ready = false;
  for (let i = 0; i < 100; i++) { try { await state(); ready = true; break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  check(ready, 'isolated API ready');
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env,
    KAOYAN_USER_DATA_DIR: resolve(temp, 'electron'), KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: `http://127.0.0.1:${uiPort}`, KAOYAN_FRONTEND_DEV_URL: `http://127.0.0.1:${uiPort}`,
  } });
  page = await app.firstWindow(); page.setDefaultTimeout(15000);
  page.on('pageerror', error => result.errors.push(String(error)));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.locator('.app-shell').waitFor();
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [width, height]);
    await page.goto(`http://127.0.0.1:${uiPort}/`); await page.locator('.app-shell').waitFor();
    if (width === 760 && await page.getByRole('button', { name: '收起侧栏', exact: true }).isVisible()) await page.getByRole('button', { name: '收起侧栏', exact: true }).click();
    await fetch(`http://127.0.0.1:${apiPort}/api/qa/mode/recover`, { method: 'POST' });
    await page.locator('input[type=file][accept="image/png,image/jpeg,image/webp,image/bmp"]').first().setInputFiles(resolve(out, 'fixture.png'));
    const source = page.getByAltText('待处理原图'); await source.waitFor();
    const box = await source.boundingBox();
    await page.locator('.problem-image-dialog .cursor-move > .bottom-0.right-0').hover(); await page.mouse.down();
    await page.mouse.move(box.x + box.width * .55, box.y + box.height * .65, { steps: 10 }); await page.mouse.up();
    await page.getByRole('button', { name: '应用裁剪', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(out, `${width}-crop.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '应用裁剪', exact: true }).click();
    await page.getByAltText('待解析的题目附件').waitFor();
    await page.locator('.composer-textarea').fill('请完整讲解裁剪区域中的题目');
    await page.getByRole('button', { name: '发送问题', exact: true }).click();
    await page.getByText('恢复后的完整讲解。', { exact: false }).last().waitFor();
    const thumb = '.is-visual-question .question-image-thumbnail img';
    await page.waitForFunction(sel => document.querySelector(sel)?.naturalWidth > 0, thumb);
    const size = await imageSize(thumb); const observed = await state();
    check(size[0] < 600 && size[1] < 360, `${width} crop actually changes dimensions`);
    check(JSON.stringify(size) === JSON.stringify(observed.vision_sizes.at(-1)), `${width} displayed crop equals vision input`);
    check(observed.attempts === 2, `${width} transient 503 recovers once through SDK and SSE`);
    await page.getByRole('button', { name: '查看题目图片原图', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.question-image-original img')?.naturalWidth > 0);
    check(JSON.stringify(await imageSize('.question-image-original img')) === JSON.stringify(size), `${width} enlarged picture uses crop`);
    await page.keyboard.press('Escape');
    await page.goto(`http://127.0.0.1:${uiPort}/?conversation_id=${encodeURIComponent(observed.conversation_id)}`);
    await page.reload(); await page.waitForFunction(sel => document.querySelector(sel)?.naturalWidth > 0, thumb);
    await page.getByText('恢复后的完整讲解。', { exact: false }).last().waitFor();
    await page.waitForFunction(() => document.querySelector('.learning-question > .markdown-body')?.textContent.includes('请完整讲解裁剪区域中的题目'));
    check(JSON.stringify(await imageSize(thumb)) === JSON.stringify(size), `${width} persisted conversation keeps crop after reload`);
    check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${width} no horizontal overflow`);
    await page.screenshot({ path: resolve(out, `${width}-chat.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await fetch(`http://127.0.0.1:${apiPort}/api/qa/mode/payment`, { method: 'POST' });
    await page.locator('input[type=file][accept="image/png,image/jpeg,image/webp,image/bmp"]').first().setInputFiles(resolve(out, 'fixture.png'));
    await page.getByRole('button', { name: '应用裁剪', exact: true }).click();
    await page.getByAltText('待解析的题目附件').waitFor();
    await page.locator('.composer-textarea').fill('检查模型错误提示');
    await page.getByRole('button', { name: '发送问题', exact: true }).click();
    await page.getByText('这次回答没有完成', { exact: true }).waitFor();
    await page.locator('details').evaluateAll(nodes => nodes.forEach(el => { el.open = true; }));
    await page.getByText('模型服务账户余额或额度不足（HTTP 402）', { exact: false }).last().waitFor();
    check((await state()).attempts === 1, `${width} payment failure makes one request`);
    check(!(await page.locator('body').innerText()).includes('PRIVATE_PROVIDER_BODY'), `${width} private provider body stays hidden`);
    await page.waitForFunction(sel => document.querySelector(sel)?.naturalWidth > 0, thumb);
    check((await imageSize(thumb))[0] > 0, `${width} picture retained on provider error`);
    await page.screenshot({ path: resolve(out, `${width}-error.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '新对话', exact: true }).click();
  }
  check(result.errors.length === 0, 'no renderer errors');
} catch (error) { result.errors.push(String(error)); process.exitCode = 1; await page?.locator('details').evaluateAll(nodes => nodes.forEach(el => { el.open = true; })).catch(() => {}); await page?.screenshot({ path: resolve(out, 'failure.png') }).catch(() => {}); if (page) writeFileSync(resolve(out, 'failure.txt'), await page.locator('body').innerText()); }
finally {
  writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(out, 'backend.log'), logs.join(''));
  writeFileSync(resolve(out, 'requests.json'), JSON.stringify(requests, null, 2));
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {});
  api.kill(); fixture.kill(); server.close(); console.log(JSON.stringify(result));
}
