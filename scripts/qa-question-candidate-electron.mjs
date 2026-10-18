/** Real Electron + real v1 API/storage on frozen local data copies. Other UI APIs are fixtures. */
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,extname} from 'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');
const work=resolve(process.env.TEXA_QC_QA_WORK || `artifacts/question-candidate-contract/electron-${Date.now()}`);mkdirSync(work,{recursive:true});
const out=resolve(work,'screenshots');mkdirSync(out,{recursive:true});
const book='传感器原理及应用';
const upstream=spawn(process.execPath,['scripts/visual-preview-server.mjs'],{env:{...process.env,TEXA_VISUAL_PORT:'18061'},stdio:'ignore'});
const backend=spawn(resolve('venv310/bin/python'),['scripts/qa-question-candidate-server.py'],{env:{...process.env,TEXA_QC_QA_WORK:work},stdio:['ignore','pipe','pipe']});
let backendLog='';backend.stdout.on('data',d=>backendLog+=d);backend.stderr.on('data',d=>backendLog+=d);
let scenario='normal', writes=0, captured=[], latest=null, lastCommit=null;
const server=createServer(async(req,res)=>{try{
 const url=new URL(req.url,'http://127.0.0.1');let body='';for await(const c of req)body+=c;
 if(url.pathname.startsWith('/api/') || url.pathname==='/health'){
  const headers={'Content-Type':'application/json'};
  if(url.pathname==='/api/books/list'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,data:[{name:book,book_id:'qc-book',display_name:book,subject:'专业课',has_pdf:false,chapter_count:11,lifecycle_status:'active'}]}));return;}
  if(url.pathname.startsWith('/api/exercises/')){
   if(url.pathname==='/api/exercises/candidates/batch-add'){
    writes++;captured.push(JSON.parse(body));
    if(scenario==='downgrade'){res.writeHead(404,headers);res.end(JSON.stringify({detail:'Not Found'}));return;}
   }
   const response=await fetch('http://127.0.0.1:18062'+req.url,{method:req.method,headers,...(body?{body}:{})});
   const data=await response.json();
   if(url.pathname==='/api/exercises/textbook-analyze'){
    if(scenario==='legacy')delete data.candidate_contract_version;
    latest=data;
   }
   if(url.pathname==='/api/exercises/candidates/batch-add')lastCommit=data;
   if(url.pathname==='/api/exercises/candidates/batch-add'&&scenario==='unknown'){res.writeHead(200,headers);res.write('{"success":');setTimeout(()=>res.destroy(),20);return;}
   if(url.pathname==='/api/exercises/candidates/batch-add'&&scenario==='incomplete')data.candidate_receipts=[];
   res.writeHead(response.status,headers);res.end(JSON.stringify(data));return;
  }
  if(url.pathname.endsWith('/chapters')){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,data:[]}));return;}
  if(url.pathname==='/api/chat/conversations'){
    const data=await(await fetch('http://127.0.0.1:18061'+req.url)).json();res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,data:{items:data.data.map(c=>({...c,management:{state:'active',pinned:false,revision:0}})),has_more:false,next_cursor:null}}));return;
  }
  if(url.pathname==='/api/system/settings/subjects'){res.end(JSON.stringify({success:true,data:{subjects:[{name:'专业课',children:[]}]}}));return;}
  const response=await fetch('http://127.0.0.1:18061'+req.url,{method:req.method});res.writeHead(response.status,headers);res.end(await response.text());return;
 }
 const file=resolve('frontend/dist',url.pathname==='/'||!extname(url.pathname)?'index.html':'.'+url.pathname);
 if(!file.startsWith(resolve('frontend/dist')+'/'))throw Error('invalid path');
 res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2','.ttf':'font/ttf'})[extname(file)]||'application/octet-stream');res.end(readFileSync(file));
}catch(error){res.writeHead(500);res.end(JSON.stringify({message:String(error)}));}});
const result={environment:'macOS Electron 37, production React, real v1 exercise API/storage, frozen OCR/IR copy; auxiliary APIs fixture; no models/OCR',checks:[],screenshots:[],errors:[]};
let app,page;
const check=(ok,name)=>{result.checks.push({name,status:ok?'PASS':'FAIL'});if(!ok)throw Error(name)};
async function shot(name){if(await page.locator('.exercise-candidate-review:visible').count() && !await page.locator('.exercise-candidate-review.is-comparing:visible').count()){await page.locator('.exercise-candidate-inner').waitFor({state:'visible'});check(await page.locator('.exercise-candidate-inner').isVisible(),name+' candidate canvas visible');}await page.evaluate(()=>document.fonts.ready);await page.waitForFunction(()=>[...document.querySelectorAll('[data-texa-markdown-loading]')].every(e=>!e.getBoundingClientRect().height));await page.screenshot({path:resolve(out,name+'.png'),scale:'css',animations:'disabled'});result.screenshots.push(name+'.png');check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),name+' no window overflow');}
async function setup(){await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.once('will-prevent-unload',event=>event.preventDefault()));await page.goto('http://127.0.0.1:18060/exercises');await page.getByRole('radio',{name:'导入',exact:true}).click();await page.locator('.exercise-import-setup').getByRole('button',{name:'选择科目',exact:true}).click();await page.getByRole('button',{name:'专业课',exact:true}).click();await page.getByRole('button',{name:new RegExp(book)}).click();}
async function analyze(){await page.getByRole('button',{name:'抽取教材候选题',exact:true}).click();await page.getByRole('heading',{name:'校对候选题',exact:true}).waitFor();}
async function choose(index){await page.locator('.exercise-index-item').nth(index).getByRole('button').click();}
try{
 await new Promise(r=>server.listen(18060,'127.0.0.1',r));
 for(let i=0;i<60;i++){try{await fetch('http://127.0.0.1:18062/docs');break;}catch{await new Promise(r=>setTimeout(r,200));}}
 const userData=resolve(work,'userData');mkdirSync(userData,{recursive:true});writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18060',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18060'}});
 page=await app.firstWindow();page.setDefaultTimeout(15000);page.on('pageerror',e=>result.errors.push(String(e)));page.on('dialog',d=>void d.accept().catch(()=>{}));
 await page.locator('.composer-textarea').waitFor();await page.evaluate(book=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','专业课');localStorage.setItem('kaoyan_book_name',book);},book);
 check(await page.evaluate(()=>window.kaoyanDesktop?.isElectron),'real Electron preload');
 for(const [width,height] of [[1280,820],[1024,768],[760,820]]){
  await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[width,height]);
  await setup();await analyze();check(await page.locator('.exercise-index-item').count()===108,'108 candidates '+width);
  await shot(width+'-separated');check((await page.locator('.exercise-candidate-explanation').innerText()).length>100,'source solution visibly separated '+width);
  await page.getByRole('button',{name:'原文对照',exact:true}).first().click();
  if(width<1280)await page.getByRole('button',{name:'原文对照',exact:true}).last().click();
  await shot(width+'-source');check(await page.locator('[data-source-block]').count()===3,'C001 three source blocks '+width);
  await page.getByRole('button',{name:'返回候选索引'}).click();await choose(30);await shot(width+'-missing-figure');check((await page.locator('.exercise-content-issue').innerText()).includes('图3.60'),'C031 precise missing figure '+width);
  await choose(95);await shot(width+'-mixed-solution');
  check(await page.locator('.exercise-content-issue').count()>=3,'C096 multiple risks '+width);
  await choose(19);await shot(width+'-cross-page-table');
  await choose(90);await shot(width+'-long-math');
 }
 // Ordinary no-answer/no-tag candidate requires zero per-item confirmation.
 await setup();await analyze();await page.getByRole('button',{name:'清空选择'}).click();await choose(6);await page.locator('.exercise-index-item').nth(6).getByRole('checkbox').check();
 check(await page.getByRole('button',{name:'确认入库1题',exact:true}).isEnabled(),'ordinary empty answer/tags selectable without review');
 // An edited version requires an explicit current-item confirmation.
 await choose(0);await page.getByRole('button',{name:'编辑',exact:true}).click();const question=page.getByRole('textbox',{name:'候选题题干'});await question.fill((await question.inputValue())+'\n\n本地隔离校对。');
 await page.getByRole('button',{name:'确认本题结构',exact:true}).click();await page.getByText('已确认当前版本',{exact:true}).waitFor();
 await question.fill((await question.inputValue())+'再次编辑。');check(!await page.getByText('已确认当前版本',{exact:true}).count(),'body edit clears confirmation');
 await page.getByRole('button',{name:'确认本题结构',exact:true}).click();await page.getByText('已确认当前版本',{exact:true}).waitFor();await page.getByRole('button',{name:'阅读预览'}).click();
 await page.locator('.exercise-index-item').first().getByRole('checkbox').check();
 await page.getByRole('button',{name:'确认入库2题',exact:true}).click();await page.locator('.exercise-receipt').waitFor();
 check(captured.at(-1).exercises.length===2,'submitted subset identity frozen');check(captured.at(-1).exercises[0].candidate_context.review!==null,'explicit confirmation sent');
 await page.locator('.exercise-import-receipts>summary').first().click();await page.getByRole('button',{name:'核对正文版本'}).first().click();await page.locator('.exercise-import-receipts details>summary').first().click();await page.getByText('正文与导入时相同',{exact:true}).waitFor();await shot('760-subset-receipt');
 const savedId=lastCommit.candidate_receipts[0].exercise_id;
 await fetch('http://127.0.0.1:18060/api/exercises/answer/save?book_name='+encodeURIComponent(book),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:savedId,answer:'隔离副本的后续正式答案修改',explanation:''})});
 await page.getByRole('button',{name:'核对正文版本'}).first().click();await page.getByText('正文已更改或缺失，仅为历史导入事实',{exact:true}).waitFor();check(true,'later official body change keeps receipt historical');
 await page.getByRole('button',{name:'继续校对剩余候选'}).click();check(await page.locator('.exercise-index-item').count()===106,'only saved/duplicate-skipped removed; unresolved candidates retained');
 // New client refuses old analysis or a downgraded commit endpoint.
 scenario='legacy';await setup();await page.getByRole('button',{name:'抽取教材候选题'}).click();await page.locator('p:visible').filter({hasText:'后端未提供v1候选合同'}).first().waitFor();check(true,'legacy backend version echo refusal');
 scenario='downgrade';await setup();await analyze();await page.getByRole('button',{name:/^确认入库\d+题$/}).click();await page.locator('p:visible').filter({hasText:'入库被拒绝'}).first().waitFor();check(await page.locator('.exercise-index-item').count()===108,'404 never falls back to legacy batch-add');
 // Incomplete receipts and dropped connections keep all candidates, lock resubmission.
 for(const mode of ['incomplete','unknown']){
  scenario=mode;await setup();await analyze();await page.getByRole('button',{name:/^确认入库\d+题$/}).click();await page.getByRole('heading',{name:'入库结果待核对'}).waitFor();
  const before=writes;await page.getByRole('button',{name:'核对导入批次'}).click();await page.locator('.exercise-import-receipts').first().waitFor();check(writes===before,mode+' no automatic resend');check(await page.locator('.exercise-index-item').count()===108,mode+' candidates retained');await shot('760-'+mode);
 }
 check(result.errors.length===0,'no renderer exceptions');
}catch(error){result.errors.push(String(error));if(page)await page.screenshot({path:resolve(out,'failure.png')});process.exitCode=1;}
finally{writeFileSync(resolve(work,'results.json'),JSON.stringify({...result,writes},null,2));writeFileSync(resolve(work,'backend.log'),backendLog);await app?.evaluate(({app})=>app.exit(0)).catch(()=>{});await app?.close().catch(()=>{});server.close();upstream.kill();backend.kill();console.log(JSON.stringify({checks:result.checks.length,errors:result.errors,screenshots:result.screenshots.length,writes,work},null,2));}
