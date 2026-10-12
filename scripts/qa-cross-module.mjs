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
 if(await trace.locator('.execution-step.is-pending').count())throw Error('planned-only steps remain');
 await shot('1280-chat-process');
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
