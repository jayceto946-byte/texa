export async function scopeCase({page,app,shot,assert,reset,state,requests}) {
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setContentSize(1280,820));
  await reset();await page.getByRole('radio',{name:'导入',exact:true}).click();
  await page.locator('.exercise-import-setup').getByRole('button',{name:'选择科目',exact:true}).click();await page.getByRole('button',{name:/高等数学 · 上册（第七版）/}).click();
  state.scenario='analyzing';await page.getByRole('button',{name:'抽取教材候选题'}).click();
  await page.getByRole('link',{name:'学习',exact:true}).click();await page.getByRole('button',{name:'选择学习范围',exact:true}).click();await page.getByRole('button',{name:/微积分学习指导/}).click();
  await page.getByRole('link',{name:'练习',exact:true}).click();await page.getByRole('heading',{name:'校对候选题',exact:true}).waitFor();
  const source=await page.locator('.exercise-review-heading').innerText();assert(source.includes('上册')&&!source.includes('微积分学习指导'),'in-flight import retains original scope after global scope change');await shot('1280-scope-retained');
  state.scenario='normal';await page.getByRole('button',{name:'确认入库',exact:true}).click();await page.getByRole('heading',{name:'已加入 5 道题目',exact:true}).waitFor();
  const write=requests.filter(r=>r.path==='/api/exercises/batch-add').at(-1);assert(write.book==='高等数学 · 上册（第七版）','candidate commit remains bound to analyzed scope');
}
