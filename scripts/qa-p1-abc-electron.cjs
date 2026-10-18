/* Synthetic candidate UI on combined A/B/C backend, no model or user data. */
const {_electron}=require('playwright');
const {spawn}=require('node:child_process');
const {mkdtempSync,mkdirSync,writeFileSync}=require('node:fs');
const {resolve,join}=require('node:path');
const {tmpdir}=require('node:os');
const dir=mkdtempSync(join(tmpdir(),'texa-p1c-electron-'));
const base='http://127.0.0.1:18187';
const server=spawn(process.env.TEXA_QA_PYTHON,['-m','uvicorn','scripts.qa_p1_abc_server:app','--host','127.0.0.1','--port','18187','--lifespan','off'],{cwd:process.cwd(),env:{...process.env,TEXA_P1C_QA:'1',TEXA_P1C_QA_ROOT:dir,DATA_DIR:join(dir,'data'),MINERU_OUTPUT_PATH:join(dir,'mineru'),ENV_PATH:join(dir,'empty.env'),KAOYAN_TRUSTED_ORIGINS:base},stdio:['ignore','ignore','pipe']});
let logs='',app,page;server.stderr.on('data',d=>logs+=d.toString());
const checks=[],errors=[];const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name)};
const out=resolve('artifacts/p1-abc-electron');mkdirSync(out,{recursive:true});
(async()=>{try{
 for(let i=0;i<100;i++){try{if((await fetch(base+'/p1abc-fixture')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 const userData=join(dir,'userData');mkdirSync(userData);writeFileSync(join(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app=await _electron.launch({executablePath:process.env.TEXA_QA_ELECTRON,args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base,KAOYAN_FRONTEND_DEV_URL:base}});
 page=await app.firstWindow();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')logs+='\n'+m.text();});page.on('dialog',d=>d.accept());
 await page.waitForURL(url=>url.href.startsWith(base),{timeout:45000});await page.waitForLoadState('domcontentloaded');
 check(await page.evaluate(()=>window.kaoyanDesktop?.isElectron),'real Electron preload');
 await page.route('**/api/system/settings',r=>r.fulfill({json:{success:true,data:{models:{providers:[],models:[],roles:{reasoning:{model:'fixture'},vision:{model:'fixture'}},credentials:{reasoning:{required:false},vision:{required:false}},multimodal_mode:'native',profiles:[]},subjects:[],env:{}}}}));
 await page.route('**/api/books/list',r=>r.fulfill({json:{success:true,data:[{name:'integration-toy',display_name:'integration-toy',book_id:'toy',subject:'数学/高数',has_pdf:false,chapter_count:1,lifecycle_status:'active'}]}}));
 await page.route('**/api/books/*/chapters',r=>r.fulfill({json:{success:true,data:[]}}));
 await page.evaluate(()=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学/高数');localStorage.setItem('kaoyan_book_name','integration-toy');});
 await page.goto(base+'/exercises');await page.getByRole('radio',{name:'导入',exact:true}).click();
 // Use the existing scope selector when route state has no selected textbook.
 const analyze=page.getByRole('button',{name:'抽取教材候选题',exact:true});
 if(!await analyze.isEnabled()){
   await page.locator('.exercise-import-setup').getByRole('button',{name:'选择科目',exact:true}).click();
   await page.getByRole('button',{name:'数学',exact:true}).click();
   await page.getByRole('button',{name:'高数',exact:true}).click();
   await page.getByRole('button',{name:/integration-toy/}).click();
 }
 await analyze.click();await page.getByRole('heading',{name:'校对候选题',exact:true}).waitFor();
 const count=await page.locator('.exercise-index-item').count();check(count===3,'three synthetic source candidates');
 const rows=page.locator('.exercise-index-item');
 for(const [width,height] of [[1280,820],[1024,768],[760,820]]){
   await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
   await rows.nth(1).getByRole('button').click();
   await page.locator('.exercise-candidate-explanation').waitFor();check((await page.locator('.exercise-candidate-explanation').innerText()).includes('7'),'source solution separated '+width);
   await page.waitForFunction(()=>[...document.querySelectorAll('[data-texa-markdown-loading]')].every(e=>!e.getBoundingClientRect().height));
   await page.screenshot({path:join(out,`candidate-${width}.png`),animations:'disabled'});
   check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),'no overflow '+width);
 }
 await rows.nth(2).getByRole('button').click();check((await page.locator('.exercise-content-issue').allTextContents()).join('').includes('图1.1'),'required image stays unresolved');
 await page.getByRole('button',{name:'清空选择',exact:true}).click();await rows.first().getByRole('checkbox').check();
 await rows.first().getByRole('button').click();
 check(await page.getByRole('button',{name:'确认入库1题',exact:true}).isEnabled(),'ordinary candidate has no mandatory review');
 await page.getByRole('button',{name:'确认入库1题',exact:true}).click();await page.locator('.exercise-receipt').waitFor();
 check(await page.getByRole('heading',{name:'已加入 1 道题目',exact:true}).isVisible(),'candidate committed through actual API');
 await page.getByRole('button',{name:'继续校对剩余候选',exact:true}).click();check(await rows.count()===2,'unresolved candidates retained');
 const receipts=await page.evaluate(async()=>{const r=await(await fetch('/api/exercises/import-batches?book_name=integration-toy')).json();return r.data[0].candidate_receipts;});
 check(receipts.length===1&&receipts[0].review_kind==='system_proposed','receipt persistence without artificial human confirmation');
 check(errors.length===0,'no renderer errors');
}catch(e){errors.push(String(e));if(page)await page.screenshot({path:join(out,'failure.png')}).catch(()=>{});console.error(logs.slice(-3000));process.exitCode=1;}finally{const result={status:errors.length?'FAIL':'PASS',checks,errors,synthetic:true,real_model:'NOT VERIFIED'};writeFileSync(join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));if(app)await app.close();server.kill('SIGTERM');}})();
