/** Isolated Electron textbook upload + real ONNX/Chroma; no LLM/OCR calls. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const book = '合成题库';
const work = resolve(process.env.TEXA_INDEX_QA_WORK || `artifacts/index-input-p0-2026-10-27/electron-${Date.now()}`);
mkdirSync(resolve(work, 'screenshots'), { recursive: true });
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18861' }, stdio: 'ignore' });
const backend = spawn(resolve('venv310/bin/python'), ['docs/validation/index-input-p0-2026-10-27/electron_server.py'], { env: { ...process.env, TEXA_INDEX_QA_WORK: work }, stdio: ['ignore', 'pipe', 'pipe'] });
let backendLog = '', latest;
backend.stdout.on('data', d => backendLog += d); backend.stderr.on('data', d => backendLog += d);
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const chunks = []; for await (const chunk of req) chunks.push(chunk); const body = Buffer.concat(chunks);
    if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
      res.setHeader('Content-Type', 'application/json');
      if (url.pathname === '/api/system/settings/subjects') { res.end(JSON.stringify({ success: true, data: { subjects: [{ name: '专业课', children: [] }] } })); return; }
      const target = url.pathname.startsWith('/api/books/') ? '18862' : '18861';
      const response = await fetch(`http://127.0.0.1:${target}${req.url}`, { method: req.method, headers: { 'Content-Type': req.headers['content-type'] || 'application/json' }, ...(body.length ? { body } : {}) });
      if(url.pathname.includes('/file-sources/')) { res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'application/octet-stream' }); res.end(Buffer.from(await response.arrayBuffer())); return; }
      const data = await response.json();
      if (url.pathname.startsWith('/api/books/import-jobs/') && data.data?.status === 'completed') latest = data.data;
      if (url.pathname === '/api/chat/conversations') { res.end(JSON.stringify({ success: true, data: { items: data.data.map(c => ({ ...c, management: { state: 'active', pinned: false, revision: 0 } })), has_more: false, next_cursor: null } })); return; }
      res.writeHead(response.status); res.end(JSON.stringify(data)); return;
    }
    const file = resolve('frontend/dist', url.pathname === '/' || !extname(url.pathname) ? 'index.html' : '.' + url.pathname);
    if (!file.startsWith(resolve('frontend/dist') + '/')) throw Error('invalid path');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ttf': 'font/ttf' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(JSON.stringify({ message: String(error) })); }
});
const result = { environment: 'macOS real Electron, real textbook upload/job, ONNX FP32/Chroma and release gate; auxiliary APIs fixture; no LLM/OCR', checks: [], screenshots: [], errors: [] };
const check = (ok, name) => { result.checks.push({ name, status: ok ? 'PASS' : 'FAIL' }); if (!ok) throw Error(name); };
let app, page;
async function shot(name) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(e => !e.getBoundingClientRect().height));
  await page.screenshot({ path: resolve(work, 'screenshots', name + '.png'), animations: 'disabled', scale: 'css' });
  result.screenshots.push(name + '.png');
  check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), name + ' no horizontal overflow');
}
try {
  await new Promise(r => server.listen(18860, '127.0.0.1', r));
  for (let i = 0; i < 60; i++) { try { await fetch('http://127.0.0.1:18862/docs'); break; } catch { await new Promise(r => setTimeout(r, 200)); } }
  const userData = resolve(work, 'userData'); mkdirSync(userData, { recursive: true }); writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18860', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18860' } });
  page = await app.firstWindow(); page.setDefaultTimeout(15000); page.on('pageerror', e => result.errors.push(String(e))); page.on('dialog', d => void d.accept().catch(() => {}));
  await page.locator('.composer-textarea').waitFor();
  await page.evaluate(book => { localStorage.setItem('texa:setup-complete:v3', '1'); localStorage.setItem('kaoyan_subject', '专业课'); localStorage.setItem('kaoyan_book_name', book); }, book);
  check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
  const zipResult = spawnSync(resolve('venv310/bin/python'), ['-c', "import runpy,json,io,zipfile,sys;p=runpy.run_path('docs/validation/index-input-p0-2026-10-27/validate_hybrid.py')['payload'](True);b=io.BytesIO();z=zipfile.ZipFile(b,'w');z.writestr('structured_content.json',json.dumps(p,ensure_ascii=False));z.close();sys.stdout.buffer.write(b.getvalue())"]);
  if(zipResult.status) throw Error(zipResult.stderr.toString());
  for(const [width,height] of [[1280,820],[1024,768],[760,820]]) {
    latest = null;
    await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
    await page.goto('http://127.0.0.1:18860/books/import');
    await page.locator('input[type=file][accept*=zip]').setInputFiles({name:`通用输入合同验收${width}.zip`,mimeType:'application/zip',buffer:zipResult.stdout});
    await page.getByRole('button',{name:'导入输出包',exact:true}).click();
    await page.getByRole('button',{name:'查看教材状态',exact:true}).waitFor({timeout:120000});
    check(latest?.status==='completed','real import job completed '+width);
    const name=latest.result.name;
    const manifest=JSON.parse(readFileSync(resolve(work,'data/vector_db/_index_manifests',name+'.json'),'utf8'));
    check(manifest.embedding_integrity.silent_truncations===0,'no embedding truncation '+width);
    check(manifest.source_integrity.span_errors===0,'source spans checked '+width);
    check(manifest.vector_count>manifest.chunk_count,'multiple bounded vectors '+width);
    check(manifest.release_quality.status==='passed','production evidence gate '+width);
    check(manifest.embedding_contract.max_length===512,'runtime identity bound '+width);
    await shot(width+'-real-import-completed');
  }
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); if (page) await page.screenshot({ path: resolve(work, 'screenshots/failure.png') }); process.exitCode = 1; }
finally {
  writeFileSync(resolve(work, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(work, 'backend.log'), backendLog);
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); backend.kill();
  console.log(JSON.stringify({ checks: result.checks.length, errors: result.errors, screenshots: result.screenshots.length, work }, null, 2));
}
