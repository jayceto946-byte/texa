/** Production renderer in the real Electron shell, disposable userData and fixture APIs.
 * NODE_PATH=<bundled packages> node scripts/qa-ui-source-study.mjs before|after|reference
 * No real storage, model calls, or release package modifications.
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron, chromium } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'after';
const out = resolve('docs/qa/ui-source-study-2026-10-19', phase);
mkdirSync(out, { recursive: true });
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18129' }, stdio: 'ignore' });
const result = { phase, environment: phase === 'reference' ? 'macOS ARM64, isolated Chrome browser, live read-only Storybook, deployment revision unknown' : 'macOS ARM64, Electron 37, production frontend, isolated fixture APIs', checks: [], errors: [], screenshots: [], observations: {} };
let requests = 0;
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (url.pathname === '/api/chat/stream') {
      requests++;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' }); res.write(': connected\n\n');
      // Keep a real fetch pending so the existing loading/stop controls can be inspected.
      const timer = setTimeout(() => res.destroy(), 30000); res.on('close', () => clearTimeout(timer)); return;
    }
    if (url.pathname === '/api/focus') return reply({ revision: 0, tasks: [], total: 0, next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', reason: '', remaining_seconds: 0, active_ms: 0, server_time: Date.now() / 1000 });
    if (url.pathname === '/api/chat/conversations') {
      const payload = await (await fetch('http://127.0.0.1:18129' + req.url)).json();
      return reply({ items: payload.data.map(c => ({ ...c, management: { state: 'active', pinned: false, revision: 0 } })), has_more: false, next_cursor: null });
    }
    if (/^\/api\/chat\/conversations\/[^/]+\/management$/.test(url.pathname)) return reply({ state: 'active', pinned: false, revision: 0 });
    if (url.pathname.startsWith('/api/chat/conversations/')) {
      const payload = await (await fetch('http://127.0.0.1:18129' + req.url)).json();
      return reply({ ...payload.data, management: { state: 'active', pinned: false, revision: 0 } });
    }
    if (url.pathname.startsWith('/api/notes')) return reply({ items: [], has_more: false, next_cursor: null, books: [], chapter_refs: [] });
    if (/^\/api\/goals\/[^/]+\/tasks$/.test(url.pathname)) return reply([]);
    if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
      const response = await fetch('http://127.0.0.1:18129' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return;
    }
    if (url.pathname === '/reference') { res.setHeader('Content-Type', 'text/html'); res.end(readFileSync('/private/tmp/texa-open-claude-ui-study/docs/claude-components-storybook.html')); return; }
    const file = resolve('frontend/dist', !extname(url.pathname) ? 'index.html' : '.' + url.pathname);
    if (!file.startsWith(resolve('frontend/dist') + '/')) throw Error('Invalid path');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.ttf': 'font/ttf' })[extname(file)] || 'application/octet-stream');
    res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(JSON.stringify({ message: String(error) })); }
});
let app, browser, page;
const check = (ok, name) => { result.checks.push({ name, status: ok ? 'PASS' : 'FAIL' }); if (!ok && phase === 'after') throw Error(name); };
async function shot(name, locator) {
  await page.evaluate(() => document.fonts.ready);
  if (phase !== 'reference') await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(el => !el.getBoundingClientRect().height));
  const path = resolve(out, name + '.png');
  await (locator || page).screenshot({ path, animations: 'disabled', scale: 'css' }); result.screenshots.push(path);
}
const go = async path => { await page.goto('http://127.0.0.1:18128' + path); await page.locator('.composer-textarea').waitFor(); };
try {
  await new Promise(r => server.listen(18128, '127.0.0.1', r));
  for (let i = 0; i < 50; i++) { try { await fetch('http://127.0.0.1:18129/health'); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const userData = resolve('/tmp/texa-ui-study-' + Date.now()); mkdirSync(userData, { recursive: true });
  writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  if (phase === 'reference') {
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  } else {
    app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18128', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18128' } });
    page = await app.firstWindow();
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820));
  }
  page.setDefaultTimeout(12000); page.on('pageerror', e => result.errors.push(String(e)));
  if (phase === 'reference') {
    await page.goto('https://claude-storybook.bystanderss.chatgpt.site/');
    await page.getByText('Chat Composer', { exact: false }).first().waitFor({ timeout: 45000 });
    await page.getByPlaceholder('How can I help you today?').waitFor();
    await shot('storybook');
    result.observations.headings = await page.getByRole('heading').allTextContents();
    result.observations.controls = await page.locator('button,input,textarea').evaluateAll(elements => elements.map(el => ({ tag: el.tagName, text: el.textContent, placeholder: el.getAttribute('placeholder') })));
    await page.getByPlaceholder('How can I help you today?').focus();
    await shot('storybook-focus');
    await page.getByText('Add content', { exact: true }).click(); await shot('storybook-add-content');
    result.observations.addContentMenuCount = await page.getByRole('menu').count();
    for (const name of ['Segmented Control', 'Thinking Accordion', 'Spring Physics Presets']) {
      await page.getByRole('button', { name: new RegExp(name) }).click();
      await page.getByRole('heading', { name, exact: true }).waitFor();
      await shot('storybook-' + name.toLowerCase().replaceAll(' ', '-'));
      result.observations[name] = await page.locator('button').allTextContents();
      if (name === 'Segmented Control') {
        await page.getByRole('button', { name: 'Projects', exact: true }).click(); await shot('storybook-segmented-selected');
      }
      if (name === 'Thinking Accordion') {
        await page.getByRole('button', { name: '切换状态：当前为【思考完毕】', exact: true }).click(); await shot('storybook-thinking-active');
      }
      if (name === 'Spring Physics Presets') {
        await page.getByRole('button', { name: /一键同屏发射/ }).click(); await shot('storybook-springs-triggered');
      }
    }
    writeFileSync(resolve(out, 'body.txt'), await page.locator('body').innerText());
  } else {
    await go('/');
    check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
    await page.getByRole('button', { name: /等价无穷小：为什么相减/ }).first().click();
    await page.locator('.study-turn-heading').first().waitFor();
    const field = page.locator('.composer-textarea');
    const tools = page.getByRole('button', { name: '学习操作', exact: true });
    await page.mouse.click(850, 80); await shot('learning-normal');
    await field.focus(); await shot('composer-focus', page.locator('.chat-composer'));
    await page.getByRole('button', { name: '上传题目图片' }).hover(); await shot('composer-hover', page.locator('.chat-composer'));
    await tools.focus(); await page.keyboard.press('Enter');
    await page.getByRole('menu').waitFor();
    const menu = page.getByRole('menu');
    result.observations.menuInitialFocus = await page.evaluate(() => document.activeElement?.getAttribute('role'));
    check(result.observations.menuInitialFocus === 'menuitem', 'menu opens with item focus');
    await shot('menu-keyboard');
    await page.keyboard.press('End');
    check(await page.getByRole('menuitem', { name: '错题速录' }).evaluate(el => el === document.activeElement), 'End focuses last menu item');
    await page.keyboard.press('ArrowDown');
    check(await page.getByRole('menuitem').first().evaluate(el => el === document.activeElement), 'ArrowDown wraps to first menu item');
    await page.keyboard.press('Escape');
    check(await tools.evaluate(el => el === document.activeElement), 'Escape restores trigger focus');
    if (phase === 'after') {
      await field.fill('键盘检查');
      await tools.press('ArrowUp');
      check(await page.getByRole('menuitem').last().evaluate(el => el === document.activeElement), 'ArrowUp opens at last item');
      await page.keyboard.press('Tab');
      check(!await menu.count(), 'Tab exits and dismisses menu');
      check(await page.getByRole('button', { name: '发送问题' }).evaluate(el => el === document.activeElement), 'Tab moves to enabled send button');
      await tools.press('ArrowDown'); await page.keyboard.press('Home');
      check(await page.getByRole('menuitem').first().evaluate(el => el === document.activeElement), 'Home focuses first item');
      await page.keyboard.press('Shift+Tab');
      check(!await menu.count() && !await tools.evaluate(el => el === document.activeElement), 'Shift+Tab exits menu to preceding control');
      await tools.click(); await page.mouse.click(850, 80); check(!await menu.count(), 'outside click dismisses menu');
    }
    await field.fill('说明相减结构中的有效阶数');
    await field.press('Shift+Enter');
    check((await field.inputValue()).endsWith('\n'), 'Shift+Enter inserts newline');
    await field.dispatchEvent('compositionstart', { data: '阶' });
    await field.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, isComposing: true, bubbles: true });
    check(requests === 0, 'CJK composing Enter does not send');
    await field.dispatchEvent('compositionend', { data: '阶' });
    await field.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, isComposing: false, bubbles: true });
    check(requests === 0, 'IME keyCode 229 does not send after compositionend');
    await field.fill(Array.from({ length: 16 }, (_, i) => `第${i + 1}行：保留公式、条件与中文叙述。`).join('\n'));
    await shot('composer-multiline');
    check(await field.evaluate(el => el.clientHeight <= Math.min(240, innerHeight * .3) + 1 && el.scrollHeight > el.clientHeight), 'long input is bounded and scrollable');
    await field.fill('解释相减结构中的有效阶数'); await field.press('Enter');
    await page.getByRole('button', { name: '停止生成' }).waitFor();
    await page.getByRole('button', { name: '上传题目图片' }).hover({ force: true });
    await shot('composer-loading', page.locator('.chat-composer'));
    check(await field.isDisabled(), 'generating disables question input');
    if (phase === 'after') check(await page.getByRole('button', { name: '上传题目图片' }).evaluate(el => getComputedStyle(el).opacity === '0.45' && getComputedStyle(el).borderColor === 'rgba(0, 0, 0, 0)'), 'disabled tool is dimmed and has no hover border');
    await page.getByRole('button', { name: '停止生成' }).click();
    await page.getByRole('button', { name: '发送问题' }).waitFor(); check(true, 'stop returns to composer');
    // Browser-native rejection path, no OCR or model invoked.
    await page.locator('input[type=file][accept="image/png,image/jpeg,image/webp,image/bmp"]').setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('fixture') });
    await page.locator('.composer-surface [role=alert]').waitFor(); await shot('composer-error', page.locator('.chat-composer'));
    for (const [w, h] of [[1280, 820], [1024, 768], [760, 820]]) {
      await app.evaluate(({ BrowserWindow }, [width, height]) => BrowserWindow.getAllWindows()[0].setContentSize(width, height), [w, h]);
      await go('/?conversation_id=visual-session-0'); await page.locator('.study-turn-heading').first().waitFor(); await field.fill('怎样判断展开到几阶？'); await shot(`${w}-learning`);
      check(await page.evaluate(() => document.body.scrollWidth <= innerWidth && [...document.querySelectorAll('.composer-surface,.composer-toolbar')].every(el => el.scrollWidth <= el.clientWidth + 1)), `${w}: composer fits viewport`);
      await tools.click(); await shot(`${w}-menu`); await page.keyboard.press('Escape');
      await page.goto('http://127.0.0.1:18128/books'); await page.locator('.library-workbench').waitFor(); await shot(`${w}-books`);
    }
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820));
    await go('/'); await page.emulateMedia({ reducedMotion: 'reduce' });
    await tools.click(); await shot('menu-reduced-motion');
    check(await menu.evaluate(el => getComputedStyle(el).animationName === 'none'), 'menu reduced-motion has no animation');
    await page.keyboard.press('Escape');
    await page.evaluate(() => localStorage.setItem('texa_appearance_theme', 'graphite')); await page.reload();
    await field.waitFor(); await tools.click(); await shot('menu-graphite');
    check(await page.evaluate(() => document.documentElement.dataset.theme === 'graphite'), 'stored graphite theme preserved');
    check(result.errors.length === 0, 'no renderer exceptions');
    if (process.argv.includes('--native')) {
      await go('/'); await field.focus();
      await page.evaluate(() => {
        window.texaNativeInputEvents = [];
        for (const type of ['compositionstart', 'compositionupdate', 'compositionend', 'keydown', 'input']) {
          document.querySelector('.composer-textarea').addEventListener(type, event => window.texaNativeInputEvents.push({ type, key: event.key, keyCode: event.keyCode, composing: event.isComposing, trusted: event.isTrusted, data: event.data }));
        }
      });
      const initialRequests = requests;
      console.log('Native input probe ready for 120 seconds');
      await new Promise(r => setTimeout(r, 120000));
      result.observations.nativeInputEvents = await page.evaluate(() => window.texaNativeInputEvents);
      result.observations.nativeInputValue = await field.inputValue();
      result.observations.nativeInputSentRequests = requests - initialRequests;
      result.observations.nativeCompositionObserved = result.observations.nativeInputEvents.some(event => event.type === 'compositionstart');
      await shot('native-ime');
    }
  }
} catch (error) { result.errors.push(String(error)); if (page) { await shot('failure').catch(() => {}); writeFileSync(resolve(out, 'failure.txt'), await page.locator('body').innerText().catch(() => '')); } process.exitCode = 1; }
finally {
  writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2));
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); await browser?.close().catch(() => {}); server.close(); upstream.kill();
  console.log(JSON.stringify({ phase, checks: result.checks, errors: result.errors, screenshots: result.screenshots.length }, null, 2));
}
