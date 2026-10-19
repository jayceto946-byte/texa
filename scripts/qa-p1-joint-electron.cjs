/* Existing Electron/React view, actual disposable SQL/SSE replays, no paid API. */
const {_electron}=require('playwright');
const {spawn}=require('node:child_process');
const {mkdtempSync,mkdirSync,writeFileSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve}=require('node:path');
const dir=mkdtempSync(join(tmpdir(),'texa-joint-ui-'));
const base='http://127.0.0.1:18189';
const out=resolve('docs/qa/p1-joint/electron');mkdirSync(out,{recursive:true});
const server=spawn(process.env.TEXA_QA_PYTHON,['-m','uvicorn','scripts.qa_p1_joint_server:app','--host','127.0.0.1','--port','18189','--lifespan','off'],
 {cwd:process.cwd(),env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',TEXA_JOINT_UI_ROOT:dir,DATA_DIR:join(dir,'data'),PROGRESS_PATH:join(dir,'progress'),
 VECTOR_DB_PATH:join(dir,'vector'),MINERU_OUTPUT_PATH:join(dir,'mineru'),ENV_PATH:join(dir,'empty.env'),KAOYAN_TRUSTED_ORIGINS:base},stdio:['ignore','ignore','pipe']});
let logs='',app,page;server.stderr.on('data',d=>logs+=d.toString());
const checks=[],errors=[],rendererErrors=[];
const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name)};
(async()=>{try{
 let ready=false;
 for(let i=0;i<200;i++){try{if((await fetch(base+'/p1-joint-fixture')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}
 check(ready,'isolated production SQL/SSE fixtures ready');
 const userData=join(dir,'userData');mkdirSync(userData);writeFileSync(join(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app=await _electron.launch({executablePath:process.env.TEXA_QA_ELECTRON,args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,
 KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base,KAOYAN_FRONTEND_DEV_URL:base}});
 page=await app.firstWindow();page.setDefaultTimeout(15000);page.on('pageerror',e=>rendererErrors.push(String(e)));
 await page.route('**/api/system/settings',r=>r.fulfill({json:{success:true,data:{models:{providers:[],models:[],roles:{reasoning:{model:'fixture'},vision:{model:'fixture'}},credentials:{reasoning:{required:false},vision:{required:false}},multimodal_mode:'native',profiles:[]},subjects:[],env:{}}}}));
 await page.route('**/api/books/list',r=>r.fulfill({json:{success:true,data:[]}}));
 await page.waitForURL(u=>u.href.startsWith(base),{timeout:45000});
 check(await page.evaluate(()=>window.kaoyanDesktop?.isElectron),'real Electron preload');
 for(const [name,label] of [['strict','部分内容尚未验证，需要核对'],['failed','回答中断'],['verified','处理完成']]){
  await page.evaluate(name=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_conversation_id','qa-joint-'+name);localStorage.setItem('kaoyan_subject','数学');},name);
  await page.goto(base+'/?conversation_id=qa-joint-'+name);
  await page.getByRole('region',{name:'任务执行过程'}).getByRole('status').getByText(label,{exact:true}).waitFor();
  const trace=page.locator('.execution-trace');
  check((await trace.innerText()).includes(label),name+' terminal label');
  if(name==='strict'){
   check(!(await trace.innerText()).includes('处理完成'),'degraded never shown as verified completion');
   await page.getByText('结论：1024',{exact:false}).waitFor();
   check((await page.locator('body').innerText()).includes('结论：1024'),'strict body retained');
  }
  await page.waitForFunction(()=>[...document.querySelectorAll('[data-texa-markdown-loading]')].every(e=>!e.getBoundingClientRect().height));
  await trace.getByRole('button',{name:/查看过程/}).click();
  await page.screenshot({path:join(out,name+'.png'),animations:'disabled'});
  check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),name+' no horizontal overflow');
 }
 check(rendererErrors.length===0,'no renderer exceptions');
}catch(e){errors.push(String(e));if(page)await page.screenshot({path:join(out,'failure.png')}).catch(()=>{});console.error(logs.slice(-5000));process.exitCode=1;}
finally{const result={status:errors.length?'FAIL':'PASS',checks,errors,rendererErrors,fixture:'actual local Runtime/SQL/SSE with scripted provider',real_paid_model_ui:'NOT VERIFIED',data_isolation:dir};writeFileSync(join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));if(app)await app.close();server.kill('SIGTERM');}})();
