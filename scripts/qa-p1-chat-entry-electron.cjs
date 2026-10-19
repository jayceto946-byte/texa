/* Render the saved public model responses and final-code local replays. */
const {_electron}=require('playwright');
const {spawn}=require('node:child_process');
const {mkdtempSync,mkdirSync,writeFileSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve}=require('node:path');
const qa='/private/tmp/texa-p1-chat-entry-20261019', base='http://127.0.0.1:18190';
const dir=mkdtempSync(join(tmpdir(),'texa-chat-entry-ui-'));
const out=resolve('docs/qa/p1-chat-entry/electron');mkdirSync(out,{recursive:true});
const server=spawn(process.env.TEXA_QA_PYTHON,['-m','uvicorn','scripts.qa_p1_chat_entry_server:app','--host','127.0.0.1','--port','18190','--lifespan','off'],
 {cwd:process.cwd(),env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',DATA_DIR:join(qa,'data'),PROGRESS_PATH:join(qa,'progress'),
 VECTOR_DB_PATH:join(qa,'vector'),MINERU_OUTPUT_PATH:join(qa,'mineru'),ENV_PATH:join(qa,'empty.env'),KAOYAN_TRUSTED_ORIGINS:base},stdio:['ignore','ignore','pipe']});
let logs='',app,page;server.stderr.on('data',d=>logs+=d.toString());
const checks=[],errors=[],rendererErrors=[];
const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);console.log(name)};
(async()=>{try{
 let ready=false;
 for(let i=0;i<200;i++){try{if((await fetch(base+'/health')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}
 check(ready,'isolated saved chat receipts ready');
 const userData=join(dir,'userData');mkdirSync(userData);writeFileSync(join(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app=await _electron.launch({timeout:30000,executablePath:process.env.TEXA_QA_ELECTRON,args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,
 KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base,KAOYAN_FRONTEND_DEV_URL:base}});
 console.log('Electron connected');
 page=await app.firstWindow({timeout:30000});page.setDefaultTimeout(15000);page.on('pageerror',e=>rendererErrors.push(String(e)));
 await page.route('https://**',r=>r.abort());
 await page.route('**/api/system/settings',r=>r.fulfill({json:{success:true,data:{models:{providers:[],models:[],roles:{reasoning:{model:'saved acceptance'},vision:{model:'fixture'}},credentials:{reasoning:{required:false},vision:{required:false}},multimodal_mode:'native',profiles:[]},subjects:[],env:{}}}}));
 await page.route('**/api/books/list',r=>r.fulfill({json:{success:true,data:[]}}));
 await page.waitForURL(u=>u.href.startsWith(base),{timeout:45000});
 check(await page.evaluate(()=>window.kaoyanDesktop?.isElectron),'real Electron preload');
 for(const [name,label,answer] of [['C','部分内容尚未验证，需要核对','拟合'],['B','部分内容尚未验证，需要核对','0.233'],['AB','部分结论未通过检查','最小值']]){
  await page.evaluate(()=>localStorage.setItem('texa:setup-complete:v3','1'));
  await page.goto(base+'/?conversation_id=chat-entry-replay-final-'+name);
  await page.getByRole('region',{name:'任务执行过程'}).getByRole('status').getByText(label,{exact:true}).waitFor();
  const trace=page.locator('.execution-trace');
  check((await trace.innerText()).includes(label),name+' terminal verification label');
  check(!(await trace.innerText()).includes('处理完成'),name+' never presented as whole-task verified');
  await page.waitForFunction(()=>[...document.querySelectorAll('[data-texa-markdown-loading]')].every(e=>!e.getBoundingClientRect().height));
  check((await page.locator('body').innerText()).includes(answer),name+' saved answer displayed');
  await trace.getByRole('button',{name:/查看过程/}).click();
  await trace.screenshot({path:join(out,name+'.png'),animations:'disabled'});
  check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),name+' no horizontal overflow');
 }
 check(rendererErrors.length===0,'no renderer exceptions');
}catch(e){errors.push(String(e));console.error(logs.slice(-3000));process.exitCode=1;}
finally{const result={status:errors.length?'FAIL':'PASS',checks,errors,rendererErrors,fixture:'actual chat-entry paid responses replayed locally through final code; existing Electron history view',additional_model_requests:0,live_paid_desktop_submission:false,data_isolation:qa};writeFileSync(join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));if(app)await app.close();server.kill('SIGTERM');}})();
