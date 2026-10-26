/** Real Electron renderer, isolated HTTP fixtures and userData; no user data or models. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const out = resolve('docs/qa/settings-history-motion-2026-10-26');
mkdirSync(out, { recursive: true });
const requests = [], checks = [], errors = [], timing = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const fixture = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: '18292' }, stdio: 'ignore' });
const item = (view, i) => ({ id: `${view}-${i}`, title: `${view === 'active' ? '最近' : '回收站'}记录${i}：用几何意义理解定积分与连续函数`, subject: '数学/高数', book_name: '', updated_at: '2026-10-26T10:00:00Z', message_count: 2, management: { state: view, pinned: i === 0, revision: 0 } });
let failList = false;
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost'), path = url.pathname;
    const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ success: true, data })); };
    if (path.startsWith('/api/')) requests.push({ path: req.url, method: req.method });
    if (path === '/api/chat/conversations') {
      await wait(400);
      if (failList) { failList = false; res.writeHead(503, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ success: false, message: '隔离测试：列表暂时不可用' })); return; }
      const view = url.searchParams.get('view') || 'active', more = url.searchParams.has('cursor');
      return reply({ items: view === 'archived' ? [] : Array.from({ length: more ? 2 : 3 }, (_, i) => item(view, i + (more ? 3 : 0))), has_more: view === 'active' && !more, next_cursor: view === 'active' && !more ? 'fixture-next' : null });
    }
    if (/^\/api\/chat\/conversations\/active-\d$/.test(path)) return reply({ id: path.split('/').at(-1), subject: '数学/高数', book_name: '', messages: [{ id: 'qa-q', role: 'user', content: '用几何意义理解定积分' }, { id: 'qa-a', role: 'assistant', content: '定积分将区间上的函数值累加。\n\n$$\\int_a^b f(x)\\,dx.$$' }], page: { limit: 40, total: 2, has_more: false } });
    if (path.endsWith('/management')) return reply({ state: 'active', pinned: false, revision: 0 });
    if (path === '/api/focus') return reply({ revision: 0, runtime_id: 'qa', snapshot_sequence: 1, tasks: [], next_offset: null, current_task: null, current_session: null, next_task: null, goal_stats: [], status: 'idle', active_ms: 0, remaining_seconds: null, server_time: Date.now()/1000 });
    if (path === '/api/system/backups') return reply({ items: [], backup_path: '/isolated/backups' });
    if (path.startsWith('/api/') || path === '/health') {
      const r = await fetch('http://127.0.0.1:18292' + req.url, { method: req.method, ...(req.method === 'POST' ? { body: '{}' } : {}) });
      res.writeHead(r.status, { 'Content-Type': 'application/json' }); res.end(await r.text()); return;
    }
    const file = resolve('frontend/dist', extname(path) ? '.'+path : 'index.html');
    if (!file.startsWith(resolve('frontend/dist')+'/')) return res.writeHead(403).end();
    res.setHeader('Content-Type', ({ '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.woff2':'font/woff2', '.ttf':'font/ttf', '.svg':'image/svg+xml', '.png':'image/png' })[extname(file)] || 'application/octet-stream'); res.end(readFileSync(file));
  } catch(e) { res.writeHead(500).end(String(e)); }
});
let app, page;
const check = (pass, name) => { checks.push({ name, pass: !!pass }); if (!pass) throw Error(name); };
const shot = name => page.screenshot({ path: resolve(out, name+'.png'), animations: 'disabled', scale: 'css' });
const activePanel = () => page.locator('.persistent-route-panel:not([hidden])');
async function openNav() {
  if (await page.locator('.app-shell').getAttribute('data-navigation') === 'closed') {
    await page.getByRole('button', { name:'展开侧栏', exact:true }).click(); await wait(230);
  }
}
async function go(path) { await page.goto('http://127.0.0.1:18291'+path); await page.locator('.app-shell').waitFor(); await page.evaluate(()=>document.fonts.ready); }
async function frame() { await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))); }
try {
  await new Promise(r=>server.listen(18291,'127.0.0.1',r));
  for(let n=0;n<40;n++){try{await fetch('http://127.0.0.1:18292/health');break;}catch{await wait(100);}}
  const userData=mkdtempSync('/private/tmp/texa-settings-motion-'); writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
  app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18291',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18291'}});
  page=await app.firstWindow();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(JSON.stringify({message:e.message,stack:e.stack,url:page.url()})));await page.locator('.app-shell').waitFor();await page.emulateMedia({reducedMotion:'no-preference'});
  for(const [w,h] of [[1280,820],[1024,768],[760,820]]){
    await app.evaluate(({BrowserWindow},size)=>BrowserWindow.getAllWindows()[0].setContentSize(...size),[w,h]);
    await go('/'); await openNav();
    await page.locator('.context-session-entry').first().waitFor();
    await shot(`${w}-history`);
    await page.getByRole('button',{name:'归档',exact:true}).click();
    check(await page.getByRole('status',{name:'正在读取会话',exact:true}).isVisible(),`${w} uncached archive uses skeleton`);
    check(await page.locator('.context-session-entry').count()===0,`${w} switching view never shows previous rows`);
    await shot(`${w}-skeleton`);
    await page.getByText('当前范围暂无会话',{exact:true}).waitFor();
    const count=requests.filter(r=>r.path.startsWith('/api/chat/conversations?')).length;
    const t=Date.now(); await page.getByRole('button',{name:'最近',exact:true}).click();
    await page.locator('.context-session-entry').first().waitFor(); timing.push({width:w,cached_return_ms:Date.now()-t});
    check(await page.locator('.history-list-skeleton').count()===0,`${w} cached recent rows show immediately`);
    check(requests.filter(r=>r.path.startsWith('/api/chat/conversations?')).length===count,`${w} cached tab avoids repeated HTTP`);
    await page.getByRole('button',{name:'加载更多会话',exact:true}).click();
    await page.locator('.context-session-entry').nth(4).waitFor();
    await page.getByRole('button',{name:'归档',exact:true}).click();await page.getByText('当前范围暂无会话',{exact:true}).waitFor();
    await page.getByRole('button',{name:'最近',exact:true}).click();
    check(await page.locator('.context-session-entry').count()===5,`${w} paginated rows survive switching tabs`);
    await page.locator('.context-session-row').first().click();await page.locator('.learning-question').waitFor();
    if(w<920)await openNav();
    if(w<=760)await page.locator('.navigation-domains').evaluate(el=>{el.open=true;});
    await page.getByRole('link',{name:'教材',exact:true}).click();await activePanel().locator('.library-book-row').first().waitFor();
    await openNav();
    const aligned=await page.evaluate(()=>{
      const a=document.querySelector('.navigation-collapse').getBoundingClientRect(), b=document.querySelector('.persistent-route-panel:not([hidden]) .app-page-header').getBoundingClientRect();return Math.abs(a.y+a.height/2-b.y-b.height/2)<1;
    });check(aligned,`${w} collapse button shares header center`);
    const full=await page.locator('.study-navigation').evaluate(el=>el.getBoundingClientRect().width);
    await page.getByRole('button',{name:'收起侧栏',exact:true}).click();await frame();
    const mid=await page.locator('.study-navigation').evaluate(el=>({width:el.getBoundingClientRect().width,running:el.getAnimations().some(a=>a.playState==='running')}));
    check(mid.running&&mid.width>0&&mid.width<full,`${w} collapse has an actual intermediate animated width`);
    await wait(240);
    check(await page.locator('.study-navigation').evaluate(el=>el.getBoundingClientRect().width)<1,`${w} collapsed navigation occupies no width`);
    check(await page.locator('.app-rail').evaluate(el=>el.inert),`${w} collapsed navigation excluded from keyboard focus`);
    check(await page.evaluate(()=>{const a=document.querySelector('.context-sidebar-trigger').getBoundingClientRect(),b=document.querySelector('.persistent-route-panel:not([hidden]) .app-page-header').getBoundingClientRect();return Math.abs(a.y+a.height/2-b.y-b.height/2)<1;}),`${w} expand button shares header center`);
    await shot(`${w}-collapsed`);await openNav();
    if(w<=760)await page.locator('.navigation-domains').evaluate(el=>{el.open=true;});
    await page.getByRole('button',{name:'设置',exact:true}).click();await frame();
    check(await page.locator('.settings-dialog').evaluate(el=>el.getAnimations().some(a=>a.effect.getKeyframes().some(f=>Number(f.opacity)<1))),`${w} settings opening animates`);
    await page.getByRole('button',{name:'数据与教材',exact:true}).click();await frame();
    check(await page.locator('.settings-content-pane').evaluate(el=>el.getAnimations().some(a=>a.effect.getKeyframes().some(f=>Number(f.opacity)<1))),`${w} settings tab animates`);
    check(await page.getByText('MinerU API URL',{exact:true}).count()===0 && await page.getByText('保存解析配置',{exact:true}).count()===0,`${w} parser API and CLI configuration removed`);
    await page.getByText('建议先用 MinerU 解析教材，再导入包含 Markdown 和图片的 ZIP 压缩包。',{exact:true}).waitFor();
    await wait(220);await shot(`${w}-settings-data`);
    check(await page.locator('.settings-dialog').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&el.scrollWidth<=el.clientWidth;}),`${w} settings fits viewport`);
    await page.keyboard.press('Escape');await page.getByRole('dialog',{name:'设置',exact:true}).waitFor({state:'hidden'});
    await page.getByRole('button',{name:'设置',exact:true}).click();await frame();
    check(await page.locator('.settings-dialog').evaluate(el=>el.getAnimations().some(a=>a.effect.getKeyframes().some(f=>Number(f.opacity)<1))),`${w} retained settings replays opening animation`);
    await page.keyboard.press('Escape');
  }
  await page.emulateMedia({reducedMotion:'reduce'}); await openNav();await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('button',{name:'偏好',exact:true}).click();await frame();
  check(await page.locator('.settings-dialog').evaluate(el=>el.getAnimations({subtree:true}).filter(a=>a.playState==='running').length===0),'reduced motion disables dialog and settings pane animation');await page.keyboard.press('Escape');
  await go('/books/import');await page.getByRole('radio',{name:'MinerU 输出包（推荐）',exact:true}).waitFor();
  check(await page.getByRole('radio',{name:'MinerU 输出包（推荐）',exact:true}).getAttribute('aria-checked')==='true','textbook import defaults to recommended bundle');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1280,820));await go('/');await openNav();await page.locator('.context-session-entry').first().waitFor();
  failList=true;await page.evaluate(()=>window.dispatchEvent(new CustomEvent('conversations:changed',{detail:{id:'active-0',management:{state:'active',pinned:true,revision:1}}})));await page.getByText('隔离测试：列表暂时不可用',{exact:true}).waitFor();
  check(await page.locator('.context-session-entry').count()===3,'refresh failure retains existing rows and exposes error');
  await page.getByRole('button',{name:'重新读取',exact:true}).click();await page.getByText('隔离测试：列表暂时不可用',{exact:true}).waitFor({state:'hidden'});
  await wait(500);await page.getByRole('button',{name:'归档',exact:true}).click();await page.getByRole('button',{name:'最近',exact:true}).click();await wait(500);
  check(await page.locator('.context-session-entry').count()===3 && !(await page.locator('.context-session-list').innerText()).includes('当前范围暂无会话'),'late archive response cannot overwrite recent rows');
  await page.getByRole('button',{name:'收起侧栏',exact:true}).click();await page.getByRole('button',{name:'展开对话历史',exact:true}).click();await page.locator('.learning-context-sidebar[data-floating="true"]').waitFor({state:'visible'});
  check(await page.locator('.learning-context-sidebar[data-floating="true"] .context-session-entry').count()===3,'collapsed learning retains floating history access');await shot('floating-history');
  check(errors.length===0,'no renderer errors');
} catch(e) { errors.push(String(e)); if(page)await shot('failure');process.exitCode=1; }
finally {writeFileSync(resolve(out,'electron-results.json'),JSON.stringify({platform:'real macOS Electron; isolated HTTP fixtures; 400ms simulated list latency; no Windows/native phone or live backend latency claim',checks,timing,errors,requests},null,2));if(app)await app.close();await new Promise(r=>server.close(r));fixture.kill();}
console.log(JSON.stringify({checks:checks.length,errors,timing}));
