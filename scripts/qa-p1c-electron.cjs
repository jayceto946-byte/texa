/* Electron renderer -> actual P1-C APIs, deterministic data only. */
const { _electron } = require('playwright');
const {spawn} = require('node:child_process');
const {mkdtempSync, mkdirSync, writeFileSync} = require('node:fs');
const {resolve, join} = require('node:path');
const {tmpdir} = require('node:os');
const root = process.cwd();
const dir = mkdtempSync(join(tmpdir(), 'texa-p1c-electron-'));
const base = 'http://127.0.0.1:18186';
const py = process.env.TEXA_QA_PYTHON;
const executablePath = process.env.TEXA_QA_ELECTRON;
if (!py || !executablePath) throw new Error('Set TEXA_QA_PYTHON and TEXA_QA_ELECTRON to existing runtimes');
const server = spawn(py, ['-m','uvicorn','scripts.qa_p1c_server:app','--host','127.0.0.1','--port','18186','--lifespan','off'], {
 cwd: root, env: {...process.env, TEXA_P1C_QA:'1', TEXA_P1C_QA_ROOT:dir, KAOYAN_TRUSTED_ORIGINS:base, ENV_PATH:join(dir,'empty.env'), DATA_DIR:join(dir,'data'), MINERU_OUTPUT_PATH:join(dir,'mineru')}, stdio:['ignore','ignore','pipe']});
let logs='', app;
server.stderr.on('data', d=>{logs+=d.toString();});
const checks=[];
function check(value, name) { if(!value) throw new Error(name); checks.push(name); }
(async()=>{try {
 for(let i=0;i<80;i++){try{if((await fetch(base+'/p1c-fixture')).ok)break;}catch{} await new Promise(r=>setTimeout(r,100));}
 const fixture = await (await fetch(base+'/p1c-fixture')).json();
 const userData=join(dir,'userData');mkdirSync(userData);
 writeFileSync(join(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app = await _electron.launch({executablePath,args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base,KAOYAN_FRONTEND_DEV_URL:base}});
 const page=await app.firstWindow();page.setDefaultTimeout(15000);await page.waitForURL(url=>url.href.startsWith(base),{timeout:45000});await page.waitForLoadState('domcontentloaded');
 check(await page.evaluate(()=>window.kaoyanDesktop?.isElectron),'real Electron preload');
 const result=await page.evaluate(async({fixture,base})=>{
   const checks=[]; const req=async(path,body)=>{
     const r=await fetch(base+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
     if(!r.ok)throw new Error(path+':'+r.status);return await r.json();};
   const ok=(v,name)=>{if(!v)throw new Error(name);checks.push(name);};
   const b='?book_name='+fixture.book;
   let r=await req('/api/exercises/answer/save'+b,{id:fixture.exercise_id,answer:'参考结果 2',knowledge_job_id:fixture.job_id});
   ok(r.metadata_status==='saved' && r.data.knowledge_structure.primary.concept_id==='c1','job classification saved');
   r=await req('/api/exercises/by-concept/c1'+b);ok(r.data.length===1,'canonical same-concept query');
   r=await req('/api/mistakes/weak-points'+b);ok(r.data.length===0,'association does not imply weakness');
   let record=(await req('/api/mistakes/'+fixture.mistake_id+b)).data;
   const path='/api/mistakes/'+fixture.mistake_id+'/attempts/'+fixture.attempt_id+'/diagnosis'+b;
   r=await req(path,{expected_revision:record.revision,operation_id:'smoke-proposal',proposal:{errors:[{error_type:'orientation',concept_ids:['c1'],start:5,end:9,quote:'法向取反',step:2}]}});
   ok(r.data.diagnosis.status==='suggested','evidence suggestion persisted');
   ok((await req('/api/mistakes/weak-points'+b)).data.length===0,'unconfirmed cause excluded');
   const confirm={expected_revision:r.data.revision,operation_id:'smoke-confirm',confirm:true,expected_diagnosis_digest:r.data.diagnosis_digest};
   r=await req(path,confirm);ok(r.data.diagnosis.status==='confirmed','explicit attempt confirmation');
   const replay=await req(path,confirm);ok(replay.data.revision===r.data.revision,'confirmation replay idempotent');
   r=await req('/api/mistakes/weak-points'+b);ok(r.data.find(v=>v.concept_id==='c1')?.count===1,'one confirmed concept error');
   r=await req('/api/mistakes/diagnosis'+b);ok(r.data.confirmed_error_attempts===1,'one attempt globally counted');
   r=await req('/api/mistakes/'+fixture.mistake_id+'/attempts'+b);ok(r.data.items[0].diagnosis.errors[0].quote==='法向取反','evidence span readback');
   return checks;
 },{fixture,base});
 checks.push(...result);
 await page.evaluate((fixture)=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学/高数');localStorage.setItem('kaoyan_book_name',fixture.book);},fixture);
 await page.route('**/api/system/settings',route=>route.fulfill({json:{success:true,data:{models:{providers:[],models:[],roles:{reasoning:{model:'fixture'},vision:{model:'fixture'}},credentials:{reasoning:{required:false,configured:false},vision:{required:false,configured:false}},multimodal_mode:'native',profiles:[]},subjects:[],env:{}}}}));
 await page.goto(base+'/mistakes/diagnosis');
 await page.getByRole('heading',{name:'错题诊断',exact:true}).waitFor();
 await page.getByText('哪里容易错',{exact:true}).waitFor();
 await page.getByRole('link',{name:'Stokes',exact:true}).first().waitFor();
 const imageDir=resolve('artifacts/p1c',process.env.TEXA_QA_STAGE||'final');mkdirSync(imageDir,{recursive:true});
 for(const [width,height] of [[1280,820],[1024,768],[760,820]]){
   await page.setViewportSize({width,height});
   await page.screenshot({path:join(imageDir,`diagnosis-${width}.png`),fullPage:true});
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'diagnosis no horizontal overflow '+width);
 }
 const editChecks=await page.evaluate(async({fixture,base})=>{
   const b='?book_name='+fixture.book;
   const record=(await (await fetch(base+'/api/mistakes/'+fixture.mistake_id+b)).json()).data;
   const r=await fetch(base+'/api/mistakes/'+fixture.mistake_id+b,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:record.revision,operation_id:'smoke-edit',changes:{question_text:'修订题目'}})});
   if(!r.ok)throw new Error('existing edit API');
   const weak=await(await fetch(base+'/api/mistakes/weak-points'+b)).json();
   if(weak.data.length)throw new Error('old evidence still counted');
   return ['existing edit API accepts correction','edited question invalidates old diagnosis'];
 },{fixture,base});
 checks.push(...editChecks);
 const out={status:'PASS',checks,electron:await app.evaluate(()=>process.versions.electron),fixture:true,real_model:'NOT VERIFIED',userData:dir};
 mkdirSync('artifacts/p1c',{recursive:true});writeFileSync('artifacts/p1c/electron-results.json',JSON.stringify(out,null,2));
 console.log(JSON.stringify(out,null,2));
 }catch(e){console.error(e.stack);console.error(logs.slice(-3500));process.exitCode=1;}finally{if(app)await app.close();server.kill('SIGTERM');}})();
