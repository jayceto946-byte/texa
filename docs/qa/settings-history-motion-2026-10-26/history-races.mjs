/** Audit race witness and renderer baseline. In-memory API fixtures, no model or user DB. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname, join } from 'node:path';
import { tmpdir } from 'node:os';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'after';
const build = resolve(process.argv[3] || '/private/tmp/texa-audit-build-before');
const out = resolve('docs/qa/settings-history-motion-2026-10-26/races');
mkdirSync(out, { recursive: true });
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18193' }, stdio: 'ignore' });
const messages = id => [{ id: `${id}-q`, role: 'user', content: `会话${id}问题：求导数` }, { id: `${id}-a`, role: 'assistant', content: `会话${id}答案：$f(x)=x^2$，所以 $f'(x)=2x$。` }];
const history = { has_more: true, next_before_seq: 30, limit: 40, total: 42 };
let pending = null;
const requests = [];
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path.startsWith('/api/')) requests.push({ path, method: req.method });
    if (path === '/api/books/list') return reply([]);
    if (path === '/api/chat/conversations') return reply({ items: ['A', 'B'].map(id => ({ id, title: `会话${id}`, subject: '数学', book_name: '', management: { state: 'active', pinned: false, revision: 1 } })), next_cursor: null, has_more: false });
    if (/^\/api\/chat\/conversations\/[AB]$/.test(path)) { const id = path.at(-1); return reply({ id, subject: '数学', book_name: '', messages: messages(id), page: id === 'A' ? history : { ...history, has_more: false, total: 2 } }); }
    if (/^\/api\/chat\/conversations\/A\/messages\/[ab]\/context$/.test(path)) return reply({ conversation_id: 'A', subject: '数学', book_name: '', messages: messages('A'), page: { ...history, next_after_seq: 32 } });
    if (path === '/api/chat/conversations/A/messages' || path === '/api/chat/conversations/A/messages-after') { pending = () => reply({ messages: [...messages('A'), { id: 'late-A', role: 'assistant', content: '迟到A消息，不应出现在B' }], page: { ...history, has_more: false }, has_more: false, next_after_seq: null }); return; }
    if (path.endsWith('/management')) return reply({ state: 'active', pinned: false, revision: 1 });
    if (path === '/api/focus') return reply({ revision: 0, runtime_id: 'qa', snapshot_sequence: 1, tasks: [], next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', active_ms: 0, remaining_seconds: null, server_time: Date.now() / 1000 });
    if (path.startsWith('/api/') || path === '/health') {
      const response = await fetch('http://127.0.0.1:18193' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return;
    }
    const file = resolve(build, extname(path) ? '.' + path : 'index.html');
    if (!file.startsWith(build + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500).end(String(error)); }
});
let app, page;
const result = { phase, environment: 'macOS actual Electron; production renderer, in-memory HTTP fixtures; no model/backend timing', checks: [], races: [], errors: [], reload_ms: [], navigation_ms: [] };
const check = (name, pass) => { result.checks.push({ name, pass: !!pass }); if (!pass) throw Error(name); };
async function switchTo(id, locator = '') {
  await page.evaluate(url => { history.pushState({}, '', url); dispatchEvent(new PopStateEvent('popstate')); }, `/?conversation_id=${id}${locator}`);
  await page.getByText(`会话${id}问题：求导数`, { exact: true }).waitFor();
}
async function waitPending() { for (let n = 0; n < 100 && !pending; n++) await new Promise(r => setTimeout(r, 20)); if (!pending) throw Error('pagination request not observed'); }
try {
  await new Promise(r => server.listen(18192, '127.0.0.1', r));
  for (let n = 0; n < 50; n++) { try { await fetch('http://127.0.0.1:18193/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const profile = mkdtempSync(join(tmpdir(), 'texa-audit-electron-'));
  writeFileSync(join(profile, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  const started = performance.now();
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: profile, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18192', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18192' } });
  page = await app.firstWindow(); page.setDefaultTimeout(10000); page.on('pageerror', error => result.errors.push(String(error)));
  await page.locator('.composer-textarea').waitFor(); result.launch_to_composer_ms = performance.now() - started;
  for (let n = 0; n < 5; n++) { const at = performance.now(); await page.reload(); await page.locator('.composer-textarea').waitFor(); result.reload_ms.push(performance.now() - at); }
  for (const direction of ['earlier', 'later']) {
    await page.goto('http://127.0.0.1:18192/?conversation_id=A' + (direction === 'later' ? '&message_id=a' : ''));
    await page.getByText('会话A问题：求导数', { exact: true }).waitFor();
    await page.getByRole('button', { name: direction === 'earlier' ? /加载更早消息/ : '加载后续消息' }).click();
    await waitPending(); await switchTo('B'); pending(); pending = null;
    await page.waitForTimeout(250);
    const contaminated = await page.getByText('迟到A消息，不应出现在B', { exact: true }).count() > 0;
    const switchedBack = await page.evaluate(() => localStorage.getItem('kaoyan_conversation_id')) === 'A';
    result.races.push({ direction, contaminated, switchedBack });
    check(`${direction}: ${phase === 'before' ? 'race reproduced' : 'late response ignored'}`, phase === 'before' ? contaminated : !contaminated && !switchedBack);
  }
  await page.goto('http://127.0.0.1:18192/?conversation_id=B'); await page.getByText('会话B问题：求导数', { exact: true }).waitFor();
  result.memory_before = await app.evaluate(({ app }) => app.getAppMetrics().map(({ type, memory, cpu }) => ({ type, memory, cpu })));
  for (let n = 0; n < 20; n++) { const at = performance.now(); await switchTo(n % 2 ? 'B' : 'A'); result.navigation_ms.push(performance.now() - at); }
  result.memory_after = await app.evaluate(({ app }) => app.getAppMetrics().map(({ type, memory, cpu }) => ({ type, memory, cpu })));
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [width, height]);
    await page.waitForFunction(expected => innerWidth === expected, width);
    // Freeze responsive sidebar transitions so screenshots show the settled UI.
    await page.screenshot({ path: join(out, `${width}.png`), animations: 'disabled' });
    check(`${width}: formulas rendered`, await page.locator('.katex').count() > 0);
    check(`${width}: no horizontal overflow`, await page.evaluate(() => document.body.scrollWidth <= innerWidth));
  }
  if (phase !== 'before') {
    for (const direction of ['earlier', 'later']) {
      await page.goto('http://127.0.0.1:18192/?conversation_id=A&message_id=a');
      await page.getByText('会话A问题：求导数', { exact: true }).waitFor();
      await page.getByRole('button', { name: direction === 'earlier' ? /加载更早消息/ : '加载后续消息' }).click();
      await waitPending(); pending(); pending = null;
      await page.getByText('迟到A消息，不应出现在B', { exact: true }).waitFor();
      check(`${direction}: current page appends without duplicates`, await page.getByText('会话A问题：求导数', { exact: true }).count() === 1);
    }
    await page.goto('http://127.0.0.1:18192/?conversation_id=A&message_id=a');
    await page.getByText('会话A问题：求导数', { exact: true }).waitFor();
    await page.getByRole('button', { name: /加载更早消息/ }).click(); await waitPending();
    const replaced = page.waitForResponse(response => response.url().endsWith('/messages/b/context'));
    await switchTo('A', '&message_id=b'); await replaced; await page.waitForTimeout(100);
    pending(); pending = null; await page.waitForTimeout(150);
    check('replacing same conversation invalidates previous page read', await page.getByText('迟到A消息，不应出现在B', { exact: true }).count() === 0);
  }
  check('no renderer exceptions', result.errors.length === 0);
} catch (error) { result.errors.push(String(error)); process.exitCode = 1; await page?.screenshot({ path: join(out, 'failure.png') }).catch(() => {}); }
finally {
  writeFileSync(join(out, 'results.json'), JSON.stringify(result, null, 2));
  writeFileSync(join(out, 'requests.json'), JSON.stringify(requests, null, 2));
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {});
  server.closeAllConnections(); server.close(); upstream.kill(); console.log(JSON.stringify(result));
}
