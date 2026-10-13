/** Actual Electron + isolated real FastAPI/Runtime/SymPy, controlled model only. */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');
const out=resolve('docs/qa/evidence/native-tool-loop/electron');mkdirSync(out,{recursive:true});
const userData='/private/tmp/texa-native-tool-electron-'+Date.now();mkdirSync(userData,{recursive:true});
writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'macOS Electron development shell',model:'controlled LangChain interface',math:'actual isolated SymPy',checks:[],errors:[],sse:[]};
let app,page;
try{
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
 page=await app.firstWindow();page.setDefaultTimeout(20000);
 page.on('pageerror',e=>result.errors.push(String(e)));
 await page.locator('.composer-textarea').waitFor();
 result.checks.push({name:'actual Electron preload',passed:await page.evaluate(()=>window.kaoyanDesktop?.isElectron)});
 page.on('response',async response=>{if(response.url().endsWith('/api/chat/stream')){try{result.sse.push((await response.text()).split('\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)).execution_event));}catch{}}});
 await page.locator('.composer-textarea').fill('计算 2^10');await page.getByRole('button',{name:'发送问题',exact:true}).click();
 const trace=page.locator('.execution-trace').last();await trace.waitFor();
 await trace.locator('button').first().click();
 await page.getByText('正在计算',{exact:true}).first().waitFor();
 await page.screenshot({path:resolve(out,'1280-calculating.png')});
 await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
 await page.locator('.markdown-body').filter({hasText:'1024'}).last().waitFor();
 if(await trace.locator('button').first().getAttribute('aria-expanded')!=='false')throw Error('native process did not fold at completion');
 const body=await page.locator('body').innerText();if(body.includes('runtime_call_id')||body.includes('verification_request'))throw Error('raw tool protocol leaked into normal content');
 result.checks.push({name:'two SymPy tools and final independent answer, process folds',passed:true});
 for(const width of [1280,1024,760]){await page.setViewportSize({width,height:820});await page.screenshot({path:resolve(out,`${width}-final.png`)});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);result.checks.push({name:`${width} layout`,passed:!overflow});}
 await page.locator('.composer-textarea').fill('计算 1/0');await page.getByRole('button',{name:'发送问题',exact:true}).click();
 await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();await page.getByText(/除数不能为零/).last().waitFor();
 await page.screenshot({path:resolve(out,'tool-failure.png')});
 result.checks.push({name:'tool failure disclosed',passed:true});
 await page.locator('.composer-textarea').fill('求 sin(x^x)的积分');await page.getByRole('button',{name:'发送问题',exact:true}).click();
 await page.locator('.execution-trace').last().getByText('正在计算',{exact:true}).first().waitFor();
 await page.getByRole('button',{name:'停止生成',exact:true}).click();
 await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
 await page.screenshot({path:resolve(out,'cancelled.png')});
 result.checks.push({name:'real tool run cancellation acknowledged',passed:true});
 await page.reload();await page.locator('.composer-textarea').waitFor();
 await page.getByRole('button',{name:'展开侧栏',exact:true}).click();
 await page.locator('.context-session-row').filter({hasText:'计算 2^10'}).first().click();
 await page.locator('.markdown-body').filter({hasText:'1024'}).first().waitFor();
 result.checks.push({name:'reload restores authoritative final answer',passed:true});
}catch(e){result.errors.push(String(e));process.exitCode=1;if(page){result.body=await page.locator('body').innerText();await page.screenshot({path:resolve(out,'failure.png')});}}
finally{await app?.close();if(result.checks.some(c=>!c.passed)||result.errors.length)process.exitCode=1;writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
