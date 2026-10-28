/** Isolated real Electron + file parsing/API/SQLite. No model/OCR calls. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const work = resolve(process.env.TEXA_MINERU_EXERCISE_QA_WORK || `artifacts/mineru-exercise-2026-10-27/electron-${Date.now()}`);
mkdirSync(resolve(work, 'screenshots'), { recursive: true });
const book = '合成题库';
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18061' }, stdio: 'ignore' });
const backend = spawn(resolve('venv310/bin/python'), ['scripts/qa-mineru-exercise-server.py'], { env: { ...process.env, TEXA_QC_QA_WORK: work }, stdio: ['ignore', 'pipe', 'pipe'] });
let backendLog = '', latest;
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
      if(url.pathname.includes('/file-sources/')) { res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/octet-stream' }); res.end(Buffer.from(await response.arrayBuffer())); return; }
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
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, [w,h]) => BrowserWindow.getAllWindows()[0].setContentSize(w,h), [width,height]);
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.once('will-prevent-unload', e => e.preventDefault()));
    await page.goto('http://127.0.0.1:18060/exercises');
    await page.getByRole('radio', {name:'导入',exact:true}).click();
    await page.getByRole('button', {name:'上传文件 / MinerU 包',exact:true}).click();
    check((await page.getByLabel('题目文件',{exact:true}).getAttribute('accept')).includes('.zip'), 'ZIP picker '+width);
    await shot(width+'-source-setup');
    await page.getByLabel('题目文件',{exact:true}).setInputFiles({name:'合成习题解析.zip',mimeType:'application/zip',buffer:zipResult.stdout});
    await shot(width+'-zip-ready');
    await page.getByRole('button',{name:'分析文件',exact:true}).click();
    await page.getByRole('heading',{name:'校对候选题',exact:true}).waitFor();
    check(latest.success && latest.data.length===2 && latest.extract.provider==='file-source-units','real ZIP API two candidates '+width);
    check(latest.data[0].projection.structure.original_number==='2-1','chapter-prefixed number '+width);
    check((await page.locator('.exercise-candidate-explanation').innerText()).includes('解：'),'source solution separated '+width);
    await shot(width+'-zip-candidates');
    await page.locator('.exercise-index-item').nth(1).getByRole('button').click();
    await compare();
    await page.locator('.exercise-source-image img').waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('.exercise-source-image img')].every(i=>i.complete&&i.naturalWidth>0));
    check(await page.locator('.exercise-source-image img').count()===1,'persisted ZIP figure loaded '+width);
    check((await page.locator('.exercise-original').innerText()).includes('物理页 2'),'physical page retained '+width);
    await page.locator('.exercise-source-image img').scrollIntoViewIfNeeded();
    await shot(width+'-zip-source-image');
  }
  // Completion notice is a UI-only fixture; ZIP extraction above uses the real API.
  const pendingJob = {id:'qa-structure',status:'running',stage:'structure',progress:40,message:'结构检查',book_name:'合成教材'};
  await page.route('**/api/books/import-capabilities', route => route.fulfill({json:{success:true,data:{mineru:{configured:false,available:false,mode:'none',reason:'not_configured'},local_pdf:{available:true},output_bundle:{available:true}}}}));
  await page.route('**/api/books/import-mineru-output', route => route.fulfill({json:{success:true,job_id:'qa-structure',data:pendingJob}}));
  await page.route('**/api/books/import-jobs/qa-structure', route => route.fulfill({json:{success:true,data:{...pendingJob,status:'completed',stage:'completed',progress:100,result:{name:'合成教材',chapter_count:2,used_mineru:true,ingestion_report:{source_metadata:{structure_quality:{exercise_sections_without_units:['heading-one']}}}}}}}));
  for(const [width,height] of [[1280,820],[1024,768],[760,820]]) {
    await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
    await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.once('will-prevent-unload',e=>e.preventDefault()));
    await page.goto('http://127.0.0.1:18060/books/import');
    await page.locator('input[type=file][accept*=zip]').setInputFiles({name:'合成教材.zip',mimeType:'application/zip',buffer:zipResult.stdout});
    await page.getByRole('button',{name:'导入输出包',exact:true}).click();
    await page.getByText('结构检查发现 1 个习题范围尚未识别出题目。教材正文已保留用于检索，这些范围暂不能保证可抽题。',{exact:true}).waitFor();
    check(true,'automatic structure notice '+width);
    await shot(width+'-automatic-structure-notice');
  }
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); if (page) await page.screenshot({ path: resolve(work, 'screenshots/failure.png') }); process.exitCode = 1; }
finally {
  writeFileSync(resolve(work, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(work, 'backend.log'), backendLog);
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); backend.kill();
  console.log(JSON.stringify({ checks: result.checks.length, errors: result.errors, screenshots: result.screenshots.length, work }, null, 2));
}
