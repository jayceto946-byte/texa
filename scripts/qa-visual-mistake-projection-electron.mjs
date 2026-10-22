/** Offline OCR response fixture -> real Electron production renderer.
 * NODE_PATH=<Playwright packages> node scripts/qa-visual-mistake-projection-electron.mjs
 * No model requests, production storage or record mutations.
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { extname, resolve } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const out = resolve('docs/qa/visual-mistake-projection-2026-10-21');
mkdirSync(out, { recursive: true });
const fixture = JSON.parse(readFileSync(process.env.TEXA_VISUAL_FIXTURE || resolve(out, 'fixture.json')));
const base = { user_answer: '不会做', correct_answer: '', explanation: '', source: '学习会话', subject: '数学/高数', tags: [], mistake_type: [], difficulty: 3, created_at: '2026-10-21T08:00:00Z', revision: 1, content_revision: 1, content_status: 'ready', diagnosis_status: 'missing', visibility: 'active', attachments: [] };
const legacy = { ...base, id: 'legacy', question_text: fixture.raw };
const clean = { ...base, id: 'clean', question_text: fixture.question, visual_ir: fixture.ir };
const draft = { ...legacy, id: 'legacy-draft', content_complete: false, updated_at: base.created_at };
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18159' }, stdio: 'ignore' });
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path === '/api/focus') return reply({ revision: 0, tasks: [], total: 0, next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', remaining_seconds: 0, active_ms: 0, server_time: Date.now() / 1000 });
    if (path === '/api/chat/conversations') return reply({ items: [], next_cursor: null });
    if (path === '/api/mistakes/query') return reply({ items: [legacy, clean], next_cursor: null });
    if (path === '/api/mistakes/candidates') return reply([]);
    if (path === '/api/mistakes/drafts') return reply([draft]);
    if (path === '/api/mistakes/drafts/legacy-draft') return reply(draft);
    if (path === '/api/mistakes/legacy') return reply(legacy);
    if (path === '/api/mistakes/clean') return reply(clean);
    if (path.startsWith('/api/') || path === '/health') {
      const response = await fetch('http://127.0.0.1:18159' + req.url);
      res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return;
    }
    const file = resolve('frontend/dist', extname(path) ? '.' + path : 'index.html');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream');
    res.end(readFileSync(file));
  } catch (e) { res.writeHead(500); res.end(String(e)); }
});
let app, page;
const result = { platform: 'macOS, real Electron production renderer, isolated API fixtures', checks: [], errors: [] };
function check(ok, name) { result.checks.push({ name, pass: !!ok }); if (!ok) throw Error(name); }
async function go(path) { await page.goto('http://127.0.0.1:18158' + path); await page.locator('.app-shell').waitFor(); await page.evaluate(() => document.fonts.ready); }
async function noMetadata(name) {
  const text = await page.locator('.persistent-route-panel:not([hidden])').innerText();
  check(!/schema_version|visual_summary|entities|properties|MATH_PROTECTED|题干上方左侧/.test(text), name + ': internal metadata hidden');
  check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), name + ': no horizontal overflow');
}
try {
  await new Promise(r => server.listen(18158, '127.0.0.1', r));
  for (let i = 0; i < 30; i++) { try { await fetch('http://127.0.0.1:18159/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const userData = '/private/tmp/texa-visual-mistake-' + Date.now(); mkdirSync(userData); writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: process.env.TEXA_QA_ELECTRON || resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18158', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18158' } });
  page = await app.firstWindow(); page.setDefaultTimeout(12000); page.on('pageerror', e => result.errors.push(String(e))); page.on('dialog', dialog => { void dialog.accept().catch(() => {}); }); await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.locator('.app-shell').waitFor();
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [width, height]);
    for (const id of ['legacy', 'clean']) {
      await go('/mistakes/' + id); await page.locator('.reading-markdown .katex').first().waitFor(); await noMetadata(`${width}-${id}`);
      check(await page.locator('.reading-markdown .katex-error').count() === 0, `${width}-${id}: valid math rendering`);
      check((await page.locator('.reading-markdown').first().innerText()).includes('[37]'), `${width}-${id}: original question retained`);
      await page.screenshot({ path: resolve(out, `${width}-${id}.png`), scale: 'css', animations: 'disabled' });
    }
  }
  await go('/mistakes/legacy'); await page.getByRole('button', { name: '编辑档案', exact: true }).click();
  check(await page.getByRole('textbox', { name: '题目', exact: true }).inputValue() === fixture.question, 'legacy record editor receives full corrected projection');
  await page.getByRole('button', { name: '取消编辑', exact: true }).click();
  await page.getByRole('heading', { name: '错题详情', exact: true }).waitFor();
  await go('/mistakes/intake/legacy-draft'); await page.getByRole('textbox', { name: '题干与公式', exact: true }).waitFor();
  check(await page.getByRole('textbox', { name: '题干与公式', exact: true }).inputValue() === fixture.question, 'legacy draft editor hides IR but preserves full question');
  await go('/mistakes'); await page.locator('.mistakes-row-title').first().waitFor(); await noMetadata('collection');
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (e) { result.errors.push(String(e)); process.exitCode = 1; await page?.screenshot({ path: resolve(out, 'failure.png') }).catch(() => {}); }
finally { writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); console.log(JSON.stringify(result)); }
