const {_electron: electron} = require('/Users/jichengqian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base='http://127.0.0.1:18775';
let backend, app;
async function boot() {
 backend=spawn('/Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python',['/private/tmp/texa_restart_desktop.py'],{cwd:'/private/tmp/texa-checkpoint-acceptance',stdio:['ignore',fs.openSync('/private/tmp/texa-acceptance-results/restart-backend.log','a'),fs.openSync('/private/tmp/texa-acceptance-results/restart-backend.log','a')]});
 for(let i=0;i<100;i++){try{if((await fetch(base+'/health')).ok) return;}catch{}await new Promise(r=>setTimeout(r,100));}
 throw Error('Backend did not start');
}
async function open() {
 app=await electron.launch({executablePath:'/Users/jichengqian/Documents/ChatGPT/texa/desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron',args:['/private/tmp/texa-checkpoint-acceptance/desktop'],env:{...process.env,KAOYAN_USER_DATA_DIR:'/private/tmp/texa-final-restart/userData',KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base},timeout:30000});
 const page=await app.firstWindow();await page.waitForURL(base+'/**');
 await page.route('**/api/system/settings',async route=>{const response=await route.fetch();const data=await response.json();data.data.models.credentials.reasoning.required=false;await route.fulfill({response,json:data});});
 await page.evaluate(()=>localStorage.setItem('texa:setup-complete:v3','1'));await page.goto(base+'/goals');
 return page;
}
async function data(gid){return (await (await fetch(base+'/api/goals/'+gid+'/runtime')).json()).data;}
async function stop(){const exited=once(backend,'exit');backend.kill('SIGTERM');await exited;backend=null;}
async function main(){
 await boot();let page=await open();
 for(const kind of ['expired','unknown']) {
  await page.getByRole('button',{name:new RegExp(kind+' 审批边界')}).click();
  await page.getByText(kind==='expired'?'已过期，不能确认':'写入结果未知，需核对记录；不可再次执行',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'确认执行',exact:true}).count(),0);
  await page.screenshot({path:'/private/tmp/texa-acceptance-results/electron-'+kind+'.png'});
  console.log('PASS '+kind+' has no confirmation entry');
 }
 await page.getByRole('button',{name:/Electron 停止与重启验证/}).click();
 await page.getByRole('button',{name:'开始执行',exact:true}).click();
 await page.getByText('当前任务 · 正在执行',{exact:true}).waitFor();
 const before=await data('g_stop');assert.equal(before.status,'running');
 await app.close();app=null;await stop();
 await boot();page=await open();
 await page.getByRole('button',{name:/Electron 停止与重启验证/}).click();
 await page.getByRole('button',{name:'继续执行',exact:true}).waitFor();
 const after=await data('g_stop');assert.equal(after.status,'interrupted');assert.equal(after.active_run_id,before.active_run_id);
 await page.screenshot({path:'/private/tmp/texa-acceptance-results/electron-restart.png'});
 console.log('PASS backend and Electron restarted; same run interrupted, explicit resume available');
}
main().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(app)await app.close();if(backend)await stop();});
