/** Additional offline UI surfaces for the anti-slop audit; imported by qa-pages. */
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
export async function auditPanels({ browser, capture, results, dist }) {
 for (const width of [1280,390]) {
  const context=await browser.newContext({viewport:{width,height:820},reducedMotion:'reduce'});
  await context.addInitScript(()=>{if(!sessionStorage.getItem('slop-onboarding'))localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学/高数');});
  const page=await context.newPage();
  page.on('pageerror',e=>results.errors.push({width,error:e.message}));
  await page.route('**/api/books/*/chapter-highlights',route=>route.fulfill({json:{success:true,data:{chapters:[]}}}));
  await page.route('**/api/mistakes/chat-sources/query?*',route=>route.fulfill({json:{success:true,data:[]}}));
  const shot=async name=>{await page.waitForTimeout(250);await page.evaluate(()=>document.fonts.ready);results.checks.push({name,width,state:'panel',...await capture(page,`${width}-panel-${name}`)});};
  const go=async path=>{await page.goto(`http://127.0.0.1:18040${path}`);await page.waitForLoadState('networkidle');};
  await go('/exercises');await page.getByRole('radio',{name:'导入',exact:true}).click();await shot('exercise-import');
  await page.getByRole('button',{name:'手动录入',exact:true}).click();await shot('manual-exercise');await page.getByRole('button',{name:'取消',exact:true}).click();
  await go('/');await shot('empty-chat');
  await page.getByRole('button',{name:'打开数学符号面板',exact:true}).click();await shot('math-templates');
  await page.getByRole('button',{name:'矩阵输入',exact:true}).click();await page.locator('.math-input-panel .katex').first().waitFor();await shot('math-matrix');await page.getByRole('button',{name:'关闭数学符号面板',exact:true}).click();
  await page.getByRole('button',{name:'更多',exact:true}).click();await shot('composer-menu');await page.keyboard.press('Escape');
  await go('/goals');await page.getByRole('button',{name:'新目标',exact:true}).click();await shot('new-goal');
  await go('/books');await page.getByText('详细信息',{exact:true}).first().click();await shot('book-details');
  await go('/settings');
  for (const label of ['偏好','模型连接','数据与教材','关于与更新','高级与诊断']) {
   if (width===390) await page.getByRole('button',{name:'返回设置',exact:true}).click();
   await page.getByRole('button',{name:label,exact:true}).click();await page.waitForTimeout(150);await shot(`settings-${label}`);
  }
  await page.getByRole('button',{name:'关闭设置',exact:true}).click();
  await go('/?conversation_id=visual-session-0');await shot('session-loaded');
  if (process.env.TEXA_QA_EXTENDED) {
   await page.getByRole('button',{name:'选择学习范围',exact:true}).first().click();await shot('scope-selector');await page.keyboard.press('Escape');
   await page.getByRole('button',{name:'查看来源 · 3',exact:true}).click();await shot('source-inspector');await page.getByRole('button',{name:'关闭详情面板',exact:true}).click();
   await page.route('**/api/books/*/figures?*',route=>route.fulfill({json:{success:true,data:{items:[],total:0}}}));
   await page.getByRole('button',{name:'选择教材图片',exact:true}).click();await shot('figure-catalog-empty');await page.getByRole('button',{name:'关闭详情面板',exact:true}).click();
   await page.getByRole('button',{name:'选择历史错题',exact:true}).click();await shot('mistake-picker');await page.keyboard.press('Escape');
   await page.locator('input[type=file][accept*="image/png"]:not([capture])').first().setInputFiles({name:'synthetic-question.png',mimeType:'image/png',buffer:readFileSync(resolve('docs/qa/anti-ai-slop/before/1280-chat.png'))});
   await page.getByRole('heading',{name:'裁剪并增强题目图片',exact:true}).waitFor();await shot('image-editor');await page.getByRole('button',{name:'取消',exact:true}).click();
   await go('/books');await page.getByRole('button',{name:'更多教材操作',exact:true}).first().click();await shot('book-menu');
   await page.route('**/api/books/*/figure-audit?*',route=>route.fulfill({json:{success:true,data:{canonical_hash:'fixture',status:'complete',total_findings:0,summary:{figure_blocks:1,assets_checked:1,errors:0,suspects:0,unverifiable:0},findings:[]}}}));
   await page.getByRole('menuitem',{name:'审核图片',exact:true}).click();await page.getByRole('heading',{name:'教材图片审核',exact:true}).scrollIntoViewIfNeeded();await shot('figure-audit');await page.getByRole('button',{name:'关闭图片审核',exact:true}).click();
   await go('/?conversation_id=visual-session-0');
  }
  await page.locator('.current-session-menu button:visible, .context-session-entry:has(.context-session-row.is-active) > button[aria-haspopup=menu]:visible').first().click();await shot('session-menu');
  await page.route('**/api/notes/preflight',route=>route.fulfill({json:{success:true,data:{turn_count:1,message_count:2,batches:1,captured_at:'2026-10-15T02:00:00Z',selection:{conversation_id:'visual-session-0'},fingerprint:'synthetic',existing_drafts:{items:[]},existing_notes:{items:[]}}}}));
  await page.route('**/api/notes/turns?*',route=>route.fulfill({json:{success:true,data:{items:[{turn_id:'t1',label:'等价替换与泰勒展开'}],next_cursor:null}}}));
  await page.getByRole('menuitem',{name:'整理为笔记',exact:true}).click();await page.getByText('共 1 轮',{exact:false}).waitFor();await shot('note-preflight');await page.getByRole('button',{name:'取消',exact:true}).click();
  await page.getByRole('button',{name:'更多',exact:true}).click();await page.getByRole('menuitem',{name:'查看/生成重点',exact:true}).click();await shot('highlight-dialog');await page.getByRole('button',{name:'关闭',exact:true}).last().click();
  for(const kind of ['routing','input','confirmation','confirmation-add','confirmation-practice','confirmation-result','confirmation-update','confirmation-unknown','interrupted']) {
   await go('/');
   await page.route('**/api/chat/stream',async route=>{
    const request=route.request().postDataJSON();
    const confirming=kind.startsWith('confirmation');
    const actions={
     'confirmation':{type:'mark_concept_reviewed',payload:{name:'泰勒公式',quality:4,book_name:'高等数学 · 上册'}},
     'confirmation-add':{type:'add_mistake',payload:{question_text:'已知函数在原点附近连续，求极限并说明适用条件。'.repeat(5),user_answer:'',correct_answer:'1/6',subject:'数学/高数',tags:'极限',mistake_type:['忽略高阶项']}},
     'confirmation-practice':{type:'create_practice_session',payload:{book_name:'高等数学 · 上册',exercise_ids:['exercise-1','exercise-2'],shuffle:false,limit:5}},
     'confirmation-result':{type:'record_practice_result',payload:{book_name:'高等数学 · 上册',session_id:'practice-1',exercise_id:'exercise-1',user_answer:'',quality:0,note:'独立作答尚未完成'}},
     'confirmation-update':{type:'update_mistake',payload:{book_name:'高等数学 · 上册',mistake_id:'mistake-1',expected_revision:2,notes:''}},
     'confirmation-unknown':{type:'future_action',payload:{target:'保留完整载荷',future_field:{value:1}}},
    };
    const task={schema_version:'learning-task/v1',id:'synthetic-task',task_type:kind==='input'?'visual_qa':'qa',goal:request.question,status:kind==='input'?'waiting_for_input':confirming?'waiting_for_confirmation':kind==='interrupted'?'interrupted':'completed',required_inputs:kind==='input'?[{type:'image',name:'附表',blocking:true,status:'missing',reason:'缺少计算所需数据'}]:[],required_outputs:[],terminal:kind==='routing',interruptible:false,resumable:kind==='interrupted',input_action_required:kind==='input',confirmation_required:confirming,artifacts:{resume_stage:'检索完成',pending_actions:confirming?[{action_id:'synthetic-action',...actions[kind],status:'pending',allowed_actions:['confirm','reject']}]:[]}};
    const base={schema:'texa.execution/v1',request_id:'synthetic-request',task_id:task.id,run_id:'synthetic-run',conversation_id:request.conversation_id,turn_id:request.turn_id,operation_id:'answer',phase:'generation',summary:'界面状态样例',label:'解答',kind:'system',elapsed_ms:1};
    const suggestion={target_subject:'数学/线代',target_book_name:'线性代数（第六版）',current_subject:'数学/高数',current_book_name:'',confidence:0.88,reason:'问题涉及矩阵的秩。'};
    const envelopes=[{execution_event:{...base,seq:1,type:'output_delta',status:'running',payload:{text:kind==='routing'?'矩阵的秩是线性无关行或列的最大个数。':'当前任务及已取得的内容已保留。',replace:true}}},{execution_event:{...base,seq:2,type:'final',status:'completed',payload:{task_status:task.status}},learning_task:task,...(kind==='routing'?{subject_suggestion:suggestion}:{})}];
    await route.fulfill({contentType:'text/event-stream',body:envelopes.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')});
   });
   await page.locator('.composer-textarea').fill('矩阵的秩如何理解？');await page.getByRole('button',{name:'发送问题',exact:true}).click();
   await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();await page.getByText('矩阵的秩如何理解？',{exact:true}).waitFor();await shot(`task-${kind}`);await page.unroute('**/api/chat/stream');
  }
  await page.evaluate(()=>{sessionStorage.setItem('slop-onboarding','1');localStorage.removeItem('texa:setup-complete:v3');localStorage.removeItem('kaoyan:onboarding-complete:v2');});await go('/');await shot('onboarding-welcome');
  await page.getByRole('button',{name:'开始设置',exact:true}).click();await shot('onboarding-models');
  await page.getByRole('button',{name:'保存并继续',exact:true}).click();await page.getByRole('heading',{name:'学习工作区已就绪',exact:true}).waitFor();await shot('onboarding-ready');
  await page.getByRole('button',{name:'进入学习工作区',exact:true}).click();await page.locator('.composer-textarea').waitFor();results.interactions.push(`${width}: import→manual→cancel; formula→matrix→close; menu→Escape; new goal; book details; all settings; onboarding→save→workspace`);
  // Startup shell is static plus a synthetic preload. Repair functions are never called.
  await page.route('**/loading.html',async route=>route.fulfill({path:resolve(dist.includes('before-dist')?'/tmp/texa-slop-before-loading.html':'desktop/loading.html'),contentType:'text/html'}));
  await page.route('**/assets/texa-lockup.svg',async route=>route.fulfill({path:resolve('desktop/assets/texa-lockup.svg'),contentType:'image/svg+xml'}));
  await go('/loading.html');await shot('desktop-startup');
  await page.evaluate(()=>showStartupError({failure:{code:'MODEL_MISSING',recoverable:true,repair_action:'repair_embedding_runtime',diagnostic_id:'synthetic-test'}}));await shot('desktop-startup-error');
  await context.close();
 }
}
