/** Isolated Electron chrome QA. API/goal/timer data are fixtures, never user storage. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname, join } from 'node:path';
import { tmpdir } from 'node:os';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'after';
const out = resolve('docs/qa/chat-header-history-2026-10-23', phase); mkdirSync(out, { recursive: true });
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18187' }, stdio: 'ignore' });
const goal = { id: 'qa-goal', title: '复习极限与积分', objective: '完成教材复习', status: 'active', revision: 1, success_criteria: [], scope: { subject: '数学', book_name: '' } };
const task = { id: 'qa-focus', goal_id: goal.id, goal_title: goal.title, goal_status: 'active', goal_revision: 1, title: '复习多重积分的计算步骤', content: '', duration_seconds: 1500, elapsed_seconds: 60, active_ms: 60000, legacy_elapsed_ms: 0, status: 'pending', revision: 1, position: 0, criterion_ids: [] };
let running = false, sequence = 0;
const conversations = ['解释一下多重积分', '打开错题速录', '解释一下泰勒公式中的余项与相减时的有效阶数', '给我讲讲这道图片题', '用几何意义理解定积分'].map((title, i) => ({ id: 'qa-chat-' + i, title, subject: '数学', book_name: '', updated_at: '2026-10-22T12:00:00Z', message_count: 2, management: { state: 'active', pinned: i === 0, revision: 1 } }));
const requests = [];
const server = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (pathname.startsWith('/api/')) requests.push({ path: req.url, method: req.method });
    if (pathname === '/api/chat/conversations') return reply({ items: conversations, has_more: false, next_cursor: null });
    if (pathname.endsWith('/management')) return reply({ state: 'active', pinned: false, revision: 1 });
    if (/^\/api\/chat\/conversations\/qa-chat-\d$/.test(pathname)) return reply({ id: pathname.split('/').at(-1), subject: '数学', book_name: '', messages: [
      { id: 'qa-user', role: 'user', content: '解释一下多重积分' },
      { id: 'qa-answer', role: 'assistant', content: '二重积分将区域上的函数值累加。\n\n$$\\iint_D f(x,y)\\,dx\\,dy.$$\n\n计算时先确定区域，再选择积分次序。' },
    ], page: { has_more: false, total: 2, limit: 40 } });
    if (pathname === '/api/focus') return reply({ revision: running ? 2 : 1, runtime_id: 'qa-runtime', snapshot_sequence: ++sequence, tasks: [task], next_offset: null, current_task: running ? task : null, next_task: null,
      current_session: running ? { id: 'qa-session', task_id: task.id, mode: 'countdown', target_seconds: 1500, status: 'running', active_ms: 60000, confirmed_active_ms: 60000, started_at: Date.now() / 1000 - 60, ended_at: null, end_reason: '' } : null,
      status: running ? 'running' : 'idle', reason: '', checkpoint_at: null, active_ms: running ? 60000 : 0, remaining_seconds: running ? 1440 : null, overtime_seconds: 0, server_time: Date.now() / 1000, goal_stats: [{ goal_id: goal.id, task_count: 1, completed_count: 0, active_ms: 60000 }],
    });
    if (pathname === '/api/goals') return reply([goal]);
    if (pathname === '/api/goals/' + goal.id) return reply(goal);
    if (pathname === '/api/goals/' + goal.id + '/runtime') return reply(null);
    if (pathname === '/api/goals/' + goal.id + '/evidence') return reply([]);
    if (pathname.startsWith('/api/') || pathname === '/health') {
      const response = await fetch('http://127.0.0.1:18187' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return;
    }
    const file = resolve('frontend/dist', extname(pathname) ? '.' + pathname : 'index.html');
    if (!file.startsWith(resolve('frontend/dist') + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500).end(String(error)); }
});
let app, page;
const results = { phase, platform: 'macOS real Electron; fixture APIs, no real model or learning writes', checks: [], geometry: [], errors: [] };
function check(ok, name) { results.checks.push({ name, pass: !!ok }); if (!ok) throw Error(name); }
async function shot(name) { await page.screenshot({ path: resolve(out, name + '.png'), animations: 'disabled', scale: 'css' }); }
async function chat() {
  await page.goto('http://127.0.0.1:18186/?conversation_id=qa-chat-1');
  await page.locator('.learning-question .markdown-body').waitFor();
  await page.locator('.context-session-entry').first().waitFor({ state: 'attached' });
  await page.evaluate(() => document.fonts.ready);
}
async function geometry() {
  return page.locator('.learning-workspace-header').evaluate(header => {
    const box = selector => { const el = header.querySelector(selector); return el ? el.getBoundingClientRect().toJSON() : null; };
    const button = header.querySelector('.learning-new-conversation');
    return { header: header.getBoundingClientRect().toJSON(), newChat: box('.learning-new-conversation'), timer: box('.focus-tray'), scope: box('.scope-trigger'),
      newFont: button ? getComputedStyle(button).fontSize : null, scopeFont: header.querySelector('.scope-trigger') ? getComputedStyle(header.querySelector('.scope-trigger')).fontSize : null,
      pageOverflow: document.body.scrollWidth > innerWidth };
  });
}
try {
  await new Promise(r => server.listen(18186, '127.0.0.1', r));
  for (let n = 0; n < 40; n++) { try { await fetch('http://127.0.0.1:18187/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const userData = mkdtempSync(join(tmpdir(), 'texa-chat-chrome-'));
  writeFileSync(join(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18186', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18186' } });
  page = await app.firstWindow(); page.setDefaultTimeout(10000); page.on('pageerror', e => results.errors.push(String(e)));
  await page.locator('.app-shell').waitFor();
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  for (const [w, h] of [[1280, 820], [1024, 768], [760, 820]]) {
    running = false;
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [w, h]);
    await chat();
    if (w <= 760) await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    await shot(w + '-history');
    if (phase === 'before') continue;
    check(await page.locator('.learning-context-sidebar[data-floating="false"] .learning-context-header').count() === 0, w + ' duplicate sidebar toolbar removed');
    check(await page.locator('.conversation-group-label').count() === 0, w + ' group headings removed');
    check(await page.locator('.context-session-entry.is-pinned .conversation-pin').count() === 1, w + ' pinned row has inline pin');
    check(await page.locator('.context-session-entry:not(.is-pinned) .conversation-pin').count() === 0, w + ' unpinned rows have no pin');
    const spacing = await page.locator('.context-session-entry').evaluateAll(nodes => nodes.slice(0, 3).map((el, i, all) => i ? el.getBoundingClientRect().top - all[i - 1].getBoundingClientRect().bottom : 0));
    check(spacing.every(gap => gap <= 5), w + ' pinned and recent rows share compact spacing');
    if (w <= 760) await page.getByRole('button', { name: '收起侧栏', exact: true }).click();
    const beforeTimer = await geometry(); results.geometry.push({ w, state: 'idle', ...beforeTimer });
    check(Math.abs(beforeTimer.newChat.height - beforeTimer.scope.height) <= 1 && beforeTimer.newFont === beforeTimer.scopeFont, w + ' new chat matches subject control height and font');
    check(beforeTimer.newChat.right <= beforeTimer.scope.left && !beforeTimer.pageOverflow, w + ' new chat sits left of subject without overflow');
    running = true;
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.locator('.learning-workspace-header .focus-tray').waitFor();
    await page.locator('.focus-tray').evaluate(el => Promise.all(el.getAnimations().map(animation => animation.finished)));
    const active = await geometry(); results.geometry.push({ w, state: 'running', ...active });
    check(active.newChat.right <= active.timer.left && active.timer.right <= active.scope.left, w + ' new chat timer and subject are parallel without overlap');
    check(Math.abs(active.newChat.y - active.scope.y) <= 1 && Math.abs(active.timer.y - active.scope.y) <= 1, w + ' header controls share vertical alignment');
    check(await page.locator('.focus-tray').evaluate(el => getComputedStyle(el).animationName !== 'none'), w + ' timer has entry animation');
    check(!active.pageOverflow, w + ' active timer fits header');
    await shot(w + '-timer');
    await page.locator('.focus-docked').click(); await page.locator('.focus-mini-panel').waitFor();
    check(await page.locator('.focus-mini-panel').evaluate(el => { const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight; }), w + ' focus panel stays inside window');
    await page.keyboard.press('Escape');
    await page.locator('.learning-new-conversation').focus(); await page.keyboard.press('Enter');
    await page.locator('.learning-workspace-shell[data-empty="true"]').waitFor();
    check(await page.locator('.learning-new-conversation').count() === 0, w + ' new chat opens start page without redundant header action');
    check(await page.locator('.focus-tray').count() === 1, w + ' new conversation retains focus session');
    if (w <= 760) await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    await page.getByRole('button', { name: '已置顶 解释一下多重积分', exact: true }).click();
    await page.locator('.context-session-entry.is-pinned .context-session-row[aria-current="page"]').waitFor();
    check((await page.locator('.learning-question .markdown-body').innerText()).trim() === '解释一下多重积分', w + ' pinned conversation still opens');
    if (w <= 760) await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    await page.getByRole('button', { name: '解释一下多重积分的更多操作', exact: true }).click();
    check(await page.getByRole('menuitem', { name: '取消置顶', exact: true }).isVisible(), w + ' pinned conversation actions retained');
    await page.keyboard.press('Escape');
  }
  if (phase !== 'before') {
    await page.emulateMedia({ reducedMotion: 'reduce' }); await chat();
    await page.locator('.focus-tray').waitFor();
    check(await page.locator('.focus-tray').evaluate(el => getComputedStyle(el).animationName === 'none'), 'reduced motion disables timer animation');
    if (!await page.getByRole('link', { name: '目标与任务', exact: true }).isVisible()) await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
    if (!await page.getByRole('link', { name: '目标与任务', exact: true }).isVisible()) await page.locator('.navigation-domains > summary').click();
    await page.getByRole('link', { name: '目标与任务', exact: true }).click(); await page.locator('.goals-header .focus-tray').waitFor(); await shot('goals-timer');
    check(await page.locator('.goals-header').evaluate(el => { const timer = el.querySelector('.focus-tray').getBoundingClientRect(); return [...el.children].filter(child => !child.classList.contains('focus-tray')).every(child => { const r = child.getBoundingClientRect(); return !r.width || r.right <= timer.left || r.left >= timer.right; }); }), 'goal header timer remains beside goal actions');
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820));
    await chat();
    await page.getByRole('button', { name: '收起侧栏', exact: true }).click();
    await page.getByRole('button', { name: '展开对话历史', exact: true }).hover();
    await page.getByRole('button', { name: '收起对话历史', exact: true }).waitFor();
    check(await page.locator('.learning-context-sidebar[data-floating="true"] .conversation-pin').count() === 1, 'collapsed history retains inline pin');
    await shot('collapsed-history');
    await page.getByRole('button', { name: '收起对话历史', exact: true }).click();
    check(await page.getByRole('button', { name: '展开对话历史', exact: true }).getAttribute('aria-expanded') === 'false', 'floating history close remains available');
    await page.locator('.learning-workspace-header .focus-tray').evaluate(el => { el.dataset.qaIdentity = 'same-timer'; });
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/focus');
    await page.evaluate(() => window.dispatchEvent(new Event('online'))); await refreshed;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    check(await page.locator('.learning-workspace-header .focus-tray').getAttribute('data-qa-identity') === 'same-timer', 'focus refresh retains timer element without replaying entry');
    check(await page.locator('.learning-header-actions').evaluate(el => getComputedStyle(el).webkitAppRegion === 'no-drag'), 'header controls remain clickable in native titlebar');
    check(!requests.some(r => r.method !== 'GET' && /focus\/commands|chat.*(?:stream|save)/.test(r.path)), 'no model requests or learning writes');
    check(results.errors.length === 0, 'no renderer exceptions');
  }
} catch (e) { results.errors.push(String(e)); process.exitCode = 1; await shot('failure').catch(() => {}); }
finally { writeFileSync(resolve(out, 'results.json'), JSON.stringify(results, null, 2)); writeFileSync(resolve(out, 'requests.json'), JSON.stringify(requests, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); console.log(JSON.stringify(results)); }
