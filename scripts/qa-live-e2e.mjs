/** Real API + SQLite browser journey. Requires scripts/qa-live-server.py at18041.
 * Synthetic configuration only. No provider or textbook index/paid service calls.
 */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {chromium}=createRequire(import.meta.url)('playwright');
const out=resolve('docs/qa/evidence/live-e2e');mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const runId=Date.now();
let lastPage;
const results={checks:[],errors:[],requests:[]};
try {
 for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:844}});
  await context.addInitScript(()=>{localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('kaoyan_subject','数学');});
  const page=await context.newPage();lastPage=page;page.on('pageerror',e=>results.errors.push(e.message));
  page.on('request',r=>{if(r.method()!=='GET')results.requests.push({width,method:r.method(),path:new URL(r.url()).pathname});});
  await page.goto('http://127.0.0.1:18041/mistakes/intake');
  await page.getByRole('button',{name:'手动输入',exact:true}).click();await page.getByText('草稿已恢复',{exact:true}).waitFor();
  await page.getByLabel(/^题干与公式/).fill(`QA-${runId}-${width} 求 $x^2$ 的导数。`);
  await page.getByLabel('参考答案（可选）',{exact:true}).fill('$2x$');
  await page.getByLabel('我当时的作答或卡住位置',{exact:true}).fill('$x$');
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await page.getByText('草稿已保存',{exact:true}).waitFor();
  const draftUrl=page.url();await page.reload();await page.waitForLoadState('networkidle');await page.getByText('草稿已恢复',{exact:true}).waitFor();
  if(!(await page.getByLabel(/^题干与公式/).inputValue()).includes(`QA-${runId}-${width}`))throw Error('draft not persisted');
  results.checks.push({width,case:'manual draft save→refresh→restore',status:'PASS',url:draftUrl});
  await page.getByRole('button',{name:'保存并安排复习',exact:true}).click();await page.waitForURL(/\/mistakes\/(?!intake)[^/?]+/);
  const mistakeUrl=page.url();const id=new URL(mistakeUrl).pathname.split('/').at(-1);
  await page.waitForLoadState('networkidle');await page.getByRole('heading',{name:'错题详情',exact:true}).waitFor();await page.screenshot({path:resolve(out,`${width}-saved-mistake.png`)});
  const response=await context.request.get(`http://127.0.0.1:18041/api/mistakes/${id}?book_name=default`);const saved=await response.json();
  if(!saved.success || !saved.data.question_text.includes(`QA-${runId}-${width}`))throw Error('saved API mismatch');
  results.checks.push({width,case:'draft→saved mistake',status:'PASS',id});
  // Start from the actual due-list workflow; fixture mistakes are due immediately.
  await page.goto('http://127.0.0.1:18041/learning/review');await page.getByRole('button',{name:'开始复习',exact:true}).click();await page.waitForURL(/\/learning\/review\/[^/?]+/);
  const reviewUrl=page.url();await page.getByLabel('先写下本次答案，再查看参考与反馈').fill('$2x$');
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.waitForLoadState('networkidle');
  await page.reload();await page.getByLabel('先写下本次答案，再查看参考与反馈').waitFor();
  if(await page.getByLabel('先写下本次答案，再查看参考与反馈').inputValue()!=='$2x$')throw Error('review draft lost');
  results.checks.push({width,case:'review answer save→refresh→restore',status:'PASS',url:reviewUrl});
  // Finish every item; scope may include a previous viewport's due mistake.
  for(let n=0;n<10;n++){
   if(await page.getByRole('heading',{name:'本次复习完成',exact:true}).isVisible())break;
   await page.getByLabel('先写下本次答案，再查看参考与反馈').fill('$2x$');await page.getByRole('button',{name:'提交作答并查看反馈',exact:true}).click();
   await page.getByRole('button',{name:'独立做对',exact:true}).click();await page.waitForLoadState('networkidle');
  }
  await page.getByRole('heading',{name:'本次复习完成',exact:true}).waitFor();await page.screenshot({path:resolve(out,`${width}-review-complete.png`)});
  await page.reload();await page.getByRole('heading',{name:'本次复习完成',exact:true}).waitFor();
  results.checks.push({width,case:'review reveal→self grade→complete→refresh',status:'PASS',url:reviewUrl});
  await page.goto('http://127.0.0.1:18041/exercises');await page.getByRole('button',{name:'手动录入',exact:true}).click();
  const save=page.getByRole('button',{name:'保存到题库',exact:true});if(!await save.isDisabled())throw Error('unchecked input save enabled');
  await page.getByLabel('完整题干',{exact:true}).fill(`QA-${runId}-${width} 求 $x^3$ 的导数。`);await page.getByLabel('参考答案（可选）',{exact:true}).fill('$3x^2$');
  await page.getByLabel('题干与关键条件已经核对完整').check();await save.click();await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.reload();await page.waitForLoadState('networkidle');
  const exercises=await (await context.request.post('http://127.0.0.1:18041/api/exercises/list',{data:{search_kw:`QA-${runId}-${width}`}})).json();
  if(exercises.data.length!==1 || exercises.data[0].question_text!==`QA-${runId}-${width} 求 $x^3$ 的导数。`)throw Error('exercise repeated/lost');
  results.checks.push({width,case:'manual exercise validation→save→refresh',status:'PASS',id:exercises.data[0].id});
  await page.screenshot({path:resolve(out,`${width}-exercise-saved.png`)});
  await context.close();
 }
} catch(e){results.errors.push(String(e));if(lastPage){results.lastUrl=lastPage.url();results.body=await lastPage.locator('body').innerText();await lastPage.screenshot({path:resolve(out,'failure.png')});}process.exitCode=1;}
finally{await browser.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(results,null,2));}
