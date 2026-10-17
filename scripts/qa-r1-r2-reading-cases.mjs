/** Imported by the isolated Electron harness. All writes target in-memory fixtures. */
export async function readingCases({page,app,shot,assert,reset,state,requests}) {
for(const [w,h] of [[1280,820],[1024,768]]) {
  state.session=null;state.job=null;state.scenario='normal';
  await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[w,h]);
  await reset();
  await page.getByRole('radio',{name:'题库',exact:true}).click();
  const sessionsBefore=requests.filter(r=>r.method==='POST'&&r.path==='/api/exercises/practice-sessions').length;
  await page.locator('.workspace-register-row>button').first().click();
  await page.getByRole('heading',{name:'习题详情',exact:true}).waitFor();
  await shot(`${w}-bank-reading`);
  assert(requests.filter(r=>r.method==='POST'&&r.path==='/api/exercises/practice-sessions').length===sessionsBefore,'bank reading creates no practice session');
  await page.getByRole('button',{name:'AI 解题',exact:true}).click();
  await page.getByRole('button',{name:'生成解答',exact:true}).waitFor({state:'visible'});
  state.scenario='generating';await page.getByRole('button',{name:'生成解答',exact:true}).click();
  await page.getByText('正在生成',{exact:true}).waitFor();await shot(`${w}-bank-generating`);
  state.scenario='normal';await page.getByRole('button',{name:'保存到题库',exact:true}).waitFor();
  await shot(`${w}-bank-ai`);
  const countBefore=state.creates;
  if(w===1024){await page.getByRole('button',{name:'题目与来源',exact:true}).click();await page.getByRole('button',{name:'AI 解题',exact:true}).last().click();}
  assert(state.creates===countBefore,'pane switches do not create jobs');
  await page.getByRole('button',{name:'编辑草稿',exact:true}).click();
  await page.getByRole('textbox',{name:'答案草稿'}).fill('## 用户编辑\n\n$1/6$\n\n用户编辑的草稿');
  state.scenario='save-failed';await page.getByRole('button',{name:'保存到题库',exact:true}).click();await page.getByText('保存未确认，当前草稿保留。请核对题库后重试。',{exact:true}).waitFor();
  assert((await page.getByRole('textbox',{name:'答案草稿'}).inputValue()).includes('用户编辑'),'save failure preserves editor');await shot(`${w}-save-failed`);
  state.scenario='normal';await page.getByRole('button',{name:'保存到题库',exact:true}).click();await page.getByText('已保存到题库',{exact:true}).waitFor();
  assert(state.records[0].answer.includes('用户编辑'),'only explicit save updates official answer');await shot(`${w}-saved`);
  await page.getByRole('button',{name:'返回题库',exact:true}).click();
  await page.getByRole('radio',{name:'练习',exact:true}).click();await page.getByRole('button',{name:/开始练习 ·/}).click();
  await page.getByRole('textbox',{name:'你的作答'}).fill('保留三阶项，我的作答不能丢失。');
  await shot(`${w}-practice-reading`);
  await page.getByRole('button',{name:'AI 解题',exact:true}).click();
  await page.getByRole('button',{name:'生成解答',exact:true}).click();await page.getByRole('button',{name:'保存到题库',exact:true}).waitFor();await shot(`${w}-practice-ai`);const practiceSolution=page.locator('.question-reading-solution');await practiceSolution.evaluate(el=>{el.scrollTop=el.scrollHeight;});await shot(`${w}-practice-ai-end`);assert(await page.getByRole('button',{name:'重新生成',exact:true}).isVisible(),'long practice solution reaches end with rating footer');await practiceSolution.evaluate(el=>{el.scrollTop=0;});
  if(w===1024){await page.getByRole('button',{name:'题目与作答',exact:true}).click();assert((await page.getByRole('textbox',{name:'你的作答'}).inputValue()).includes('不能丢失'),'narrow pane retains attempt');}
  await page.getByRole('button',{name:'暂停',exact:true}).click();await page.getByRole('button',{name:'继续',exact:true}).click();
  assert((await page.getByRole('textbox',{name:'你的作答'}).inputValue()).includes('不能丢失'),'pause/resume retains answer');
  await page.getByRole('link',{name:'笔记',exact:true}).click();await page.getByRole('link',{name:'练习',exact:true}).click();
  assert((await page.getByRole('textbox',{name:'你的作答'}).inputValue()).includes('不能丢失'),'exercise→notes→exercise retains attempt');await shot(`${w}-practice-return`);
  await page.getByRole('button',{name:'基本理解',exact:true}).click();await page.getByRole('heading',{name:'第 2 / 6 题',exact:true}).waitFor();assert(state.session.summary.answered===1,'self-rating submits and advances same practice');
  await page.goto('http://127.0.0.1:18060/mistakes/qa-mistake?book_name=qa-book');await page.locator('.question-reading').waitFor();await shot(`${w}-mistake-reading`);
  await page.getByRole('button',{name:'参考答案',exact:true}).click();await shot(`${w}-mistake-reference`);
  await page.getByRole('button',{name:'AI 讲解',exact:true}).first().click();await shot(`${w}-mistake-ai-conflict`);
  assert(await page.getByRole('button',{name:'生成讲解并保存',exact:true}).count()===0,'unsafe legacy mistake write removed per Astra');
  await page.getByRole('button',{name:'编辑档案',exact:true}).click();await page.getByRole('heading',{name:'校正档案',exact:true}).waitFor();await shot(`${w}-mistake-edit`);await page.getByRole('button',{name:'取消编辑',exact:true}).click();
}
}
