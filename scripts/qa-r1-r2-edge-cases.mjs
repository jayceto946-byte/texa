export async function edgeCases({page,app,shot,assert,reset,state,requests}) {
const importSetup=async()=>{await page.getByRole('radio',{name:'导入',exact:true}).click();await page.locator('.exercise-import-setup').getByRole('button',{name:'选择科目',exact:true}).click();await page.getByRole('button',{name:/高等数学 · 上册（第七版）/}).click();};
for(const [w,h] of [[1280,820],[1024,768]]) {
  state.session=null;state.job=null;state.scenario='normal';
  await app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[w,h]);await reset();
  // Long reading, absent answer and real inline fixture image.
  await page.getByRole('radio',{name:'题库',exact:true}).click();await page.locator('.workspace-register-row>button').nth(2).click();await shot(`${w}-matrix-reading`);await page.getByRole('button',{name:'参考答案',exact:true}).click();await shot(`${w}-missing-answer`);
  await page.getByRole('button',{name:'AI 解题',exact:true}).first().click();state.scenario='job-failed';await page.getByRole('button',{name:'生成解答',exact:true}).click();await page.getByText('回答模型未配置',{exact:true}).waitFor();await shot(`${w}-ai-failed`);
  state.scenario='disconnect';const createCount=state.creates;await page.getByRole('button',{name:'生成解答',exact:true}).click();await page.getByRole('button',{name:'重新读取任务状态',exact:true}).waitFor();await shot(`${w}-ai-disconnected`);assert(state.creates===createCount+1,'disconnect creates exactly one job');
  state.scenario='normal';await page.getByRole('button',{name:'重新读取任务状态',exact:true}).click();await page.getByRole('button',{name:'保存到题库',exact:true}).waitFor();assert(state.creates===createCount+1,'reconnect queries same job');await shot(`${w}-ai-recovered`);
  const solution=page.locator('.question-reading-solution');await solution.evaluate(el=>{el.scrollTop=260;});await page.waitForTimeout(60);const before=await solution.evaluate(el=>el.scrollTop);
  if(w===1024){await page.getByRole('button',{name:'题目与来源',exact:true}).click();await page.getByRole('button',{name:'AI 解题',exact:true}).last().click();assert(Math.abs(await solution.evaluate(el=>el.scrollTop)-before)<3,'narrow switch restores solution scroll');}
  await page.getByRole('button',{name:'返回题库',exact:true}).click();state.job=null;await page.locator('.workspace-register-row>button').nth(3).click();await page.getByText('原图暂不可读取，请对照来源文件。',{exact:true}).waitFor();await shot(`${w}-bank-path-only-image`);await page.getByText('题目管理',{exact:true}).click();await shot(`${w}-bank-management`);await page.getByRole('button',{name:'返回题库',exact:true}).click();
  await page.getByRole('radio',{name:'导入',exact:true}).click();await importSetup();
  state.scenario='analyzing';await page.getByRole('button',{name:'抽取教材候选题'}).click();await shot(`${w}-analyzing`);await page.getByRole('heading',{name:'校对候选题'}).waitFor();
  const selectionBefore=await page.locator('.exercise-candidate-index [aria-current=true]').innerText();await page.getByRole('checkbox',{name:'选择候选题 c-1',exact:true}).uncheck();assert(await page.locator('.exercise-candidate-index [aria-current=true]').innerText()===selectionBefore,'checkbox selection does not navigate current candidate');
  await page.getByRole('button',{name:'返回来源',exact:true}).click();state.scenario='analyze-failed';await page.getByRole('button',{name:'抽取教材候选题'}).click();await page.locator('.exercise-import-setup').getByText('解析失败，请调整范围。',{exact:false}).waitFor();await shot(`${w}-analyze-failed`);
  state.scenario='zero';await page.getByRole('button',{name:'抽取教材候选题'}).click();await page.getByRole('button',{name:'抽取教材候选题'}).waitFor();await page.waitForTimeout(100);await shot(`${w}-zero-candidates`);
  state.scenario='stress';await page.getByRole('button',{name:'抽取教材候选题'}).click();await page.getByRole('heading',{name:'校对候选题'}).waitFor();assert(await page.locator('.exercise-index-item').count()===200,'200-candidate index');await shot(`${w}-200-candidates`);
  const writeCount=requests.filter(r=>r.path==='/api/exercises/batch-add').length;state.scenario='unknown';await page.getByRole('button',{name:'确认入库',exact:true}).click();await page.getByRole('heading',{name:'入库结果待核对'}).waitFor();await shot(`${w}-commit-unknown`);await page.getByRole('button',{name:'核对导入批次'}).click();assert(requests.filter(r=>r.path==='/api/exercises/batch-add').length===writeCount+1,'unknown commit never repeats write');
  // Clear mounted in-memory fixture work through a fresh isolated navigation after explicit unload acceptance.
  await page.getByRole('link',{name:'错题',exact:true}).click();state.scenario='image';await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.once('will-prevent-unload',e=>e.preventDefault()));await page.goto('http://127.0.0.1:18060/mistakes/qa-mistake?book_name=qa-book');await page.getByText('对照原图',{exact:true}).click();await page.getByRole('img',{name:'错题原图',exact:true}).waitFor();await shot(`${w}-image-question`);
  state.scenario='normal';
}
}
