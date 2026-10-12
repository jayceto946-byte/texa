/** Incremental cross-module QA, using the existing isolated real API server. */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {chromium,_electron}=createRequire(import.meta.url)('playwright');
const electronMode=process.env.TEXA_QA_ELECTRON==='1';
const out=resolve(process.env.TEXA_QA_E2E_OUT||'docs/qa/evidence/cross-module/current');mkdirSync(out,{recursive:true});
const base='http://127.0.0.1:18041';
const mark='QA-CROSS-'+Date.now();
if(electronMode){mkdirSync('/tmp/texa-cross-module-electron',{recursive:true});writeFileSync('/tmp/texa-cross-module-electron/setup-complete.json',JSON.stringify({version:3,complete:true}));}
const browser=electronMode?await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:'/tmp/texa-cross-module-electron',KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:base,KAOYAN_FRONTEND_DEV_URL:base}}):await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const context=electronMode?browser.context():await browser.newContext({viewport:{width:1280,height:820}});
await context.addInitScript(()=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学');});
const page=electronMode?await browser.firstWindow():await context.newPage();page.setDefaultTimeout(12000);
if(electronMode){await page.waitForURL(url=>url.searchParams.has('desktop_launch'));await page.waitForLoadState('networkidle');}
const result={environment:electronMode?'macOS Electron development shell':'Chrome',model:'offline fixture',checks:[],errors:[]};
page.on('pageerror',e=>result.errors.push(String(e).replace(/access_token=[^&\s"']+/g,'access_token=[REDACTED]')));
const api=async(path,method='GET',data)=>{const r=await context.request.fetch(base+'/api'+path,{method,data});const v=await r.json();if(!r.ok()||!v.success)throw Error(path+': '+JSON.stringify(v));return v;};
const shot=async name=>{await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:resolve(out,name+'.png')});};
const check=async(name,work)=>{try{await work();result.checks.push({name,status:'PASS'});}catch(e){result.checks.push({name,status:'FAIL',error:String(e).replace(/access_token=[^&\s"']+/g,'access_token=[REDACTED]')});process.exitCode=1;await shot('failure-'+name);}writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));};
try{
await check('goal-double-resume',async()=>{
 let goal=(await api('/goals','POST',{title:mark,objective:'读取近期学习记录',scope:{},success_criteria:[]})).data;
 goal=(await api('/goals/'+goal.id+'/commands','POST',{expected_revision:goal.revision,operation:'activate'})).data;
 const first=(await api('/goals/'+goal.id+'/run','POST',{expected_revision:goal.revision,request_key:mark+'-start'})).data;
 goal=(await api('/goals/'+goal.id+'/commands','POST',{expected_revision:goal.revision,operation:'pause'})).data;
 goal=(await api('/goals/'+goal.id+'/commands','POST',{expected_revision:goal.revision,operation:'activate'})).data;
 await page.goto(base+'/goals');await page.locator('.goal-list-item').filter({hasText:mark}).click();
 const button=page.getByRole('button',{name:'继续执行',exact:true});await button.waitFor();
 let submits=0;const track=req=>{if(req.method()==='POST'&&req.url()===base+'/api/goals/'+goal.id+'/run')submits++;};page.on('request',track);
 await button.evaluate(el=>{for(let i=0;i<12;i++)el.click();});
 await page.getByRole('heading',{name:/本次任务.*正在执行/}).waitFor();
 if(submits!==1)throw Error('double click sent '+submits+' submissions');
 page.off('request',track);
 const second=(await api('/goals/'+goal.id+'/runtime')).data;
 if(second.id!==first.id||second.active_run_id===first.active_run_id)throw Error('resume lost task or reused stopped run');
 const duplicate=(await api('/goals/'+goal.id+'/run','POST',{expected_revision:goal.revision,request_key:mark+'-other',task_id:first.id})).data;
 if(duplicate.active_run_id!==second.active_run_id)throw Error('backend created another run');
 await page.locator('.goal-events summary').click();
 if(/run\.resumed|model\.started|Runtime/.test(await page.locator('.goal-events').innerText()))throw Error('raw lifecycle visible');
 await shot('1280-goal-running');
 await page.goto(base+'/notes');const across=(await api('/goals/'+goal.id+'/runtime')).data;if(across.id!==first.id)throw Error('cross-page task identity changed');
});
await check('chat-selection-composer-mistakes',async()=>{
 const conversationId=mark+'-chat';
 await api('/chat/log','POST',{conversation_id:conversationId,turn_id:'cross-turn',subject:'数学',messages:[{role:'user',content:'说明可导与连续的关系'},{role:'assistant',content:'可导推出连续，连续未必可导。\n\n例如 $f(x)=|x|$ 在零点连续，但左右导数不同。'}]});
 await api('/mistakes/add','POST',{question_text:'求 $\\lim_{x\\to0}\\frac{x-\\sin x}{x^3}$。',subject:'数学',correct_answer:'$1/6$',user_answer:'0',explanation:'保留三阶。',tags:'QA',difficulty:3});
 await page.goto(base+'/?conversation_id='+conversationId);await page.getByText('例如',{exact:false}).waitFor();await page.locator('.learning-answer-document .katex').first().waitFor();
 const input=page.locator('.composer-textarea');await input.fill('我原来的追问');
 await page.locator('.answer-selection').evaluate(el=>{const p=el.querySelector('p');const range=document.createRange();range.selectNodeContents(p);const s=getSelection();s.removeAllRanges();s.addRange(range);});
 await page.getByRole('button',{name:'添加到对话',exact:true}).click();
 if(!(await input.inputValue()).includes('我原来的追问\n\n引用回答：\n> 可导推出连续'))throw Error('quote lost original draft');
 if(await page.getByRole('button',{name:'回答有帮助'}).count())throw Error('feedback entry remains');
 if(await page.getByRole('button',{name:'拍照提问'}).count())throw Error('desktop camera entry remains');
 await input.fill(Array.from({length:10},(_,i)=>'第'+i+'行公式追问').join('\n'));
 const tall=await input.evaluate(e=>e.getBoundingClientRect().height);if(tall<150||tall>245)throw Error('composer height '+tall);
 await input.fill('短问题');const short=await input.evaluate(e=>e.getBoundingClientRect().height);if(short>=tall)throw Error('composer does not shrink');
 const picker=page.getByRole('button',{name:'选择历史错题',exact:true});await picker.click();
 await page.locator('[aria-label="历史错题"] .katex').first().waitFor();await shot('1280-chat-mistakes');
 await page.keyboard.press('Escape');if(await page.locator('[aria-label="历史错题"]').count())throw Error('Esc kept picker');
 if(!await picker.evaluate(e=>e===document.activeElement))throw Error('Esc lost focus');
 await picker.click();await page.getByText('TEXA / 解答',{exact:true}).click();if(await page.locator('[aria-label="历史错题"]').count())throw Error('outside kept picker');
 await shot('1280-chat-quote');
});
await check('chat-process-continuity',async()=>{
 await page.goto(base+'/');await page.locator('.composer-textarea').fill(mark+' 为什么可导一定连续？');
 await page.locator('.composer-textarea').press('Enter');
 const trace=page.locator('.execution-trace').last();await trace.waitFor();
 await trace.locator('.execution-trace-toggle').click();
 await page.getByText('离线夹具：可导推出连续，连续未必可导。',{exact:true}).waitFor();
 await trace.locator('.execution-trace-body').waitFor();
 if(await trace.locator('.execution-trace-toggle').getAttribute('aria-expanded')!=='true')throw Error('process collapsed on completion');
 if(await trace.locator('.execution-live-preview').count())throw Error('redundant recent steps remain');
 if((await trace.innerText()).includes('综合证据与知识推理'))throw Error('synthetic reasoning phase remains');
 if(await trace.locator('.execution-step.is-completed').filter({hasText:'检索教材上下文'}).count())throw Error('unobserved retrieval shown completed');
 if(await trace.locator('.execution-step.is-pending').count())throw Error('planned-only steps remain');
 await shot('1280-chat-process');
});
await check('review-assets-explicit-record',async()=>{
 const pattern='**/api/kg/learning-summary?**';
 await page.route(pattern,async route=>{const response=await route.fetch();const value=await response.json();value.data.due_mistakes=[];value.data.mistake_stats.due_today=0;value.data.concept_review_plan=[{name:'QA 可导与连续',priority:1,reasons:['已标记薄弱'],exposure_count:3,days_since_review:null,recent_questions:[{question:'为什么可导推出连续？',source:'qa',timestamp:''}],related_mistakes:[],textbook_snippets:[{type:'definition',chapter:'合成教材线索',text:'由 $f(x)-f(0)=x \\cdot \\frac{f(x)-f(0)}{x}$ 理解连续性。'}]}];await route.fulfill({response,json:value});});
 let writes=0;const track=req=>{if(req.method()==='POST'&&req.url().includes('/kg/concept-review'))writes++;};page.on('request',track);
 await page.goto(base+'/learning');await page.getByRole('button',{name:'QA 可导与连续',exact:false}).click();
 await page.locator('.review-detail .katex').first().waitFor();if(writes!==0)throw Error('opening concept wrote review');
 for(const width of [1280,1024,760]){await page.setViewportSize({width,height:820});await shot(width+'-review-assets');}
 await page.getByRole('button',{name:'记录本次复习',exact:true}).first().click();await page.getByText('已记录「QA 可导与连续」的概念复习，今天不再提醒',{exact:true}).waitFor();
 if(writes!==1)throw Error('explicit review wrote '+writes+' times');page.off('request',track);await page.unroute(pattern);await page.setViewportSize({width:1280,height:820});
});
await check('notes-generated-read-edit-save',async()=>{
 const id='qa-readable-'+mark;
 await api('/chat/log','POST',{conversation_id:id,turn_id:'note-turn',subject:'数学',messages:[{role:'user',content:'可导与连续有什么关系？'},{role:'assistant',content:'可导推出连续，连续未必可导。\n\n$f(x)=|x|$ 是反例。'}]});
 const pre=(await api('/notes/preflight','POST',{selection:{conversation_id:id}})).data;
 const gen=(await api('/notes/generations','POST',{selection:pre.selection,preflight_fingerprint:pre.fingerprint,operation_id:mark+'-note'})).data;
 await page.goto(base+'/notes/drafts/'+gen.draft_id);
 await page.getByRole('heading',{name:'对话整理笔记',exact:true}).waitFor();
 if(await page.getByLabel('第 1 块正文',{exact:true}).count())throw Error('generation defaults to block editor');
 await page.locator('.note-document .katex').first().waitFor();await shot('1280-note-generated-read');
 await page.getByRole('button',{name:'编辑笔记',exact:true}).click();
 const body=page.getByLabel('第 1 块正文',{exact:true});await body.fill('自主订正：可导是连续的充分条件。$f(x)=|x|$ 连续但不可导。');
 await page.getByText('草稿已保存',{exact:true}).waitFor();
 await page.getByRole('button',{name:'保存笔记',exact:true}).click();await page.waitForURL(/\/notes\/(?!drafts)[^/?]+/);
 await page.reload();await page.getByText('自主订正：可导是连续的充分条件。',{exact:false}).waitFor();await shot('1280-note-saved');
});
await check('exercise-answer-job-failure-retry-read-save',async()=>{
 const priorSession=(await api('/exercises/practice-sessions/active')).data;
 const exercise=(await api('/exercises/add','POST',{question_text:'QA-ANSWER-FAIL '+mark+' 求 $x^3$ 的导数。',subject:'数学',explanation:'先写 $f(x)=x^3$，再用幂函数求导法则。\n\n'+('完整解析：确认变量、指数及定义域。\n\n'.repeat(20)),origin_type:'manual'})).data;
 await page.goto(base+'/exercises');await page.getByRole('radio',{name:'题库',exact:true}).click();
 await page.getByPlaceholder('搜索题干/答案/解析/标签').fill(mark);await page.getByPlaceholder('搜索题干/答案/解析/标签').press('Enter');
 await page.locator('.workspace-register-row').filter({hasText:mark}).getByRole('button').first().click();await page.getByRole('button',{name:'设为当前练习',exact:true}).click();
 if(await page.getByRole('button',{name:'手动录入',exact:true}).count())throw Error('maintenance entry mixed into active practice');
 await page.getByLabel('你的作答',{exact:true}).fill('$3x^2$');await page.getByRole('button',{name:'查看参考答案',exact:true}).click();
 if(await page.getByLabel('答案草稿',{exact:true}).isVisible())throw Error('reference answer defaults to editor');
 await page.getByText('维护题库答案',{exact:true}).click();
 let submissions=0;const track=req=>{if(req.method()==='POST'&&req.url().includes('/exercises/answer/jobs'))submissions++;};page.on('request',track);
 const pollPattern='**/api/exercises/answer/jobs/*';let failPoll=true;
 await page.route(pollPattern,async route=>{if(route.request().method()==='GET'&&!route.request().url().endsWith('/latest')&&failPoll){failPoll=false;await route.fulfill({status:503,json:{success:false,message:'QA polling unavailable'}});}else await route.continue();});
 await page.getByRole('button',{name:'基于教材生成草稿',exact:true}).evaluate(el=>{for(let i=0;i<8;i++)el.click();});
 await page.getByRole('button',{name:'正在生成…',exact:true}).waitFor();await shot('1280-exercise-answer-running');await page.getByText('连接中断，后台任务可能仍在执行；正在重新读取状态。',{exact:true}).waitFor();await shot('1280-exercise-poll-unavailable');
 await page.getByText('合成任务首次生成失败，可重试',{exact:true}).waitFor();await page.unroute(pollPattern);if(submissions!==1)throw Error('double generation submitted '+submissions+' jobs');await shot('1280-exercise-answer-failed');
 await page.getByRole('button',{name:'重试生成答案',exact:true}).click();
 await page.getByText('答案草稿已生成，可阅读或编辑，保存后才写入题库。',{exact:true}).waitFor();
 await page.getByText('维护题库答案',{exact:true}).click();
 for(const width of [1280,1024,760]){await page.setViewportSize({width,height:820});await page.getByText('标准答案',{exact:true}).scrollIntoViewIfNeeded();await shot(width+'-exercise-reference');}
 await page.setViewportSize({width:1280,height:820});await page.getByText('维护题库答案',{exact:true}).click();await page.getByRole('button',{name:'保存到题库',exact:true}).click();await page.getByText('标准答案已保存',{exact:true}).waitFor();
 const saved=(await api('/exercises/list','POST',{search_kw:mark})).data.find(item=>item.id===exercise.id);if(!saved?.answer.includes('幂函数求导'))throw Error('generated draft was not saved');
 await page.getByText('核对后，你掌握得怎么样？',{exact:true}).scrollIntoViewIfNeeded();await shot('1280-exercise-analysis-feedback');
 const beforeGrade=(await api('/exercises/list','POST',{search_kw:mark})).data.find(item=>item.id===exercise.id);if(beforeGrade.practice_count!==0)throw Error('viewing answer recorded practice');
 await page.getByRole('button',{name:'已掌握',exact:true}).click();await page.getByText('已记录练习结果',{exact:true}).waitFor();
 const graded=(await api('/exercises/list','POST',{search_kw:mark})).data.find(item=>item.id===exercise.id);if(graded.practice_count!==1)throw Error('self grade did not record one attempt');
 const preserved=(await api('/exercises/practice-sessions/active')).data;if(priorSession&&preserved?.id!==priorSession.id)throw Error('single practice replaced previous continuous session');
 await page.getByRole('button',{name:'返回练习设置',exact:true}).click();
 if(priorSession)await page.getByRole('button',{name:'结束本轮',exact:true}).click();
 const started=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname==='/api/exercises/practice-sessions');
 await page.getByRole('button',{name:'开始练习',exact:true}).click();const session=(await (await started).json()).data;
 if(session.summary.total!==1||session.filters.search_kw!==mark)throw Error('continuous practice ignored visible search scope');
 await page.getByText('连续练习进行中',{exact:true}).waitFor();await shot('1280-exercise-continuous-filtered');
 await page.getByRole('button',{name:'暂停',exact:true}).click();await page.getByRole('button',{name:'继续',exact:true}).waitFor();

 page.off('request',track);
});
if(electronMode)await check('macos-fullscreen-insets',async()=>{
 await page.goto(base+'/goals');await page.getByRole('heading',{name:'目标与任务',exact:true}).waitFor();
 await browser.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(true));
 await page.locator('.desktop-titlebar-marker.is-macos.is-fullscreen').waitFor({state:'attached'});await shot('macos-fullscreen');
 if(await page.locator('.desktop-titlebar-marker.is-macos:not(.is-fullscreen)').count())throw Error('fullscreen retains traffic light inset');
 await browser.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(false));
 await page.locator('.desktop-titlebar-marker.is-macos:not(.is-fullscreen)').waitFor({state:'attached'});await shot('macos-windowed');
});
}finally{await browser.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
