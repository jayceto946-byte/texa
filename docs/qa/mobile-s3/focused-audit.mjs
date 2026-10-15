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
const fixturePort = 18049;
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
  if (p === '/api/chat/stream') {
   let raw='';for await(const chunk of req)raw+=chunk;const input=JSON.parse(raw);
   requests.push({scenario,method:req.method,path:p});
   res.writeHead(200,{'Content-Type':'text/event-stream'});
   const base={schema:'texa.execution/v1',request_id:'s3-req',task_id:'s3-task',run_id:'s3-run',conversation_id:input.conversation_id,turn_id:input.turn_id,elapsed_ms:1,kind:'system',payload:{}};
   const task={schema_version:'learning-task/v1',id:'s3-task',task_type:'qa',goal:input.question,status:'running',required_inputs:[],required_outputs:[],terminal:false,interruptible:true,resumable:false,input_action_required:false,confirmation_required:false,active_run_id:'s3-run'};
   const emit=e=>res.write('data: '+JSON.stringify({execution_event:{...base,...e},learning_task:task})+'\n\n');
   emit({seq:1,type:'progress',phase:'context',operation_id:'context',label:'解析学习上下文',summary:'正在读取当前教材范围',status:'running'});
   await new Promise(r=>setTimeout(r,1000));
   emit({seq:2,type:'progress',phase:'tool',operation_id:'math',label:'校验积分',summary:'正在执行受限数学工具',status:'running',kind:'tool'});
   await new Promise(r=>setTimeout(r,4000));
   emit({seq:3,type:'progress',phase:'tool',operation_id:'math',label:'校验积分',summary:'校验完成',status:'completed',kind:'tool'});
   emit({seq:4,type:'output_delta',phase:'generation',operation_id:'answer',label:'生成回答',summary:'正在生成',status:'running',payload:{text:'合成审计回答：$\\int_0^1 x^2 dx=\\frac13$。\n\n'+('解释有效阶与教材范围。\n\n'.repeat(35)),replace:false}});
   await new Promise(r=>setTimeout(r,5000));
   task.status='completed';task.terminal=true;task.interruptible=false;
   emit({seq:5,type:'final',phase:'final',operation_id:'answer',label:'回答完成',summary:'已完成',status:'completed',payload:{task_status:'completed'}});res.end();return;
  }
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

const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
await new Promise(r=>server.listen(18050,'127.0.0.1',r));
const result={fixture:true,build:'f999e72',checks:[],screenshots:[],errors:[],requests};
async function shot(page,name){await page.screenshot({path:resolve(out,name+'.png')});result.screenshots.push(name+'.png');}
async function metrics(page){return await page.evaluate(()=>({body:document.body.scrollWidth,viewport:innerWidth,controls:[...document.querySelectorAll('button,a,input,textarea,select')].map(e=>{const r=e.getBoundingClientRect(),c=getComputedStyle(e);return {name:e.getAttribute('aria-label')||e.textContent?.trim().slice(0,60),w:r.width,h:r.height,x:r.x,y:r.y,visible:r.width>0&&r.height>0&&c.visibility!=='hidden'};}).filter(e=>e.visible&&e.y>=0&&e.y<innerHeight),overflow:[...document.querySelectorAll('main,article,.markdown-body,.katex-display,table')].map(e=>({tag:e.className,w:e.clientWidth,scroll:e.scrollWidth}))}));}
const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await context.addInitScript(()=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学/高数');});
const page=await context.newPage();page.on('pageerror',e=>result.errors.push(String(e)));page.setDefaultTimeout(10000);
async function goto(path){await page.goto('http://127.0.0.1:18050'+path);await page.waitForLoadState('networkidle');await page.evaluate(()=>document.fonts.ready);}
try{
for(const width of [360,390,430]){await page.setViewportSize({width,height:844});for(const [name,path] of routes.filter(([n])=>['chat','books','highlights','note','draft','mistakes','mistake','notes'].includes(n))){await goto(path);result.checks.push({name,width,...await metrics(page)});await shot(page,width+'-'+name+'-touch');await page.evaluate(()=>{for(const e of document.querySelectorAll('*'))if(e.scrollHeight>e.clientHeight+10&&getComputedStyle(e).overflowY==='auto')e.scrollTop=e.scrollHeight;});await shot(page,width+'-'+name+'-bottom');}}
await page.setViewportSize({width:390,height:844});await goto('/?conversation_id=visual-session-0');
const opener=page.getByRole('button',{name:'打开学习导航',exact:true});
if(await opener.count())await opener.click();else {const buttons=await page.getByRole('button').all();for(const b of buttons)if(/展开侧栏|打开侧栏|打开导航/.test(await b.getAttribute('aria-label')||'')){await b.click();break;}}
await shot(page,'390-navigation-history');result.checks.push({name:'navigation',...await metrics(page)});
await goto('/?conversation_id=visual-session-0');await page.locator('.composer-textarea').fill('保留输入：章节中的这个条件是什么意思？');
await page.locator('.composer-textarea').focus();await page.setViewportSize({width:390,height:480});await shot(page,'390-composer-height-simulation');result.checks.push({name:'keyboard-height-simulation',...await metrics(page)});
await page.setViewportSize({width:390,height:844});await page.locator('.composer-textarea').press('Enter');await page.waitForTimeout(1800);await shot(page,'390-stream-tool');
const toggle=page.locator('.execution-trace-toggle').last();if(await toggle.count())await toggle.click();await shot(page,'390-stream-tool-expanded');
await page.waitForTimeout(4000);await shot(page,'390-stream-body');await page.locator('.learning-workspace-scroll').evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event('scroll'));});await page.waitForTimeout(200);await shot(page,'390-stream-read-top');
await page.waitForTimeout(5500);await shot(page,'390-stream-final');result.checks.push({name:'stream-final',text:await page.locator('.execution-trace').last().innerText(),...await metrics(page)});
await goto('/notes');await page.getByRole('button',{name:'筛选',exact:true}).click();await shot(page,'390-notes-filters');
await goto('/notes/drafts/qa-draft');if(await page.getByRole('button',{name:'编辑笔记',exact:true}).count())await page.getByRole('button',{name:'编辑笔记',exact:true}).click();await shot(page,'390-note-editor');result.checks.push({name:'note-editor',...await metrics(page)});
await goto('/settings');await page.getByRole('button',{name:'返回设置',exact:true}).click();await page.getByRole('button',{name:'模型连接',exact:true}).click();await page.waitForLoadState('networkidle');await shot(page,'390-model-settings');result.checks.push({name:'models',...await metrics(page)});
}catch(e){result.errors.push(String(e));await shot(page,'focused-failure');process.exitCode=1;}
finally{writeFileSync(resolve(out,'focused-results.json'),JSON.stringify(result,null,2));await browser.close();server.close();upstream.kill();}
