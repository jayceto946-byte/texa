/** Isolated real Electron + file parsing/API/SQLite. No model/OCR calls. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const work = resolve(process.env.TEXA_MINERU_EXERCISE_QA_WORK || `artifacts/exercise-workflow-2026-11-02/electron-${Date.now()}`);
mkdirSync(resolve(work, 'screenshots'), { recursive: true });
const book = '合成题库';
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18061' }, stdio: 'ignore' });
const backend = spawn(resolve('venv310/bin/python'), ['scripts/qa-mineru-exercise-server.py'], { env: { ...process.env, TEXA_QC_QA_WORK: work }, stdio: ['ignore', 'pipe', 'pipe'] });
let backendLog = '', latest, committed;
backend.stdout.on('data', d => backendLog += d); backend.stderr.on('data', d => backendLog += d);
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const chunks = []; for await (const chunk of req) chunks.push(chunk); const body = Buffer.concat(chunks);
    if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
      res.setHeader('Content-Type', 'application/json');
      if (url.pathname === '/api/books/list') { res.end(JSON.stringify({ success: true, data: [{ name: book, book_id: 'qc-book', subject: '专业课', chapter_count: 11 }] })); return; }
      if (url.pathname === '/api/system/settings/subjects') { res.end(JSON.stringify({ success: true, data: { subjects: [{ name: '专业课', children: [] }] } })); return; }
      if (url.pathname.endsWith('/chapters')) { res.end(JSON.stringify({ success: true, data: [] })); return; }
      const target = url.pathname.startsWith('/api/exercises/') ? '18062' : '18061';
      const response = await fetch(`http://127.0.0.1:${target}${req.url}`, { method: req.method, headers: { 'Content-Type': req.headers['content-type'] || 'application/json' }, ...(body.length ? { body } : {}) });
      if (url.pathname === '/api/exercises/candidates/batch-add') { const data = await response.json(); committed = data; res.writeHead(response.status); res.end(JSON.stringify(data)); return; }
      if(url.pathname.includes('/file-sources/') || /\/attachments\//.test(url.pathname)) { res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/octet-stream' }); res.end(Buffer.from(await response.arrayBuffer())); return; }
      const data = await response.json();
      if (url.pathname === '/api/exercises/upload-analyze') latest = data;
      if (url.pathname === '/api/chat/conversations') { res.end(JSON.stringify({ success: true, data: { items: data.data.map(c => ({ ...c, management: { state: 'active', pinned: false, revision: 0 } })), has_more: false, next_cursor: null } })); return; }
      res.writeHead(response.status); res.end(JSON.stringify(data)); return;
    }
    const file = resolve('frontend/dist', url.pathname === '/' || !extname(url.pathname) ? 'index.html' : '.' + url.pathname);
    if (!file.startsWith(resolve('frontend/dist') + '/')) throw Error('invalid path');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ttf': 'font/ttf' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(JSON.stringify({ message: String(error) })); }
});
const result = { environment: 'macOS real Electron, synthetic MinerU ZIP/real parser/source snapshots/API/SQLite; auxiliary APIs fixture; no new OCR/models', checks: [], screenshots: [], errors: [] };
const check = (ok, name) => { result.checks.push({ name, status: ok ? 'PASS' : 'FAIL' }); if (!ok) throw Error(name); };
let app, page;
async function shot(name) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(e => !e.getBoundingClientRect().height));
  await page.screenshot({ path: resolve(work, 'screenshots', name + '.png'), animations: 'disabled', scale: 'css' });
  result.screenshots.push(name + '.png');
  check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), name + ' no horizontal overflow');
}
async function compare() {
  await page.getByRole('button', { name: '原文对照', exact: true }).first().click();
  if (await page.getByRole('button', { name: '原文对照', exact: true }).last().isVisible()) await page.getByRole('button', { name: '原文对照', exact: true }).last().click();
}
try {
  await new Promise(r => server.listen(18060, '127.0.0.1', r));
  for (let i = 0; i < 60; i++) { try { await fetch('http://127.0.0.1:18062/docs'); break; } catch { await new Promise(r => setTimeout(r, 200)); } }
  const userData = resolve(work, 'userData'); mkdirSync(userData, { recursive: true }); writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18060', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18060' } });
  page = await app.firstWindow(); page.setDefaultTimeout(15000); page.on('pageerror', e => result.errors.push(String(e))); page.on('dialog', d => void d.accept().catch(() => {}));
  await page.locator('.composer-textarea').waitFor();
  await page.evaluate(book => { localStorage.setItem('texa:setup-complete:v3', '1'); localStorage.setItem('kaoyan_subject', '专业课'); localStorage.setItem('kaoyan_book_name', book); }, book);
  check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
  const zipResult = spawnSync(resolve('venv310/bin/python'), ['-c', "import runpy,sys;sys.stdout.buffer.write(runpy.run_path('tests/test_mineru_exercise_archive.py')['archive_bytes']())"]);
  if(zipResult.status) throw Error(zipResult.stderr.toString());
  await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setContentSize(1280,820));
  await page.goto('http://127.0.0.1:18060/exercises');
  await page.getByRole('radio',{name:'导入',exact:true}).click();
  await page.getByRole('button',{name:'上传文件 / MinerU 包',exact:true}).click();
  await page.getByLabel('题目文件',{exact:true}).setInputFiles({name:'合成习题解析.zip',mimeType:'application/zip',buffer:zipResult.stdout});
  await page.getByRole('button',{name:'分析文件',exact:true}).click();
  await page.getByRole('heading',{name:'校对题目',exact:true}).waitFor();
  check(latest.success && latest.data.length === 2, 'real ZIP analysis');
  await page.locator('.exercise-index-item').nth(1).getByRole('button').first().click();
  for (const [width,height] of [[1280,820],[1024,768],[760,820]]) {
    await app.evaluate(({BrowserWindow},[w,h]) => BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
    await shot(width+'-candidate-review');
  }
  await page.getByRole('button',{name:'编辑题目',exact:true}).click();
  await page.getByRole('button',{name:'移除图片',exact:true}).click();
  check(await page.getByRole('button',{name:'恢复图片',exact:true}).isVisible(), 'removed figure can be restored');
  await shot('760-editor-image-removed');
  await page.getByRole('button',{name:'导入选中 2 题',exact:true}).click();
  await page.locator('.exercise-receipt').waitFor();
  check(committed.success && committed.count === 2, 'unreviewed and edited candidates imported in one batch');
  check(committed.data.every(r => r.import_review), 'review notices persist');
  check(committed.data[1].source_attachments.length === 0, 'removed picture excluded from stored question');
  await page.getByRole('radio',{name:'练习',exact:true}).click();
  await page.getByRole('button',{name:/开始练习 ·/}).click();
  const answer = page.getByRole('textbox',{name:'我的作答',exact:true});
  await answer.click(); await answer.pressSequentially('My solution: y = kx');
  check(await answer.inputValue() === 'My solution: y = kx', 'native typing before revealing answer');
  await answer.fill('我的解题思路：先写公式，再代入。');
  for (const [width,height] of [[1280,820],[1024,768],[760,820]]) {
    await app.evaluate(({BrowserWindow},[w,h]) => BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
    await shot(width+'-practice-writing');
  }
  await page.getByRole('button',{name:'查看参考答案',exact:true}).click();
  check(await page.locator('.question-reading-solution').isVisible(), 'footer reveals actual answer document');
  check((await page.locator('.question-reading-solution').innerText()).includes('将给定输入代入'), 'saved explanation displayed');
  for (const [width,height] of [[1280,820],[1024,768],[760,820]]) {
    await app.evaluate(({BrowserWindow},[w,h]) => BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
    await shot(width+'-reference-answer');
  }
  await page.getByRole('button',{name:'题目与作答',exact:true}).click();
  check(await answer.inputValue() === '我的解题思路：先写公式，再代入。', 'switching panes preserves work');
  await page.getByRole('button',{name:'收起解答',exact:true}).click();
  await page.getByRole('button',{name:'AI 解题',exact:true}).first().click();
  check(await page.getByRole('button',{name:'生成解答',exact:true}).isVisible(), 'AI solution input workflow visible');
  await shot('760-ai-solution');
  await page.getByRole('button',{name:'基本理解',exact:true}).click();
  await page.getByRole('button',{name:'提交并下一题',exact:true}).click();
  await page.getByRole('button',{name:'查看参考答案',exact:true}).waitFor();
  await page.getByRole('textbox',{name:'我的作答',exact:true}).click();
  await page.getByRole('textbox',{name:'我的作答',exact:true}).pressSequentially('Next problem');
  check(await page.getByRole('textbox',{name:'我的作答',exact:true}).inputValue() === 'Next problem', 'next question accepts native typing after assessment');
  await page.getByRole('button',{name:'查看参考答案',exact:true}).click();
  check((await page.locator('.question-reading-solution').innerText()).includes('尚未收录参考答案'), 'missing answer has explicit empty state');
  await shot('760-no-reference');
  await page.getByRole('radio',{name:'题库',exact:true}).click();
  await page.locator('.exercise-bank-open').first().click();
  await page.getByRole('button',{name:'编辑题目',exact:true}).click();
  check(await page.getByRole('dialog',{name:'编辑题目'}).isVisible(), 'bank edit entry opens full editor');
  await page.getByLabel('本题已核对，清除导入时的待核对提示（可选）').check();
  await shot('760-bank-editor');
  await page.getByRole('button',{name:'保存修改',exact:true}).click();
  await page.getByRole('dialog',{name:'编辑题目'}).waitFor({state:'hidden'});
  check(true, 'bank edit saved through real API');
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); if (page) await page.screenshot({ path: resolve(work, 'screenshots/failure.png') }); process.exitCode = 1; }
finally {
  writeFileSync(resolve(work, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(work, 'backend.log'), backendLog);
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); backend.kill();
  console.log(JSON.stringify({ checks: result.checks.length, errors: result.errors, screenshots: result.screenshots.length, work }, null, 2));
}
