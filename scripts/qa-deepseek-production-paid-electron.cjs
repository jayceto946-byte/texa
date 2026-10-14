/** Actual authorized generation through Electron -> Chat API -> production Runtime. */
const {_electron}=require('playwright');
const {mkdirSync,writeFileSync,readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const out=resolve('docs/qa/evidence/deepseek-production/paid/electron');mkdirSync(out,{recursive:true});
const plan=JSON.parse(readFileSync(resolve('docs/qa/evidence/deepseek-production/PAID-ACCEPTANCE-PLAN.json')));
const userData='/private/tmp/texa-deepseek-paid-electron-'+Date.now();mkdirSync(userData,{recursive:true});writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'actual macOS Electron and real Providers via formal Chat API',cases:[],errors:[],sse:[]};
const save=()=>writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));
(async()=>{let app,page;try{
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
 page=await app.firstWindow();page.setDefaultTimeout(25000);page.on('pageerror',e=>result.errors.push(String(e)));
 await page.locator('.composer-textarea').waitFor();
 page.on('requestfailed',r=>{result.errors.push({url:r.url(),failure:r.failure()});save();});
 await page.exposeFunction('acceptanceStreamChunk',chunk=>{result.sse.push({chunk});save();});
 await page.exposeFunction('acceptanceAbortStack',stack=>{result.errors.push({abort_stack:stack});save();});
 await page.evaluate(()=>{const original=AbortController.prototype.abort;AbortController.prototype.abort=function(...args){void window.acceptanceAbortStack(new Error('abort callsite').stack);return original.apply(this,args);};});
 await page.evaluate(()=>{const original=window.fetch;window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/chat/stream')){const reader=response.clone().body.getReader();(async()=>{const decoder=new TextDecoder();while(true){const {done,value}=await reader.read();if(done)break;await window.acceptanceStreamChunk(decoder.decode(value,{stream:true}));}})().catch(()=>{});}return response;};});
 page.on('response',async r=>{if(r.url().endsWith('/api/chat/stream')||r.url().includes('/resume/stream')){try{result.sse.push({url:r.url(),text:await r.text()});save();}catch{}}});
 await page.locator('.composer-textarea').waitFor();
 const profile=async name=>{await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('button',{name:'模型连接',exact:true}).click();await page.getByRole('combobox',{name:'切换并应用模型方案'}).click();await page.getByRole('option',{name:new RegExp(name)}).click();await page.getByRole('button',{name:'关闭设置',exact:true}).click();};
 const fresh=async()=>{if(await page.getByRole('button',{name:'展开侧栏',exact:true}).isVisible())await page.getByRole('button',{name:'展开侧栏',exact:true}).click();await page.getByRole('button',{name:'新会话',exact:true}).click();};
 const scope=async(book)=>{await page.getByRole('button',{name:'选择学习范围',exact:true}).click();await page.getByRole('button',{name:book?'专业课':'数学',exact:true}).click();await page.getByRole('button',{name:book?/传感器原理及应用/:/通用 QA/}).click();await page.waitForFunction(book=>document.querySelector('[aria-label="选择学习范围"]').innerText.includes(book?'传感器原理及应用':'通用 QA'),book);};
 const select=async id=>{const r=await page.request.post('http://127.0.0.1:18041/__acceptance__/case/'+id);if(!r.ok())throw Error('preflight/gate unavailable for '+id);};
 let currentResponse;const submit=async question=>{await page.locator('.composer-textarea').fill(question);const received=page.waitForResponse(r=>r.url().endsWith('/api/chat/stream')&&r.request().method()==='POST',{timeout:620000});await page.getByRole('button',{name:'发送问题',exact:true}).click();currentResponse=await received;};
 const complete=async()=>{if(currentResponse){await currentResponse.finished();currentResponse=null;}await page.getByRole('button',{name:'发送问题',exact:true}).waitFor({timeout:620000});return await page.locator('.learning-answer-document .markdown-body').allTextContents();};
 await profile('验收 Flash 可选');
 const selected=process.env.TEXA_PAID_CASES?process.env.TEXA_PAID_CASES.split(','):['S1','S5','S6','cancel','qwen-smoke'];
 for(const id of selected){const row={id,status:'started',started_at:new Date().toISOString(),answers:[]};result.cases.push(row);save();console.log(id,'started');try{
   if(id==='qwen-smoke')await profile('验收 Qwen 默认');
   await fresh();await scope(id==='S1');await select(id);
   const c=plan.cases.find(c=>c.id===id);
   if(id==='cancel'){
     await submit(c.question);
     await page.locator('.execution-title').filter({hasText:'正在继续解答'}).last().waitFor({timeout:185000});
     await page.getByRole('button',{name:'停止生成',exact:true}).click();await complete();
     await page.reload();await page.locator('.composer-textarea').waitFor();
     await page.locator('.context-session-row').filter({hasText:/计算 7/}).first().click();
     const before=(await (await page.request.get('http://127.0.0.1:18041/__acceptance__/status')).json()).receipts.length;
     await page.getByRole('button',{name:'继续本次解答',exact:true}).click();await complete();
     const after=(await (await page.request.get('http://127.0.0.1:18041/__acceptance__/status')).json()).receipts.length;
     row.resume_additional_requests=after-before;
     if(after!==before)throw Error('resume sent another paid request');
     await page.getByText('详细信息',{exact:true}).last().click();await page.getByText('本次模型续答状态已丢失',{exact:false}).last().waitFor();
   }else{
     for(const question of c.questions||[c.question]){await submit(question);row.answers.push(await complete());save();}
   }
   row.status='interaction_finished';row.ended_at=new Date().toISOString();
   await page.screenshot({path:resolve(out,id+'.png')});row.ui_text=await page.locator('.learning-answer-document').allTextContents();
   row.runtime_status=(await (await page.request.get('http://127.0.0.1:18041/__acceptance__/status')).json()).receipts.filter(r=>r.case===id);
   save();console.log(id,'completed');
 }catch(e){row.status='failed';row.error=String(e);row.ended_at=new Date().toISOString();if(!page.isClosed())await page.screenshot({path:resolve(out,id+'-error.png')});save();console.log(id,'failed');}}
}catch(e){result.errors.push(String(e));process.exitCode=1;if(page&&!page.isClosed())await page.screenshot({path:resolve(out,'error.png')});}
finally{await app?.close();save();}})();
