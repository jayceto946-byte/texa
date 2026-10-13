/** Read-only Electron restore of persisted real paid answers; no generation. */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');
const out=resolve('docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored');mkdirSync(out,{recursive:true});
const userData='/private/tmp/texa-paired-readonly-electron-'+Date.now();mkdirSync(userData,{recursive:true});
writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'actual macOS Electron; readonly restored paid answers; no paid UI rerun',cases:[],errors:[]};let app,page;
try {
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
 page=await app.firstWindow();page.setDefaultTimeout(25000);
 await page.route('**/api/**',async route=>{if(route.request().method()!=='GET')return route.abort();return route.continue();});
 page.on('pageerror',e=>result.errors.push(String(e)));
 await page.locator('.composer-textarea').waitFor();
 for(const id of ['integral-A','integral-C','stokes-A']) {
   await page.evaluate(id=>localStorage.setItem('kaoyan_conversation_id','conv_'+id),id);
   await page.reload();await page.locator('.composer-textarea').waitFor();await page.locator('.context-session-row.is-active').click();await page.locator('.learning-answer-document .markdown-body').first().waitFor();
   await page.setViewportSize({width:1280,height:820});await page.screenshot({path:resolve(out,id+'.png')});
   await page.getByRole('heading',{name:'最终解答',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:resolve(out,id+'-final.png')});
   result.cases.push({id,answer_text:await page.locator('.learning-answer-document .markdown-body').allTextContents(),native_trace_collapsed:(await page.locator('.execution-trace-toggle').last().getAttribute('aria-expanded'))==='false'});
 }
} catch(e){result.errors.push(String(e));process.exitCode=1;if(page)await page.screenshot({path:resolve(out,'error.png')});}
finally{await app?.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
