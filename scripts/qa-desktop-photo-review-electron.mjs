/** Isolated production Electron UI checks. No real model or learning data access. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const out = resolve('docs/qa/desktop-photo-review-2026-10-22'); mkdirSync(out, { recursive: true });
const imageFile = process.env.TEXA_QA_IMAGE || resolve('frontend/public/guide/learning.png');
const imageBytes = readFileSync(imageFile);
const fixture = JSON.parse(readFileSync(resolve('docs/qa/visual-mistake-projection-2026-10-21/fixture.json')));
const question = '为什么36题的对数函数不能直接等价无穷小替换，37却可以？';
const task = { id: 'task-photo', task_type: 'visual_qa', status: 'completed', goal: question, required_inputs: [], required_outputs: [], artifacts: { question, image_url: '/api/mistakes/tasks/task-photo/image' } };
const record = { id: 'photo', question_text: fixture.question, correct_answer: '$-\\frac12$', explanation: '相减时要保留有效阶数。', source: '问答图片上传', subject: '数学', created_at: '2026-10-22T08:00:00Z', revision: 1, content_status: 'ready', visibility: 'active', tags: [], mistake_type: [] };
let session;
function resetReview() { session = { id: 'review-photo', revision: 1, items: ['photo'], index: 0, results: {}, current_answer: '', revealed: false, current_item: { ...record, correct_answer: '', explanation: '' } }; }
resetReview();
const requests = [];
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18169' }, stdio: 'ignore' });
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1'); const path = url.pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path.startsWith('/api/')) requests.push({ path: req.url, method: req.method });
    if (path.endsWith('/image') && req.method === 'GET') { res.setHeader('Content-Type', 'image/png'); res.end(imageBytes); return; }
    if (path === '/api/system/settings/subjects') return reply([{ name: '数学', children: ['高数', '线代', '概率论'] }]);
    if (path === '/api/focus') return reply({ revision: 0, tasks: [], total: 0, next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', remaining_seconds: 0, active_ms: 0, server_time: Date.now() / 1000 });
    if (path === '/api/chat/conversations') return reply({ items: [{ id: 'photo', management: { state: 'active', pinned: false, revision: 1 }, title: question, subject: '数学', book_name: 'default', updated_at: new Date().toISOString(), message_count: 2 }], next_cursor: null });
    if (path === '/api/chat/conversations/photo') return reply({ id: 'photo', subject: '数学', book_name: 'default', messages: [
      { id: 'photo-user', role: 'user', content: question + '\n\n图片题干（识别文本，请校对）：\n' + fixture.raw, learning_task: task },
      { id: 'photo-answer', role: 'assistant', content: '关键是相减后的误差阶数。\n\n$$\\ln(1+x)=x-\\frac{x^2}{2}+o(x^2).$$\n\n第36题中，一阶项相减后抵消，必须保留高阶项。', learning_task: { ...task, task_type: 'qa' } }
    ], page: { has_more: false, total: 2, limit: 40 } });
    if (path.endsWith('/management')) return reply({ state: 'active', pinned: false, revision: 1 });
    if (path === '/api/mistakes/query') return reply({ items: [record, { ...record, id: 'photo2' }], next_cursor: null });
    if (path === '/api/mistakes/candidates' || path === '/api/mistakes/drafts') return reply([]);
    if (path === '/api/mistakes/chat-sources/query') return reply([]);
    if (path.startsWith('/api/review/sessions/review-photo')) {
      if (path.endsWith('/image') && req.method === 'POST') {
        for await (const chunk of req) { void chunk; }
        session = { ...session, revision: session.revision + 1, current_submission: { filename: '手写解答.png', image_url: '/api/review/sessions/review-photo/image' } };
        return reply(session);
      }
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null;
      if (path.endsWith('/feedback')) { session = { ...session, revision: session.revision + 2, revealed: true, feedback: { verdict: 'partial', summary: '思路正确，但二阶项的符号需要修改。', issues: ['相减后应保留 $-x^2/2$。'], suggestions: ['把最终结果改为 $-1/2$。'] }, current_item: record }; }
      else if (path.endsWith('/results')) { session = { ...session, revision: session.revision + 1, index: 1, results: { photo: 'attempt-photo' }, current_item: null, current_submission: null }; }
      else if (req.method === 'PATCH') session = { ...session, revision: session.revision + 1, ...(body.revealed ? { revealed: true, current_item: record } : { current_answer: body.answer }) };
      return reply(session);
    }
    if (path.startsWith('/api/') || path === '/health') { const response = await fetch('http://127.0.0.1:18169' + req.url); res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return; }
    const file = resolve('frontend/dist', extname(path) ? '.' + path : 'index.html');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(String(error)); }
});
let app, page;
const fixtureFailures = [];
const result = { platform: 'macOS, real Electron production renderer; isolated UI fixtures; Windows chrome simulated only', checks: [], errors: [] };
const check = (ok, name) => { result.checks.push({ name, pass: !!ok }); if (!ok) throw Error(name); };
async function shot(name) { await page.screenshot({ path: resolve(out, name + '.png'), animations: 'disabled', scale: 'css' }); }
async function go(path) { await page.goto('http://127.0.0.1:18168' + path); await page.locator('.app-shell').waitFor(); await page.evaluate(() => document.fonts.ready); }
async function noLeak(name) { check(!/schema_version|visual_summary|handwritten_work|MATH_PROTECTED|识别文本，请校对|题干上方左侧/.test(await page.locator('.persistent-route-panel:not([hidden])').innerText()), name + ' no internal OCR'); check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), name + ' no horizontal overflow'); }
try {
  await new Promise(r => server.listen(18168, '127.0.0.1', r));
  for (let i = 0; i < 40; i++) { try { await fetch('http://127.0.0.1:18169/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const userData = '/private/tmp/texa-photo-review-' + Date.now(); mkdirSync(userData); writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18168', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18168' } });
  page = await app.firstWindow(); page.setDefaultTimeout(12000); page.on('pageerror', error => result.errors.push(String(error))); page.on('response', res => { if (res.status() >= 400) fixtureFailures.push({ url: res.url(), status: res.status() }); }); page.on('console', msg => { if (msg.type() === 'error') console.log('RENDERER', msg.text()); }); await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.locator('.app-shell').waitFor();
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setContentSize(...size), [width, height]);
    await go('/goals'); await page.locator('.goal-session').waitFor();
    if (width <= 760) { if (await page.getByRole('button', { name: '收起侧栏', exact: true }).isVisible()) await page.getByRole('button', { name: '收起侧栏', exact: true }).click(); }
    await page.getByRole('button', { name: 'AI 学习任务', exact: true }).click(); await noLeak(width + ' goals');
    check(await page.getByText('按目标准备学习内容', { exact: true }).isVisible(), width + ' AI task purpose visible');
    check(await page.locator('.goal-management-actions').evaluate(el => getComputedStyle(el).justifyContent === 'flex-start' && [...el.children].every(b => getComputedStyle(b).borderTopStyle !== 'none')), width + ' goal commands aligned with borders');
    await shot(width + '-goals');
    await page.locator('body').click({ position: { x: width - 20, y: height - 20 } }); await page.keyboard.press('Meta+a');
    check(await page.evaluate(() => !window.getSelection().toString()), width + ' Cmd+A does not select whole workspace');
    await page.keyboard.press('Alt+a'); check(await page.evaluate(() => !window.getSelection().toString()), width + ' Alt+A does not select whole workspace');
    await go('/mistakes'); await page.locator('.mistakes-row-title').first().waitFor(); await noLeak(width + ' mistakes');
    check(await page.locator('.mistakes-toolbar').evaluate(el => el.getBoundingClientRect().height < 100), width + ' compact mistake toolbar'); await shot(width + '-mistakes');
    await go('/?conversation_id=photo'); await page.locator('.is-visual-question .question-image-thumbnail img').waitFor(); await noLeak(width + ' photo chat');
    const bubble = page.locator('.is-visual-question');
    await page.waitForFunction(() => document.querySelector('.is-visual-question .markdown-body')?.textContent.includes('为什么36'));
    check((await bubble.innerText()).includes('为什么36题的对数函数不能直接等价无穷小替换') && (await bubble.innerText()).includes('37却可以'), width + ' user request retained');
    check(await bubble.evaluate(el => el.querySelector('.question-image-attachment').getBoundingClientRect().top >= el.querySelector('.markdown-body').getBoundingClientRect().bottom), width + ' thumbnail below question');
    check(!requests.some(r => r.path === '/api/mistakes/tasks/task-photo/image'), width + ' original is lazy');
    await bubble.locator('.markdown-body').dblclick(); await page.keyboard.press('Meta+a');
    check(await page.evaluate(() => { const text = window.getSelection().toString(); return text.includes('为什么36') && !text.includes('学习工作区'); }), width + ' reading block selection preserved');
    await page.evaluate(() => window.getSelection().removeAllRanges());
    if (width <= 919) check(await page.locator('.learning-document-column').evaluate(el => el.getBoundingClientRect().left >= 32), width + ' reading clears history handle');
    await shot(width + '-chat');
    await page.getByRole('button', { name: '查看题目图片原图', exact: true }).click(); await page.getByRole('dialog', { name: '题目图片' }).locator('img').waitFor();
    await shot(width + '-original'); await page.keyboard.press('Escape'); check(await page.getByRole('dialog').count() === 0, width + ' Escape closes image');
    requests.length = 0;
    resetReview(); await go('/learning/review/review-photo'); await page.getByRole('textbox', { name: '写下答案，或上传手写解答' }).fill('我的答案为 1/2。');
    await page.locator('#review-answer').press('Meta+a'); check(await page.locator('#review-answer').evaluate(el => el.selectionStart === 0 && el.selectionEnd === el.value.length), width + ' editor Select All preserved'); await page.locator('#review-answer').press('ArrowRight');
    await page.getByRole('button', { name: '保存草稿', exact: true }).click(); await page.waitForFunction(() => document.querySelector('#review-answer')?.value === '我的答案为 1/2。');
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(el => el.textContent === '上传解答' && !el.disabled));
    await page.locator('input[type=file][accept*="image/png"]').setInputFiles(imageFile); await page.getByRole('button', { name: '提交作答并批改', exact: true }).waitFor();
    await page.reload(); await page.getByRole('button', { name: '提交作答并批改', exact: true }).waitFor(); await noLeak(width + ' redo input');
    check(await page.locator('.review-session-question .katex').evaluateAll(nodes => nodes.every(node => { if (getComputedStyle(node).overflowY === 'visible') return true; const box = node.getBoundingClientRect(); return [...node.querySelectorAll('.base')].every(base => { const rect = base.getBoundingClientRect(); return rect.top >= box.top - 1 && rect.bottom <= box.bottom + 1; }); })), width + ' math vertical bounds visible');
    await shot(width + '-redo');
    check(await page.locator('#review-answer').inputValue() === '我的答案为 1/2。', width + ' draft and photo survive reload');
    await page.getByRole('button', { name: '提交作答并批改', exact: true }).click(); await page.getByRole('heading', { name: 'AI 批改 部分正确' }).waitFor(); await noLeak(width + ' feedback'); await shot(width + '-feedback');
    check(await page.getByRole('button', { name: '独立做对', exact: true }).isEnabled(), width + ' explicit confirmation remains available');
    await page.getByRole('button', { name: '部分完成', exact: true }).scrollIntoViewIfNeeded(); await shot(width + '-feedback-confirm');
    await page.getByRole('button', { name: '部分完成', exact: true }).click(); await page.getByRole('heading', { name: '本次复习完成', exact: true }).waitFor();
  }
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820)); await go('/mistakes');
  await page.evaluate(() => { const marker = document.querySelector('.desktop-titlebar-marker'); marker.classList.remove('is-macos'); });
  check(await page.locator('.app-rail-mark').evaluate(el => [el, ...el.querySelectorAll('*')].every(node => getComputedStyle(node).webkitAppRegion === 'no-drag')), 'Windows logo and children no-drag');
  await page.getByRole('link', { name: 'Texa 学习工作区', exact: true }).click(); check(new URL(page.url()).pathname === '/', 'logo navigates home under Windows chrome');
  check(result.errors.length === 0, 'no renderer exceptions'); check(fixtureFailures.length === 0, 'no failed fixture responses');
} catch (error) { result.errors.push(String(error)); process.exitCode = 1; await shot('failure').catch(() => {}); }
finally { writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(out, 'requests.json'), JSON.stringify(requests, null, 2)); writeFileSync(resolve(out, 'fixture-responses.json'), JSON.stringify(fixtureFailures, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); console.log(JSON.stringify(result)); }
