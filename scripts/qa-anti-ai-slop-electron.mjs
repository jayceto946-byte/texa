/** Real macOS Electron, disposable userData, same offline fixture as route audit. */
import{createRequire}from'node:module';import{mkdirSync,writeFileSync}from'node:fs';import{resolve}from'node:path';
const{_electron}=createRequire(import.meta.url)('playwright');
export async function auditNativeShell({out,routes,results}){
 const userData='/tmp/texa-anti-ai-slop-electron';mkdirSync(userData,{recursive:true});writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 const app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18040',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18040'}});
 try{
  const page=await app.firstWindow();await page.locator('.composer-textarea').waitFor({timeout:30000});
  if(!await page.evaluate(()=>window.kaoyanDesktop?.isElectron))throw Error('native preload missing');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1280,820));
  for(const[name,path]of routes){await page.goto('http://127.0.0.1:18040'+path);await page.waitForLoadState('networkidle');await page.locator('.persistent-route-panel:not([hidden])').locator('h1,h2').first().waitFor();await page.locator('.persistent-route-panel:not([hidden]) .workspace-skeleton').waitFor({state:'hidden'});if(name==='settings')await page.getByRole('dialog').waitFor();await page.waitForTimeout(250);await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:resolve(out,`electron-${name}.png`)});const check=await page.evaluate(()=>({bodyWidth:document.body.scrollWidth,viewport:innerWidth,status:document.body.innerText.includes('页面文件未能加载')?'FAIL':'PASS'}));results.checks.push({name,state:'native-macos',...check});}
  await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});results.interactions.push('real Electron preload→19 routes→settings→Escape');
 }finally{await app.close();}
}
