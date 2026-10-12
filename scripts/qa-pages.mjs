/** Offline full-route QA harness. Uses synthetic read-only fixture APIs only.
 * NODE_PATH=<bundled modules> node scripts/qa-pages.mjs [dist] [output]
 * No model calls, production backend, or user data. Baselines require human review.
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const dist = resolve(process.argv[2] || '/tmp/texa-full-qa-dist');
const out = resolve(process.argv[3] || 'docs/qa/evidence/pages');
mkdirSync(out, { recursive: true });
const fixturePort = 18039;
const upstream = spawn(process.execPath, ['scripts/visual-preview-server.mjs'], { env: { ...process.env, TEXA_VISUAL_PORT: String(fixturePort) }, stdio: 'ignore' });
let scenario = 'populated';
const time = '2026-10-01T08:00:00Z';
const note = { id:'qa-note', title:'等价无穷小与泰勒展开：相减时保留有效阶', abstract:'比较替换误差与目标表达式的阶数，避免一次项相消后丢失有效信息。', subject:'数学/高数', tags:['极限','泰勒公式'], revision:1, status:'active', updated_at:time, origins:[{conversation_id:'visual-session-0',title_snapshot:'等价无穷小',captured_at:time}], chapter_refs:[], quality:{warning_hash:'qa',warnings:[],semantic_review:'unknown'}, blocks:[{block_id:'b1',type:'heading',data:{text:'判断替换是否安全',level:2},source_ref_ids:[],evidence_ref_ids:[]},{block_id:'b2',type:'paragraph',data:{markdown:'在相减的表达式中，首先判断一次项是否相消。$\\sin x=x-\\frac{x^3}{6}+o(x^3)$，因此 $\\lim_{x\\to0}\\frac{x-\\sin x}{x^3}=\\frac16$。'},source_ref_ids:[],evidence_ref_ids:[]}] };
const draft = { id:'qa-draft',title:note.title,updated_at:time,kind:'manual',status:'editable',draft_revision:1,conversation_id:'visual-session-0',content:note,source_snapshot_ids:['qa-source'],base_note_id:null,base_note_revision:null,job_id:null,sources:[],chapter_options:[] };
const mistake = { id:'visual-mistake-1', revision:1, status:'active', question_text:'求 $\\lim_{x\\to0}(x-\\sin x)/x^3$，说明不能直接等价替换的原因。',correct_answer:'$1/6$',user_answer:'0',explanation:'一次项相消，须保留三阶。',subject:'数学/高数',chapter:'泰勒公式',source:'高等数学 · 上册',tags:['极限'],mistake_type:['公式记错'],difficulty:3,created_at:time,next_review:'2026-10-01',review_history:[],linked_concepts:[] };
const intake = { id:'qa-intake',revision:1,...mistake,attachments:[],content_complete:true };
const review = { id:'qa-review',revision:1,items:[mistake.id],index:0,results:{},current_answer:'',revealed:false,current_item:mistake };
const unhandled = new Set();
const requests = [];
const server = createServer(async (req,res) => {
 try {
  const url = new URL(req.url,'http://127.0.0.1'); const p=url.pathname;
  if (p.startsWith('/api/') || p === '/health') {
   requests.push({scenario,method:req.method,path:p});
   res.setHeader('Content-Type','application/json');
   const bootstrap = ['/api/system/settings','/api/system/assets/status','/api/books/list','/api/system/health','/api/chat/conversations'].includes(p);
   if (!bootstrap && scenario === 'loading') await new Promise(r=>setTimeout(r,3000));
   if (!bootstrap && scenario === 'error') {res.writeHead(503);res.end(JSON.stringify({success:false,message:'QA fixture：服务暂不可用，请重试'}));return;}
   let data;
   if (p === '/api/chat/conversations') {const value=await (await fetch(`http://127.0.0.1:${fixturePort}${req.url}`)).json();data={items:value.data.map(x=>({...x,management:{state:'active',pinned:false,revision:0}})),next_cursor:null,has_more:false};}
   else if (p.endsWith('/management')) data={state:'active',pinned:false,revision:0};
   else if (p === '/api/system/settings/subjects') data={subjects:[{name:'数学',children:['高数','线代','概率论']}]};
   else if (p === '/api/system/backups') data=[];
   else if (p === '/api/system/network-diagnostics') data={observation:{path:'unknown',source:'qa-fixture',sampled_at:time,error_code:'qa_no_real_device'},changed_at:time,last_probe:null,history:[],samples:[],target_selected:false,probe_cooldown_seconds:0};
   else if (p === '/api/review/sessions') data=null;
   else if (p === '/api/exercises/answer/jobs/latest') data=null;
   else if (p === '/api/books/import-capabilities') data={mineru:{available:false,message:'QA fixture无外部OCR'},external_output:{available:true},pdf:{available:true}};
   else if (p === '/api/notes/filters') data={books:[],chapter_refs:[]};
   else if (p === '/api/notes') data={items:scenario==='empty'?[]:[note],next_cursor:null};
   else if (p === '/api/notes/drafts') data={items:scenario==='empty'?[]:[draft],next_cursor:null};
   else if (p === '/api/notes/drafts/qa-draft') data=draft;
   else if (p === '/api/notes/qa-note/revisions') data={items:[],next_cursor:null};
   else if (p === '/api/notes/qa-note') data=note;
   else if (p === '/api/mistakes/query') data={items:scenario==='empty'?[]:[mistake],next_cursor:null};
   else if (p === '/api/mistakes/candidates') data=[];
   else if (p === '/api/mistakes/drafts') data=scenario==='empty'?[]:[{...intake,id:'qa-intake',updated_at:time}];
   else if (p === '/api/mistakes/drafts/qa-intake') data={...intake,id:'qa-intake'};
   else if (p === '/api/mistakes/visual-mistake-1') data=mistake;
   else if (p === '/api/mistakes/diagnosis') data={record_count:1,groups:[],reasons:[],unconfirmed_diagnosis_count:1,comparison:{cohort_mistake_ids:[],prior_correct:0,prior_total:0,recent_correct:0,recent_total:0,comparable:false},actions:[],scope:{prior_start:'2026-08-01',recent_start:'2026-09-01',end:'2026-10-01'}};
   else if (p === '/api/review/sessions/qa-review') data=review;
   else if (p === '/api/reports/weekly') data={book_name:'高等数学 · 上册',subject:'数学/高数',start_date:'2026-09-25',end_date:'2026-10-01',summary:{qa_count:5,mistake_count:2},top_concepts:[{name:'泰勒公式',count:4}],weak_points:[{name:'等价替换',count:2}],recent_questions:[{time,question:mistake.question_text}],suggestions:['完成两道极限题，并说明有效阶数。']};
   else if (p.includes('/chapter-highlights/')) data={markdown:'## 极限与相减结构\n\n先判断相消，再保留有效阶。\n\n$$\\sin x=x-\\frac{x^3}{6}+o(x^3)$$\n\n## 例题\n\n'+mistake.question_text,metadata:{chapter_title:'第三章 · 泰勒公式',completed_at:time}};
   else {
    const r=await fetch(`http://127.0.0.1:${fixturePort}${req.url}`,{method:req.method});const value=await r.json();
    if (!r.ok) unhandled.add(`${req.method} ${p}`);
    if (scenario==='empty' && ['GET','POST'].includes(req.method) && ['/api/goals','/api/mistakes/due'].includes(p)) value.data=[];
    res.writeHead(r.status);res.end(JSON.stringify(value));return;
   }
   if(scenario==='empty' && p==='/api/reports/weekly')data={...data,summary:{},top_concepts:[],weak_points:[],recent_questions:[],suggestions:[]};
   res.end(JSON.stringify({success:true,data}));return;
  }
  let file=resolve(dist,p==='/'?'index.html':`.${p}`);if(!file.startsWith(dist+'/')){res.writeHead(403);res.end();return;}
  if (!extname(p)) file=resolve(dist,'index.html');
  const bytes=readFileSync(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2','.ttf':'font/ttf'})[extname(file)]||'application/octet-stream');res.end(bytes);
 } catch(e){res.writeHead(500);res.end(String(e));}
});
const routes=[['chat','/?conversation_id=visual-session-0'],['goals','/goals'],['notes','/notes'],['note','/notes/qa-note'],['draft','/notes/drafts/qa-draft'],['mistakes','/mistakes'],['diagnosis','/mistakes/diagnosis'],['intake','/mistakes/intake'],['intake-draft','/mistakes/intake/qa-intake'],['mistake','/mistakes/visual-mistake-1'],['exercises','/exercises'],['learning','/learning'],['review-start','/learning/review'],['review','/learning/review/qa-review'],['weekly','/weekly'],['books','/books'],['book-import','/books/import'],['highlights','/highlights?book_name=qa-book&chapter_id=qa-chapter'],['settings','/settings']];
if(process.env.TEXA_QA_ROUTES){const selected=new Set(process.env.TEXA_QA_ROUTES.split(','));routes.splice(0,routes.length,...routes.filter(([name])=>selected.has(name)));}
const results={fixture:true,started:new Date().toISOString(),routes:routes.length,checks:[],interactions:[],unhandled:[],errors:[]};
let browser;
async function capture(page,name){await page.screenshot({path:resolve(out,`${name}.png`)});return await page.evaluate(()=>({status:document.body.innerText.includes('页面文件未能加载')?'FAIL':'PASS',title:document.querySelector('.persistent-route-panel:not([hidden]) h1')?.textContent,bodyWidth:document.body.scrollWidth,viewport:innerWidth,alerts:[...document.querySelectorAll('[role=alert]')].filter(e=>e.getBoundingClientRect().height).map(e=>e.textContent)}));}
try {
 await new Promise(r=>server.listen(18040,'127.0.0.1',r));
 browser=await chromium.launch({executablePath:process.env.TEXA_QA_BROWSER || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 for(const [width,height] of [[1280,820],[1024,768],[760,820],[390,844]]) {
  const context=await browser.newContext({viewport:{width,height}});await context.addInitScript(()=>localStorage.setItem('texa:setup-complete:v3','1'));const page=await context.newPage();page.on('console',message=>{if(message.type()==='error')results.errors.push({console:message.text()});});
  page.on('pageerror',e=>results.errors.push({width,error:e.message}));
  await page.addInitScript(()=>{localStorage.setItem('kaoyan_subject','数学/高数');localStorage.setItem('texa_appearance_theme','mineral');});
  for(const [name,path] of routes){scenario='populated';await page.goto(`http://127.0.0.1:18040${path}`);await page.waitForLoadState('networkidle');await page.waitForTimeout(200);await page.evaluate(()=>document.fonts.ready);results.checks.push({name,path,width,state:scenario,...await capture(page,`${width}-${name}`)});}
  await context.close();
 }
 // Representative route states; app bootstrap remains available to reach each feature.
 for(const state of ['empty','loading','error']){
  const context=await browser.newContext({viewport:{width:390,height:844}});await context.addInitScript(()=>localStorage.setItem('texa:setup-complete:v3','1'));const page=await context.newPage();page.on('console',message=>{if(message.type()==='error')results.errors.push({console:message.text()});});
  page.on('pageerror',e=>results.errors.push({state,error:e.message}));
  for(const [name,path] of routes.filter(([name])=>['notes','mistakes','goals','intake','review-start','weekly','book-import'].includes(name))){scenario=state;await page.goto(`http://127.0.0.1:18040${path}`);await page.waitForFunction(()=>!document.body.innerText.includes('正在加载页面…') && Boolean(document.querySelector('.persistent-route-panel:not([hidden])')));if(state!=='loading') await page.waitForLoadState('networkidle');await page.waitForTimeout(200);results.checks.push({name,path,width:390,state,...await capture(page,`${state}-${name}`)});
   if(state==='error' && ['notes','review-start'].includes(name)) {
    if(name==='notes' && await page.getByText('还没有保存的笔记',{exact:true}).count())throw Error('notes error falsely empty');
    if(name==='review-start' && await page.getByRole('button',{name:'开始复习',exact:true}).count())throw Error('review starts after read error');
    scenario='populated';await page.getByRole('button',{name:name==='notes'?'重新读取':'重试读取',exact:true}).click();
    await (name==='notes'?page.getByRole('link',{name:note.title}):page.getByRole('button',{name:'开始复习',exact:true})).waitFor();
    if(await page.getByRole('alert').count())throw Error('retry retains read error');
    results.checks.push({name,path,width:390,state:'retry-success',...await capture(page,`retry-${name}`)});results.interactions.push(`${name} error→retry→success`);
   }
  }
  await context.close();
 }
 scenario='populated';
 // All stored themes, plus dark mode preference on representative reading/management/modal views.
 for(const theme of ['graphite','clay','notebook','codex']){
  const context=await browser.newContext({viewport:{width:1280,height:820},colorScheme:'dark'});await context.addInitScript(()=>localStorage.setItem('texa:setup-complete:v3','1'));const page=await context.newPage();page.on('console',message=>{if(message.type()==='error')results.errors.push({console:message.text()});});
  await page.addInitScript(t=>localStorage.setItem('texa_appearance_theme',t),theme);
  for(const [name,path] of routes.filter(([name])=>['chat','notes','mistakes','learning','settings'].includes(name))){await page.goto(`http://127.0.0.1:18040${path}`);await page.waitForLoadState('networkidle');await page.waitForTimeout(200);results.checks.push({name,path,width:1280,state:theme,...await capture(page,`${theme}-${name}`)});}
  await context.close();
 }
 const context=await browser.newContext({viewport:{width:1280,height:820}});await context.addInitScript(()=>localStorage.setItem('texa:setup-complete:v3','1'));const page=await context.newPage();page.on('console',message=>{if(message.type()==='error')results.errors.push({console:message.text()});});
 await page.goto('http://127.0.0.1:18040/notes');await page.waitForLoadState('networkidle');await page.getByRole('button',{name:'筛选',exact:true}).click();await capture(page,'interaction-notes-filters');results.interactions.push('notes filter expand');
 await page.getByRole('button',{name:'草稿',exact:true}).click();await page.getByRole('link',{name:note.title}).click();await page.getByRole('button',{name:'阅读预览',exact:true}).click();await page.getByRole('button',{name:'编辑笔记',exact:true}).click();await capture(page,'interaction-note-edit');results.interactions.push('notes tab→draft→edit');
 await page.goto('http://127.0.0.1:18040/settings');await page.waitForLoadState('networkidle');await page.waitForTimeout(200);
 for(const label of ['偏好','模型连接','数据与教材','关于与更新','高级与诊断']){const button=page.getByRole('button',{name:label,exact:true});if(await button.count()){await button.click();await page.waitForTimeout(250);await capture(page,`interaction-settings-${label}`);results.interactions.push(`settings ${label}`);}}
 // Narrow shared settings navigation: focus and unsaved field survive returning.
 await page.setViewportSize({width:390,height:844});
 await page.goto('http://127.0.0.1:18040/settings');await page.waitForLoadState('networkidle');
 await capture(page,'390-settings-content');
 await page.getByRole('button',{name:'返回设置',exact:true}).click();
 await page.waitForFunction(()=>document.activeElement?.textContent==='偏好');
 await capture(page,'390-settings-navigation');
 await page.getByRole('button',{name:'数据与教材',exact:true}).click();
 await page.waitForFunction(()=>document.activeElement?.textContent==='返回设置');
 const parserUrl=page.getByPlaceholder('http://127.0.0.1:9001',{exact:true});await parserUrl.fill('http://127.0.0.1:9001/qa-unsaved');
 await capture(page,'390-settings-data');
 await page.getByRole('button',{name:'返回设置',exact:true}).click();await page.getByRole('button',{name:'数据与教材',exact:true}).click();
 if(await parserUrl.inputValue()!=='http://127.0.0.1:9001/qa-unsaved')throw Error('unsaved settings lost on return');
 await page.getByRole('button',{name:'返回设置',exact:true}).click();await page.getByRole('button',{name:'模型连接',exact:true}).click();await page.waitForLoadState('networkidle');
 await capture(page,'390-settings-models');
 await page.keyboard.press('Tab');if(await page.locator('.settings-sidebar button:focus').count())throw Error('hidden navigation captures focus');
 await page.getByRole('button',{name:'关闭设置',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.setViewportSize({width:760,height:820});await page.goto('http://127.0.0.1:18040/books/import');await page.waitForLoadState('networkidle');
 await page.locator('input[type=file]').first().setInputFiles({name:'考研数学学习资料_长教材名称与完整章节目录_解析参数与导入取消验收.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nQA')});
 await page.locator('.management-page-content').evaluate(el=>el.parentElement.scrollTop=el.parentElement.scrollHeight);
 await capture(page,'760-import-long-scroll-end');
 await page.goto('http://127.0.0.1:18040/settings');await page.waitForLoadState('networkidle');
 await page.keyboard.press('Tab');
 results.interactions.push('390 settings navigation→detail focus→unsaved fields preserved→keyboard');
 await page.getByRole('button',{name:'关闭设置',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
 await context.close();
 if(results.checks.some(x=>x.status==='FAIL'||x.bodyWidth>x.viewport) || results.errors.some(x=>x.error))throw Error('page render/overflow checks failed');
} catch(e){results.errors.push({harness:String(e)});process.exitCode=1;}
finally{results.unhandled=[...unhandled];results.requests=requests;writeFileSync(resolve(out,'results.json'),JSON.stringify(results,null,2));await browser?.close();await new Promise(r=>server.close(r));upstream.kill();}
