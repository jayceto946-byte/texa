/** Real Electron + isolated SQL/SymPy/SSE. Controlled delays test UX only. */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');
const out=resolve('docs/qa/evidence/agent-loop-performance/electron');mkdirSync(out,{recursive:true});
const userData='/private/tmp/texa-performance-electron-'+Date.now();mkdirSync(userData,{recursive:true});
writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'macOS actual Electron development shell',model:'controlled; artificial 1.2/15 second waits; not speed evidence',checks:[],errors:[],sse:[]};
let app,page;
try {
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
 page=await app.firstWindow();page.setDefaultTimeout(25000);
 page.on('pageerror',e=>result.errors.push(String(e)));
 page.on('response',async response=>{if(response.url().endsWith('/api/chat/stream'))try{result.sse.push((await response.text()).split('\n').filter(x=>x.startsWith('data: ')).map(x=>JSON.parse(x.slice(6)).execution_event));}catch{}});
 await page.locator('.composer-textarea').waitFor();
 await page.evaluate(() => {
   window.__texaDelivery = [];
   const original = window.fetch;
   window.fetch = async (...args) => {
     const start = performance.now();
     const response = await original(...args);
     if (response.url.endsWith('/api/chat/stream') && response.body) {
       const capture = {headers_ms: performance.now()-start, reads: []};
       window.__texaDelivery.push(capture);
       const reader = response.clone().body.getReader();
       void (async () => { try {
         while (true) { const {done,value} = await reader.read();
           if (done) break;
           capture.reads.push({received_ms: performance.now()-start, bytes: value.byteLength});
         }
         capture.closed_ms = performance.now()-start;
       } catch { capture.interrupted = true; } })();
     }
     return response;
   };
 });
 await page.locator('.composer-textarea').waitFor();
 const submit=async text=>{await page.locator('.composer-textarea').fill(text);await page.getByRole('button',{name:'发送问题',exact:true}).click();};
 const title=()=>page.locator('.execution-trace').last().locator('.execution-title');
 await page.setViewportSize({width:1280,height:820});
 await submit('计算 2^10');
 await title().filter({hasText:'正在分析题目'}).waitFor();await page.screenshot({path:resolve(out,'analysis.png')});
 await title().filter({hasText:'正在计算'}).waitFor();await page.screenshot({path:resolve(out,'calculation.png')});
 await title().filter({hasText:'正在继续解答'}).waitFor();await page.screenshot({path:resolve(out,'continuation.png')});
 await title().filter({hasText:'正在生成回答'}).waitFor();await page.screenshot({path:resolve(out,'public-stream.png')});
 await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
 const trace=page.locator('.execution-trace').last();
 if(await trace.locator('button').first().getAttribute('aria-expanded')!=='false')throw Error('process did not collapse');
 result.checks.push('four truthful progress states, immediate public stream, final collapsed');
 await trace.locator('button').first().click();await trace.locator('.execution-trace-body').waitFor();await trace.locator('button').first().click();
 for(const [width,height] of [[1280,820],[1024,768],[760,820]]){await page.setViewportSize({width,height});await page.screenshot({path:resolve(out,`${width}-final.png`)});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error(`overflow ${width}`);}
 await submit('计算 1/0');await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();await page.getByText(/除数不能为零/).last().waitFor();await page.screenshot({path:resolve(out,'failure.png')});result.checks.push('tool failure visible');
 await page.setViewportSize({width:1280,height:820});await submit('计算 7');
 await title().filter({hasText:'正在分析题目'}).waitFor();await page.waitForTimeout(6000);await page.screenshot({path:resolve(out,'long-wait.png')});
 if(!(await title().innerText()).includes('正在分析题目'))throw Error('invented progress while no event');
 await page.getByRole('button',{name:'停止生成',exact:true}).click();await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();await page.screenshot({path:resolve(out,'cancelled.png')});result.checks.push('long silence keeps actual state/time, stop acknowledged');
 result.browser_delivery = await page.evaluate(()=>window.__texaDelivery);
 await page.reload();await page.locator('.composer-textarea').waitFor();
 result.checks.push('reload works after interruption');
 const body=await page.locator('body').innerText();if(/runtime_call_id|reasoning_content|handler_ms/.test(body))throw Error('raw metadata leak');
} catch(e) {result.errors.push(String(e));process.exitCode=1;if(page)await page.screenshot({path:resolve(out,'error.png')});}
finally{await app?.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
