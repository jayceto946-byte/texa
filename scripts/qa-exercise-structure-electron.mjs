/** Isolated real Electron + file parsing/API/SQLite. No model/OCR calls. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const work = resolve(process.env.TEXA_STRUCTURE_QA_WORK || `artifacts/exercise-structure-2026-10-26/electron-${Date.now()}`);
mkdirSync(resolve(work, 'screenshots'), { recursive: true });
const book = '传感器原理及应用';
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18061' }, stdio: 'ignore' });
const backend = spawn(resolve('venv310/bin/python'), ['scripts/qa-question-candidate-server.py'], { env: { ...process.env, TEXA_QC_QA_WORK: work }, stdio: ['ignore', 'pipe', 'pipe'] });
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
      const data = await response.json();
      if (url.pathname === '/api/exercises/upload-analyze') latest = data;
      if (url.pathname === '/api/exercises/candidates/batch-add') committed = data;
      if (url.pathname === '/api/chat/conversations') { res.end(JSON.stringify({ success: true, data: { items: data.data.map(c => ({ ...c, management: { state: 'active', pinned: false, revision: 0 } })), has_more: false, next_cursor: null } })); return; }
      res.writeHead(response.status); res.end(JSON.stringify(data)); return;
    }
    const file = resolve('frontend/dist', url.pathname === '/' || !extname(url.pathname) ? 'index.html' : '.' + url.pathname);
    if (!file.startsWith(resolve('frontend/dist') + '/')) throw Error('invalid path');
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ttf': 'font/ttf' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch (error) { res.writeHead(500); res.end(JSON.stringify({ message: String(error) })); }
});
const result = { environment: 'macOS real Electron, real DOCX parser/source snapshots/API/SQLite; auxiliary APIs fixture; no new OCR/models', checks: [], screenshots: [], errors: [] };
const check = (ok, name) => { result.checks.push({ name, status: ok ? 'PASS' : 'FAIL' }); if (!ok) throw Error(name); };
let app, page;
async function shot(name) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(e => !e.getBoundingClientRect().height));
  await page.screenshot({ path: resolve(work, 'screenshots', name + '.png'), animations: 'disabled', scale: 'css' });
  result.screenshots.push(name + '.png');
  check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), name + ' no horizontal overflow');
}
function docx(text) {
  const code = 'import sys,json,io,zipfile;from xml.sax.saxutils import escape\nt=json.load(sys.stdin);b=io.BytesIO()\nwith zipfile.ZipFile(b,"w") as z:z.writestr("word/document.xml",\'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>\'+"".join("<w:p><w:r><w:t>"+escape(s)+"</w:t></w:r></w:p>" for s in t.splitlines())+"</w:body></w:document>")\nsys.stdout.buffer.write(b.getvalue())';
  const result = spawnSync(resolve('venv310/bin/python'), ['-c', code], { input: JSON.stringify(text) });
  if (result.status) throw Error(result.stderr.toString());
  return result.stdout;
}
async function setup(text) {
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.once('will-prevent-unload', e => e.preventDefault()));
  await page.goto('http://127.0.0.1:18060/exercises');
  await page.getByRole('radio', { name: '导入', exact: true }).click();
  await page.getByRole('button', { name: '上传 Word / PDF', exact: true }).click();
  await page.getByLabel('题目文件', { exact: true }).setInputFiles({ name: '结构验证.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: docx(text) });
  await page.getByRole('button', { name: '分析文件', exact: true }).click();
  await page.getByRole('heading', { name: '校对候选题', exact: true }).waitFor();
  check(latest.success && latest.candidate_contract_version === 1, 'real file analysis v1');
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
  const normal = '二、矩阵\n#047 矩阵 → 伴随等于转置/本身 2005数三\n(12) 设三阶矩阵满足给定条件，求其元素。A. 1 B. 2 C. 3 D. 4\n答案：A\n解析：由给定矩阵条件进行推导。\n#048 矩阵 → 不可逆的判定与证明 2006数三\n(12) 证明给定矩阵不可逆，并说明所用性质。';
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820]]) {
    await app.evaluate(({ BrowserWindow }, [w, h]) => BrowserWindow.getAllWindows()[0].setContentSize(w, h), [width, height]);
    await setup(normal);
    check(await page.locator('.exercise-index-item').count() === 2, '# IDs retain two original (12) questions ' + width);
    check((await page.locator('.exercise-source-structure').innerText()).includes('#047'), 'catalog metadata visible ' + width);
    check((await page.locator('.exercise-candidate-answer').innerText()).includes('答案：A'), 'answer visibly separated ' + width);
    check((await page.locator('.exercise-question').innerText()).includes('(12)') && !(await page.locator('.exercise-question').innerText()).includes('解析：'), 'original number preserved and source solution excluded ' + width);
    await shot(width + '-catalog-answer');
    await compare(); await shot(width + '-source');
  }
  // Learn a new explicit solution heading through a source span, not free text.
  await setup('例题1 已知给定矩阵😀，求它的秩。演算过程：根据原文条件消元得到结果。');
  check(latest.data[0].projection.method === 'unresolved', 'unseen label stays unresolved');
  await compare();
  const block = latest.extract.source_blocks.find(b => b.text.includes('演算过程'));
  await page.locator('.exercise-source-assignment > summary').first().click();
  const area = page.getByRole('textbox', { name: '来源文字 ' + block.block_id, exact: true });
  await area.focus(); await area.evaluate(el => el.setSelectionRange(el.value.indexOf('演算过程'), el.value.indexOf('演算过程')));
  await page.getByRole('button', { name: '分配光标后的本块文字', exact: true }).first().click();
  await shot('760-source-cursor-boundary');
  await page.getByRole('button', { name: '候选题', exact: true }).click();
  await page.locator('.exercise-content-issue select').first().selectOption('corrected');
  await page.getByRole('button', { name: '确认本题结构', exact: true }).click(); await page.getByText('已确认当前版本', { exact: true }).waitFor();
  check((await page.locator('.exercise-candidate-explanation').innerText()).includes('演算过程'), 'manual source span separates solution');
  await page.getByRole('button', { name: '记住本题分离方式', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '已保存本地分离样例' }).waitFor();
  await shot('760-confirmed-sample');
  await setup('二、矩阵\n＃169 矩阵 → 求秩 2008数二\n(7) 对另一道给定矩阵题，求其秩。\n演算过程：使用另一份资料的原解。');
  check(latest.data[0].explanation.includes('演算过程'), 'sample reused on another source');
  check(latest.data[0].issues.some(i => i.code === 'learned_boundary'), 'reused sample requires current review');
  check(await page.getByRole('button', { name: '确认入库0题', exact: true }).isDisabled(), 'learned proposal cannot silently enter bank');
  await page.locator('.exercise-content-issue select').first().selectOption('source_checked');
  await page.getByRole('button', { name: '确认本题结构', exact: true }).click(); await page.getByText('已确认当前版本', { exact: true }).waitFor();
  await shot('760-learned-proposal');
  await page.getByRole('button', { name: '确认入库1题', exact: true }).click(); await page.locator('.exercise-receipt').waitFor();
  check(committed.success && committed.data[0].source_structure.catalog_number === '#169', 'real batch persists catalog metadata');
  check(committed.data[0].explanation.includes('另一份资料'), 'real batch persists source solution');
  check(committed.candidate_receipts[0].review_kind === 'user_confirmed', 'review receipt persisted atomically');
  await shot('760-import-receipt');
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); if (page) await page.screenshot({ path: resolve(work, 'screenshots/failure.png') }); process.exitCode = 1; }
finally {
  writeFileSync(resolve(work, 'results.json'), JSON.stringify(result, null, 2)); writeFileSync(resolve(work, 'backend.log'), backendLog);
  await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); server.close(); upstream.kill(); backend.kill();
  console.log(JSON.stringify({ checks: result.checks.length, errors: result.errors, screenshots: result.screenshots.length, work }, null, 2));
}
