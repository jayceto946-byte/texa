/** Isolated Electron QA: category writes affect only this in-memory fixture. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname, join } from 'node:path';
import { tmpdir } from 'node:os';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'after', out = resolve('docs/qa/library-context-logo-2026-10-23', phase); mkdirSync(out, { recursive: true });
const initial = [{ name: '数学', children: ['高数', '线代'] }, { name: '英语', children: ['阅读'] }, { name: '政治', children: [] }, { name: '专业课', children: ['数据结构'] }];
let subjects = structuredClone(initial);
const book = { name: '数据结构教材', book_id: 'qa-book', display_name: '数据结构教材', subject: '专业课/数据结构', lifecycle_status: 'active', has_pdf: false, chapter_count: 1, book_role: 'core', readiness: { technical: { status: 'ready', chunk_count: 12 }, canonical: { status: 'ready' } } };
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18189' }, stdio: 'ignore' });
const requests = [];
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path.startsWith('/api/')) requests.push({ path, method: req.method });
    if (path === '/api/books/list') return reply([book]);
    if (path === '/api/system/settings/subjects') {
      if (req.method === 'POST') { const chunks = []; for await (const chunk of req) chunks.push(chunk); subjects = JSON.parse(Buffer.concat(chunks).toString()).subjects; }
      return reply(subjects);
    }
    if (path === '/api/system/settings') { const r = await fetch('http://127.0.0.1:18189' + req.url); const data = (await r.json()).data; return reply({ ...data, subjects }); }
    if (path === '/api/chat/conversations') return reply({ items: [{ id: 'qa-logo', title: '解释一下多重积分', subject: '数学', book_name: '', management: { state: 'active', pinned: false, revision: 1 } }], next_cursor: null, has_more: false });
    if (path === '/api/chat/conversations/qa-logo') return reply({ id: 'qa-logo', subject: '数学', book_name: '', messages: [{ id: 'qa-q', role: 'user', content: '解释一下多重积分' }, { id: 'qa-a', role: 'assistant', content: '先确定区域，再选择积分次序。' }], page: { limit: 40, total: 2, has_more: false } });
    if (path.endsWith('/management')) return reply({ state: 'active', pinned: false, revision: 1 });
    if (path === '/api/focus') return reply({ revision: 0, runtime_id: 'qa', snapshot_sequence: 1, tasks: [], next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', active_ms: 0, remaining_seconds: null, server_time: Date.now() / 1000 });
    if (path.startsWith('/api/') || path === '/health') { const r = await fetch('http://127.0.0.1:18189' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) }); res.writeHead(r.status, { 'Content-Type': 'application/json' }); res.end(await r.text()); return; }
    const file = resolve('frontend/dist', extname(path) ? '.' + path : 'index.html');
    if (!file.startsWith(resolve('frontend/dist') + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (e) { res.writeHead(500).end(String(e)); }
});
let app, page;
const result = { phase, platform: 'macOS real Electron, production renderer, isolated fixtures; Windows untested', checks: [], colors: [], errors: [] };
const check = (pass, name) => { result.checks.push({ name, pass: !!pass }); if (!pass) throw Error(name); };
const shot = name => page.screenshot({ path: resolve(out, name + '.png'), animations: 'disabled', scale: 'css' });
async function go(path) { await page.goto('http://127.0.0.1:18188' + path); await page.locator('.app-shell').waitFor(); await page.evaluate(() => document.fonts.ready); }
async function books() { await go('/books'); await page.locator('.library-tree-item').first().waitFor(); }
async function treeMenu(row) { await row.click({ button: 'right' }); await page.getByRole('menu', { name: /管理/ }).waitFor(); }
try {
  await new Promise(r => server.listen(18188, '127.0.0.1', r));
  for (let n = 0; n < 40; n++) { try { await fetch('http://127.0.0.1:18189/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const userData = mkdtempSync(join(tmpdir(), 'texa-library-context-')); writeFileSync(join(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18188', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18188' } });
  page = await app.firstWindow(); page.setDefaultTimeout(10000); page.on('pageerror', e => result.errors.push(String(e))); await page.locator('.app-shell').waitFor(); await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const [w, h] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [w, h]);
    await books(); await shot(w + '-books');
    if (phase === 'before') continue;
    check(await page.locator('.library-tree-heading,.library-category-actions').count() === 0, w + ' classification heading and overflow removed');
    const rows = page.locator('.library-tree-item');
    check(await page.locator('.library-tree').evaluate(el => {
      const button = el.querySelector('.library-category-add'), row = el.querySelector('.library-tree-item');
      return Math.abs(button.getBoundingClientRect().height - row.getBoundingClientRect().height) < 1 && getComputedStyle(button).fontSize === getComputedStyle(row).fontSize;
    }), w + ' add controls match subject row height and type size');
    await rows.nth(3).click(); await treeMenu(rows.nth(0));
    check(await page.getByRole('menu', { name: '数学管理', exact: true }).isVisible(), w + ' right click targets unselected subject');
    check(await page.getByRole('menu').evaluate(el => { const r = el.getBoundingClientRect(); return r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; }), w + ' context menu within viewport');
    await shot(w + '-menu'); await page.keyboard.press('Escape');
    check(await rows.nth(0).evaluate(el => document.activeElement === el), w + ' Escape restores row focus');
    await rows.nth(0).click();
    const child = page.locator('.library-tree-child').filter({ hasText: '高数' }); await child.focus(); await page.keyboard.press('Shift+F10');
    check(await page.getByRole('menu', { name: '高数管理', exact: true }).isVisible(), w + ' keyboard opens child context menu');
    await page.getByRole('menuitem', { name: '重命名', exact: true }).click();
    await page.getByRole('textbox', { name: '科目名称', exact: true }).fill('微积分'); await page.keyboard.press('Enter');
    check(await page.locator('.library-tree-child').filter({ hasText: '微积分' }).count() === 1, w + ' rename applies to intended child');
    await page.locator('.library-tree-parent').nth(1).locator('.library-tree-disclosure').click();
    await treeMenu(page.locator('.library-tree-child').filter({ hasText: '阅读' }));
    page.once('dialog', dialog => dialog.accept()); await page.getByRole('menuitem', { name: '删除科目', exact: true }).click();
    check(await page.locator('.library-tree-child').filter({ hasText: '阅读' }).count() === 0 && await page.locator('.library-tree-child').filter({ hasText: '微积分' }).count() === 1, w + ' deleting child targets its own parent while another subject is selected');
    await treeMenu(rows.nth(3)); check(await page.getByRole('menuitem', { name: '删除学科', exact: true }).isDisabled(), w + ' populated subject deletion remains blocked'); await page.keyboard.press('Escape');
    await treeMenu(rows.nth(2));
    page.once('dialog', dialog => dialog.accept()); await page.getByRole('menuitem', { name: '删除学科', exact: true }).click();
    check(await page.locator('.library-tree-item').filter({ hasText: '政治' }).count() === 0, w + ' deletion targets the right-clicked subject');
    await page.getByRole('button', { name: '添加学科', exact: true }).click();
    check(await page.locator('.library-tree-item').filter({ hasText: '新学科' }).count() === 1, w + ' styled add subject works');
    await page.getByRole('button', { name: '添加科目', exact: true }).click();
    check(await page.locator('.library-tree-child').filter({ hasText: '新科目' }).count() === 1, w + ' styled add child works');
    check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), w + ' page has no horizontal overflow');
    await go('/?conversation_id=qa-logo'); await page.locator('.learning-question .markdown-body').waitFor();
    await page.locator('.composer-textarea').fill('尚未发送的草稿');
    if (w === 1280) { await page.getByRole('link', { name: '教材', exact: true }).click(); await page.locator('.library-tree').waitFor(); }
    if (!await page.getByRole('link', { name: 'Texa 学习工作区', exact: true }).isVisible()) await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    await page.getByRole('link', { name: 'Texa 学习工作区', exact: true }).click();
    await page.locator('.learning-workspace-shell[data-empty="true"]').waitFor();
    check(await page.locator('.composer-textarea').inputValue() === '', w + ' logo clears draft and returns to start page');
    check(new URL(page.url()).search === '', w + ' logo removes old conversation locator');
    await shot(w + '-home');
  }
  if (phase !== 'before') {
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820));
    for (const theme of ['mineral', 'graphite', 'clay', 'notebook', 'codex']) {
      await page.evaluate(theme => localStorage.setItem('texa_appearance_theme', theme), theme); await books();
      await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme);
      const colors = await page.locator('.study-classification-tools button').first().evaluate(el => ({ background: getComputedStyle(el).backgroundColor, border: getComputedStyle(el).borderTopColor, dock: getComputedStyle(el.closest('.library-tree')).backgroundColor, color: getComputedStyle(el).color }));
      result.colors.push({ theme, ...colors });
      check(colors.background === 'rgba(0, 0, 0, 0)', theme + ' add control has a transparent surface');
      const geometry = await page.locator('.study-classification-tools').evaluate(el => {
        const buttons = [...el.querySelectorAll('button')]; const [a, b] = buttons.map(b => b.getBoundingClientRect()); const group = el.getBoundingClientRect(); const style = getComputedStyle(buttons[0]);
        return { centered: Math.abs((a.left + b.right) / 2 - (group.left + group.right) / 2) < 1, gap: b.left - a.right, height: a.height, font: parseFloat(style.fontSize), icon: buttons[0].querySelector('svg').getBoundingClientRect().width, border: style.borderTopWidth };
      });
      check(geometry.centered && geometry.gap >= 12, theme + ' add controls centered with 12px spacing');
      check(geometry.height === 32 && geometry.font === 13 && geometry.icon === 16 && geometry.border === '1px', theme + ' add controls match subject size with thin border');
      await treeMenu(page.locator('.library-tree-item').first()); await shot(theme + '-theme'); await page.keyboard.press('Escape');
    }
    // Persist only into the in-memory fixture, then reload to verify save semantics.
    const longName = '数学与应用数学综合基础课程目录';
    await treeMenu(page.locator('.library-tree-item').first());
    await page.getByRole('menuitem', { name: '重命名', exact: true }).click();
    await page.getByRole('textbox', { name: '学科名称', exact: true }).fill(longName); await page.keyboard.press('Enter');
    check(await page.locator('.library-tree-item').filter({ hasText: longName }).count() === 1, 'long Chinese subject rename targets correct row');
    const saved = page.waitForResponse(r => r.url().endsWith('/api/system/settings/subjects') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '保存目录', exact: true }).click(); await saved; await books();
    check(await page.locator('.library-tree-item').filter({ hasText: longName }).count() === 1, 'explicit save survives reload in isolated fixture');
    check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), 'long subject causes no page overflow'); await shot('long-subject');
    await treeMenu(page.locator('.library-tree-item').first()); await page.keyboard.press('ArrowDown');
    check(await page.getByRole('menuitem', { name: '删除学科', exact: true }).evaluate(el => document.activeElement === el), 'menu ArrowDown moves focus');
    await page.locator('.library-category-header').click(); check(await page.getByRole('menu', { name: /管理/ }).count() === 0, 'outside click dismisses context menu');
    check(!requests.some(r => r.method !== 'GET' && !(r.method === 'POST' && ['/api/system/settings/subjects', '/api/mistakes/chat-sources/query'].includes(r.path))), 'only in-memory directory fixture written; no user data or model calls');
    check(result.errors.length === 0, 'no renderer exceptions');
  }
} catch (e) { result.errors.push(String(e)); process.exitCode = 1; await shot('failure').catch(() => {}); }
finally { writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(out, 'requests.json'), JSON.stringify(requests, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); console.log(JSON.stringify(result)); }
