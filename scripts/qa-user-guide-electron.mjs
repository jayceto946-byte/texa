/** Current production UI in real Electron. Read-only sample APIs, isolated userData.
 * NODE_PATH=<bundled node_modules> node scripts/qa-user-guide-electron.mjs [--capture]
 * No Texa data, credentials, model calls, imports or restore operations are used.
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const capture = process.argv.includes('--capture');
const out = resolve('docs/qa/user-guide-2026-10-19');
const assets = resolve('frontend/public/guide');
mkdirSync(out, { recursive: true }); mkdirSync(assets, { recursive: true });
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18119' }, stdio: 'ignore' });
const result = { environment: 'macOS, Electron 37, production frontend; read-only sample APIs; no live models or release package validation', checks: [], errors: [], screenshots: [] };
const draft = { id: 'guide-draft', kind: 'generation', status: 'editable', draft_revision: 1, conversation_id: 'visual-session-0', content: { title: '相减时保留有效阶', abstract: '从一次极限讨论中整理的方法。', subject: '数学/高数', tags: ['极限'], chapter_refs: [], blocks: [{ block_id: 'b1', type: 'paragraph', data: { markdown: '等价替换前，先检查低阶项是否相消。\n\n当 $x\\to0$ 时，$\\sin x=x-\\frac{x^3}{6}+o(x^3)$。因此 $x-\\sin x$ 的有效项是三阶项。\n\n这份示例草稿尚未保存为正式笔记。' }, source_ref_ids: [], evidence_ref_ids: [] }], quality: { warning_hash: '', warnings: [], semantic_review: 'unverified' } }, source_snapshot_ids: [], base_note_id: null, base_note_revision: null, job_id: null, sources: [], chapter_options: [] };
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (url.pathname === '/api/focus') return reply({ revision: 0, tasks: [], total: 0, next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', reason: '', remaining_seconds: 0, active_ms: 0, server_time: Date.now() / 1000 });
    if (url.pathname === '/api/books/import-capabilities') return reply({ mineru: { configured: false, available: false, mode: 'none', reason: 'not_configured' }, local_pdf: { available: true, limitation: '仅读取 PDF 文字层，不做 OCR' }, output_bundle: { available: true } });
    if (url.pathname === '/api/system/settings/subjects') return reply({ subjects: [{ name: '数学', children: ['高数', '线代', '概率论'] }] });
    if (url.pathname === '/api/system/settings') {
      const data = await (await fetch('http://127.0.0.1:18119' + req.url)).json();
      return reply({ ...data.data, models: { ...data.data.models, multimodal_mode: 'split' } });
    }
    if (url.pathname === '/api/chat/conversations') {
      const data = await (await fetch('http://127.0.0.1:18119' + req.url)).json();
      return reply({ items: data.data.map(c => ({ ...c, management: { state: 'active', pinned: false, revision: 0 } })), has_more: false, next_cursor: null });
    }
    if (url.pathname.startsWith('/api/chat/conversations/')) {
      const data = await (await fetch('http://127.0.0.1:18119' + req.url)).json();
      return reply({ ...data.data, management: { state: 'active', pinned: false, revision: 0 } });
    }
    if (url.pathname === '/api/system/backups') return reply({ items: [], last: null, backup_path: '本机学习数据备份目录' });
    if (url.pathname === '/api/notes/drafts/guide-draft') return reply(draft);
    if (url.pathname.startsWith('/api/notes')) return reply({ items: [], has_more: false, next_cursor: null, books: [], chapter_refs: [] });
    if (url.pathname === '/api/mistakes/candidates') return reply([]);
    if (url.pathname === '/api/mistakes/drafts') return reply([]);
    if (url.pathname === '/api/mistakes/query') {
      const data = await (await fetch('http://127.0.0.1:18119/api/mistakes/overview', { method: 'POST', body: '{}' })).json();
      return reply({ items: data.data.records.map(record => ({ ...record, revision: 1, content_status: 'ready', diagnosis_status: 'confirmed', visibility: 'active', mastery_status: 'learning', recent_attempts: [] })), next_cursor: null });
    }
    if (url.pathname.startsWith('/api/review/sessions')) return reply(null);
    if (/^\/api\/goals\/[^/]+\/tasks$/.test(url.pathname)) return reply([]);
    if (/^\/api\/books\/[^/]+\/(chapters|import-outline)$/.test(url.pathname)) return reply([]);
    if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
      const response = await fetch('http://127.0.0.1:18119' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(response.status, { 'Content-Type': 'application/json' }); res.end(await response.text()); return;
    }
    const file = resolve('frontend/dist', !extname(url.pathname) ? 'index.html' : '.' + url.pathname);
    if (!file.startsWith(resolve('frontend/dist') + '/')) throw Error('Invalid path');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2', '.ttf': 'font/ttf' })[extname(file)] || 'application/octet-stream');
    res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(JSON.stringify({ message: String(error) })); }
});
let app, page;
const check = (ok, name) => { result.checks.push({ name, status: ok ? 'PASS' : 'FAIL' }); if (!ok) throw Error(name); };
async function ready() {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(e => !e.getBoundingClientRect().height));
}
async function shot(name, locator) {
  await ready();
  const path = resolve(capture ? assets : out, name + '.png');
  if (locator) await locator.screenshot({ path, animations: 'disabled', scale: 'css' });
  else await page.screenshot({ path, animations: 'disabled', scale: 'css' });
  result.screenshots.push(path);
}
async function go(path) { await page.goto('http://127.0.0.1:18118' + path); await page.locator('.app-shell').waitFor(); }
async function settings(tab) { await page.getByRole('button', { name: '设置', exact: true }).click(); await page.getByRole('button', { name: tab, exact: true }).click(); }
try {
  await new Promise(r => server.listen(18118, '127.0.0.1', r));
  for (let i = 0; i < 50; i++) { try { await fetch('http://127.0.0.1:18119/health'); break; } catch { await new Promise(r => setTimeout(r, 150)); } }
  const userData = resolve('/tmp/texa-user-guide-qa-' + Date.now()); mkdirSync(userData, { recursive: true });
  writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18118', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18118' } });
  page = await app.firstWindow(); page.setDefaultTimeout(15000); page.on('pageerror', e => result.errors.push(String(e))); page.on('console', m => { if (m.type() === 'error' && /TypeError|ReferenceError|render error/.test(m.text())) result.errors.push(m.text()); });
  await page.locator('.app-shell').waitFor();
  await page.evaluate(() => { localStorage.setItem('kaoyan_subject', '数学/高数'); localStorage.setItem('kaoyan_book_name', '高等数学 · 上册（第七版）'); });
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1280, 820));
  check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
  if (capture) {
    await go('/');
    await page.getByRole('button', { name: /等价无穷小：为什么相减/ }).first().click();
    await page.locator('.study-turn-heading').first().waitFor(); await shot('learning');
    await page.getByRole('button', { name: /查看来源/ }).first().click(); await page.locator('.context-inspector').waitFor(); await shot('sources');
    await go('/');
    await settings('模型连接'); await page.getByRole('heading', { name: '模型连接', exact: true }).waitFor(); await page.locator('.settings-content-pane').evaluate(el => { el.scrollTop = 370; }); await shot('models', page.getByRole('dialog'));
    await page.getByRole('button', { name: '关闭设置' }).click();
    await go('/books'); await page.locator('.library-workbench').waitFor(); await shot('books');
    await go('/books/import'); await page.getByRole('heading', { name: '导入教材', exact: true }).waitFor(); await shot('import');
    await page.getByRole('radio', { name: 'MinerU 输出包', exact: true }).click(); await page.getByRole('button', { name: '导入输出包', exact: true }).waitFor(); await shot('import-bundle');
    await go('/exercises'); await page.getByRole('radio', { name: '导入', exact: true }).click(); await shot('exercise-import');
    await page.getByRole('radio', { name: '练习', exact: true }).click(); await page.getByRole('heading', { name: '本次题量' }).waitFor(); await shot('practice');
    await go('/mistakes'); await page.getByRole('heading', { name: '错题', exact: true }).waitFor(); await page.locator('.mistakes-row').first().waitFor(); await shot('mistakes');
    await go('/learning'); await page.getByRole('heading', { name: /复习/ }).first().waitFor(); await shot('review');
    await go('/goals'); await page.getByRole('heading', { name: '目标与任务', exact: true }).waitFor(); await shot('goals');
    await go('/notes/drafts/guide-draft'); await page.getByRole('button', { name: '保存笔记', exact: true }).waitFor(); await shot('notes');
    await settings('数据与教材'); await page.getByRole('heading', { name: '学习数据备份' }).waitFor(); await shot('backup', page.getByRole('dialog'));
  }
  if (!capture) {
    const { guideScenes } = await import('../frontend/src/features/guide/content.ts');
    const labels = { models: '模型连接', data: '数据与教材', about: '关于与更新', diagnostics: '高级与诊断' };
    await go('/'); await page.getByRole('link', { name: '用户指南', exact: true }).click();
    await page.getByRole('heading', { name: '连接回答模型', exact: true }).waitFor(); check(true, 'guide reachable from learning navigation');
    for (const scene of guideScenes) for (const step of scene.steps) {
      const path = `/guide?scene=${scene.id}&step=${step.id}`;
      await go(path); const article = page.locator('.guide-article');
      await article.getByRole('heading', { name: step.title, exact: true }).waitFor();
      await page.waitForFunction(() => { const img = document.querySelector('.guide-figure img'); return img?.complete && img.naturalWidth > 0; });
      check(await article.getByRole('listitem').count() === 3, `${scene.id}/${step.id}: three operation groups and screenshot loaded`);
      for (const action of step.actions) {
        await article.getByRole('to' in action ? 'link' : 'button', { name: action.label, exact: true }).click();
        if ('settings' in action) {
          const dialog = page.getByRole('dialog', { name: '设置', exact: true }); await dialog.waitFor();
          await dialog.getByRole('heading', { name: labels[action.settings], exact: true }).waitFor();
          await page.getByRole('button', { name: '关闭设置', exact: true }).click();
          check(new URL(page.url()).search === new URL(path, page.url()).search, `${step.id}: settings closes at same guide step`);
        } else {
          await page.waitForURL('http://127.0.0.1:18118' + action.to);
          await page.locator('.persistent-route-panel:not([hidden])').getByRole('heading').first().waitFor();
          check(!await page.getByText('页面文件未能加载', { exact: false }).isVisible(), `${action.to}: destination renders`);
        }
        check(true, `${step.id}: ${action.label}`);
        await go(path); await article.getByRole('heading', { name: step.title, exact: true }).waitFor();
      }
      if (step.id === 'backup' || step.id === 'notes') {
        await page.locator('.guide-actions').scrollIntoViewIfNeeded(); await shot(`1280-${step.id}-actions`);
      }
    }
    for (const [w, h] of [[1280, 820], [1024, 768], [760, 820]]) {
      await app.evaluate(({ BrowserWindow }, [width, height]) => BrowserWindow.getAllWindows()[0].setContentSize(width, height), [w, h]);
      await go('/guide'); await page.getByRole('heading', { name: '连接回答模型', exact: true }).waitFor();
      for (const scene of guideScenes) {
        await page.getByRole('radio', { name: scene.title, exact: true }).click(); await page.getByRole('heading', { name: scene.steps[0].title, exact: true }).waitFor();
        await shot(`${w}-${scene.id}`);
        check(await page.evaluate(() => document.body.scrollWidth <= innerWidth && [...document.querySelectorAll('.guide-body,.guide-scroll,.guide-scenarios')].every(el => el.scrollWidth <= el.clientWidth + 1)), `${w}/${scene.id}: no content overflow`);
        await page.getByRole('button', { name: '下一步', exact: true }).click(); await page.getByRole('heading', { name: scene.steps[1].title, exact: true }).waitFor();
        check(await page.locator('#guide-step-heading').evaluate(el => document.activeElement === el), `${w}/${scene.id}: next step focuses heading`);
        await page.getByRole('button', { name: '上一步', exact: true }).click();
      }
      await go('/guide?scene=textbooks&step=rented-gpu');
      await page.getByRole('heading', { name: '租卡运行 MinerU', exact: true }).waitFor();
      check(await page.locator('.guide-section').count() === 6, `${w}: rental workflow contains all six stages`);
      await page.getByRole('heading', { name: '2. 用国内源安装，独立于 Texa 环境', exact: true }).scrollIntoViewIfNeeded();
      await shot(`${w}-mineru-install`);
      check(await page.evaluate(() => document.body.scrollWidth <= innerWidth && document.querySelector('.guide-scroll').scrollWidth <= document.querySelector('.guide-scroll').clientWidth + 1), `${w}: rental command blocks contain horizontal scrolling`);
      const copy = page.getByRole('button', { name: '复制：实例终端：安装固定版本', exact: true });
      await copy.click(); await page.getByText('已复制', { exact: true }).waitFor();
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      check(copied.includes('mineru[full]==4.0.0') && copied.includes('--torch-backend=cu129'), `${w}: copy preserves pinned installation command`);
      await page.getByRole('heading', { name: '5. 下载到本机，然后关机', exact: true }).scrollIntoViewIfNeeded(); await shot(`${w}-mineru-export`);
      check(await page.locator('.guide-section').filter({ hasText: '5. 下载到本机，然后关机' }).innerText().then(text => text.includes('已关机') && text.includes('自己的 Mac/Windows')), `${w}: local download and shutdown warning visible`);
      await go('/guide?scene=manage&step=goals'); await page.getByRole('heading', { name: '安排任务与专注', exact: true }).waitFor();
      await page.getByRole('button', { name: /放大截图/ }).click(); await page.getByRole('dialog').waitFor();
      await page.keyboard.press('Escape'); check(!await page.getByRole('dialog').count(), `${w}: screenshot Escape closes`);
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.startsWith('放大截图'));
      check(true, `${w}: screenshot returns keyboard focus`);
      if (await page.getByRole('button', { name: '收起侧栏', exact: true }).isVisible()) await page.getByRole('button', { name: '收起侧栏', exact: true }).click();
      await page.getByRole('button', { name: '展开侧栏', exact: true }).click();
      if (w < 920) await page.getByText('功能与设置', { exact: true }).click();
      await page.getByRole('link', { name: '用户指南', exact: true }).click();
      check(true, `${w}: guide reachable with sidebar collapsed`);
    }
    await go('/guide?scene=unknown&step=unknown'); await page.getByRole('heading', { name: '连接回答模型', exact: true }).waitFor(); check(true, 'invalid scene and step fall back safely');
    await page.getByRole('radio', { name: '第一次学习', exact: true }).focus(); await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => [...document.querySelectorAll('[role="radio"]')].some(el => el.textContent === '教材学习' && el.getAttribute('aria-checked') === 'true'));
    check(await page.getByRole('radio', { name: '教材学习', exact: true }).getAttribute('aria-checked') === 'true', 'scene keyboard arrows');
    check(await page.getByRole('radio', { name: '教材学习', exact: true }).evaluate(el => document.activeElement === el), 'scene arrow navigation retains radio focus');
    await page.reload(); await page.getByRole('heading', { name: '按文件类型导入', exact: true }).waitFor(); check(true, 'guide location survives reload');
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1024, 768));
    await page.evaluate(() => localStorage.setItem('texa_appearance_theme', 'graphite')); await page.reload();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'graphite');
    await page.getByRole('heading', { name: '按文件类型导入', exact: true }).waitFor(); await shot('1024-graphite'); check(true, 'stored theme preserved in guide');
  }
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); if (page) await page.screenshot({ path: resolve(out, 'failure.png') }); process.exitCode = 1; }
finally {
  writeFileSync(resolve(out, capture ? 'capture-results.json' : 'results.json'), JSON.stringify(result, null, 2));
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill();
  console.log(JSON.stringify(result, null, 2));
}
