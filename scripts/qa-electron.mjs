/** macOS real shell smoke with disposable userData and external fixture backend. */
import {createRequire} from 'node:module';import{mkdirSync,writeFileSync}from'node:fs';import{resolve}from'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');const out=resolve('docs/qa/evidence/electron');mkdirSync(out,{recursive:true});
const userData='/tmp/texa-full-qa-electron';mkdirSync(userData,{recursive:true});writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
let app,page;const result={fixture:true,checks:[],errors:[]};
try{app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
 page=await app.firstWindow();await page.locator('.composer-textarea').waitFor({timeout:30000});await page.waitForLoadState('networkidle');
 result.checks.push({case:'actual Electron preload/workspace',status:await page.evaluate(()=>window.kaoyanDesktop?.isElectron)?'PASS':'FAIL'});
 await page.getByRole('link',{name:'笔记',exact:true}).click();await page.getByRole('heading',{name:'笔记',exact:true}).waitFor();await page.screenshot({path:resolve(out,'notes.png')});
 await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByText('主题色',{exact:true}).waitFor();await page.screenshot({path:resolve(out,'settings.png')});
 await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});result.checks.push({case:'navigation→settings→Escape',status:'PASS'});
 await app.close();app=null;result.checks.push({case:'graceful shell close',status:'PASS'});
}catch(e){result.errors.push(String(e));if(page){result.body=await page.locator('body').innerText();await page.screenshot({path:resolve(out,'failure.png')});}process.exitCode=1;}finally{await app?.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
