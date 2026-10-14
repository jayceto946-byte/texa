from pathlib import Path
s=Path('scripts/qa-pages.mjs').read_text()
s=s[:s.index('let browser;')]
s=s.replace('18039','18049').replace('18040','18050')
s=s.replace("  if (p.startsWith('/api/') || p === '/health') {", """  if (p === '/api/chat/stream') {
   let raw='';for await(const chunk of req)raw+=chunk;const input=JSON.parse(raw);
   requests.push({scenario,method:req.method,path:p});
   res.writeHead(200,{'Content-Type':'text/event-stream'});
   const base={schema:'texa.execution/v1',request_id:'s3-req',task_id:'s3-task',run_id:'s3-run',conversation_id:input.conversation_id,turn_id:input.turn_id,elapsed_ms:1,kind:'system',payload:{}};
   const task={schema_version:'learning-task/v1',id:'s3-task',task_type:'qa',goal:input.question,status:'running',required_inputs:[],required_outputs:[],terminal:false,interruptible:true,resumable:false,input_action_required:false,confirmation_required:false,active_run_id:'s3-run'};
   const emit=e=>res.write('data: '+JSON.stringify({execution_event:{...base,...e},learning_task:task})+'\\n\\n');
   emit({seq:1,type:'progress',phase:'context',operation_id:'context',label:'解析学习上下文',summary:'正在读取当前教材范围',status:'running'});
   await new Promise(r=>setTimeout(r,1000));
   emit({seq:2,type:'progress',phase:'tool',operation_id:'math',label:'校验积分',summary:'正在执行受限数学工具',status:'running',kind:'tool'});
   await new Promise(r=>setTimeout(r,4000));
   emit({seq:3,type:'progress',phase:'tool',operation_id:'math',label:'校验积分',summary:'校验完成',status:'completed',kind:'tool'});
   emit({seq:4,type:'output_delta',phase:'generation',operation_id:'answer',label:'生成回答',summary:'正在生成',status:'running',payload:{text:'合成审计回答：$\\\\int_0^1 x^2 dx=\\\\frac13$。\\n\\n'+('解释有效阶与教材范围。\\n\\n'.repeat(35)),replace:false}});
   await new Promise(r=>setTimeout(r,5000));
   task.status='completed';task.terminal=true;task.interruptible=false;
   emit({seq:5,type:'final',phase:'final',operation_id:'answer',label:'回答完成',summary:'已完成',status:'completed',payload:{task_status:'completed'}});res.end();return;
  }
  if (p.startsWith('/api/') || p === '/health') {""")
s+='''
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
'''
Path('/tmp/texa-mobile-s3-focused.mjs').write_text(s)
