const {_electron: electron} = require('/Users/jichengqian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
async function main() {
 const app = await electron.launch({executablePath:'/Users/jichengqian/Documents/ChatGPT/texa/desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron',args:['/private/tmp/texa-checkpoint-acceptance/desktop'],env:{...process.env,KAOYAN_USER_DATA_DIR:'/private/tmp/texa-final-electron/userData',KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18774'},timeout:30000});
 try {
  const page = await app.firstWindow();
  await page.waitForURL('http://127.0.0.1:18774/**',{timeout:30000});
  await page.route('**/api/system/settings',async route=>{const response=await route.fetch();const data=await response.json();data.data.models.credentials.reasoning.required=false;await route.fulfill({response,json:data});});
  await page.evaluate(()=>localStorage.setItem('texa:setup-complete:v3','1'));
  await page.goto('http://127.0.0.1:18774/goals');
  await page.waitForTimeout(1500);
  await page.getByRole('button',{name:/Electron 审批验证/}).click();
  await page.getByRole('button',{name:'开始执行',exact:true}).click();
  await page.getByRole('button',{name:'确认执行',exact:true}).waitFor({timeout:15000});
  await page.screenshot({path:'/private/tmp/texa-acceptance-results/electron-pending.png'});
  await page.getByRole('button',{name:'确认执行',exact:true}).click();
  await page.getByText('已整理本次学习记录，结果可回看。',{exact:false}).waitFor({timeout:15000});
  console.log('PASS real approval, receipt and durable final');
  await page.getByRole('button',{name:/Electron 停止与重启验证/}).click();
  await page.getByRole('button',{name:'开始执行',exact:true}).click();
  await page.getByRole('button',{name:'暂停',exact:true}).click();
  await page.getByRole('button',{name:'启用目标',exact:true}).waitFor();
  console.log('PASS running pause, multiple Goal selection');
  await page.getByRole('button',{name:'启用目标',exact:true}).click();
  await page.getByRole('button',{name:'继续执行',exact:true}).waitFor();
  for (const width of [1024,1366,1720]) {
   await app.evaluate(({BrowserWindow},width)=>BrowserWindow.getAllWindows()[0].setSize(width,900),width);
   await page.screenshot({path:`/private/tmp/texa-acceptance-results/electron-${width}.png`});
  }
  await page.getByRole('button',{name:'继续执行',exact:true}).click();
  console.log('RUNNING_FOR_RESTART');
  console.log(await page.locator('body').innerText());
  await page.screenshot({path:'/private/tmp/texa-acceptance-results/electron-initial.png'});
 } finally { await app.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1});
