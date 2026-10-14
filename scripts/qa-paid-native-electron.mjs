/** Real Electron interaction: one submission per sourced problem, no paid retries. */
import {createRequire} from 'node:module';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const {_electron}=createRequire(import.meta.url)('playwright');
const out=resolve(process.env.TEXA_PAID_EVIDENCE||'docs/qa/evidence/native-tool-loop/paid-2026-10-13');
mkdirSync(out,{recursive:true});
const questions=JSON.parse(readFileSync(resolve(out,'questions.json'),'utf8'));
const userData='/private/tmp/texa-paid-electron-'+Date.now();mkdirSync(userData,{recursive:true});
writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'real macOS Electron development shell',model:'configured real Qwen3.7 Plus',cases:[],errors:[]};
let app,page;
try{
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18042',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18042'}});
 page=await app.firstWindow();page.setDefaultTimeout(30000);await page.setViewportSize({width:1280,height:820});
 page.on('pageerror',e=>result.errors.push(String(e)));
 await page.locator('.composer-textarea').waitFor();
 for(const [index,item] of questions.entries()){
  if(index){const expand=page.getByRole('button',{name:'展开侧栏',exact:true});if(await expand.isVisible())await expand.click();await page.getByRole('button',{name:'新会话',exact:true}).click();}
  const entry={id:item.id,question:item.question,events:[],screenshots:[]};result.cases.push(entry);
  let recording=true;
  const handler=async response=>{if(recording&&response.url().endsWith('/api/chat/stream')){try{entry.events=(await response.text()).split('\n').filter(x=>x.startsWith('data: ')).map(x=>JSON.parse(x.slice(6)));}catch{entry.stream_read_failed=true;}}};
  page.on('response',handler);
  await page.locator('.composer-textarea').fill(item.question);
  await page.screenshot({path:resolve(out,`${item.id}-start.png`)});entry.screenshots.push(`${item.id}-start.png`);
  await page.getByRole('button',{name:'发送问题',exact:true}).click();
  entry.submitted_at=new Date().toISOString();
  const trace=page.locator('.execution-trace').last();await trace.waitFor();
  await trace.locator('button').first().click();
  await page.screenshot({path:resolve(out,`${item.id}-working.png`)});entry.screenshots.push(`${item.id}-working.png`);
  const start=Date.now();let captured=0;
  let lastText='';
  while(Date.now()-start<620000){
   if(await page.getByRole('button',{name:'发送问题',exact:true}).isVisible())break;
   const body=await page.locator('body').innerText();
   if(!captured&&/正在生成回答|正在计算/.test(body)){
    await page.screenshot({path:resolve(out,`${item.id}-progress.png`)});entry.screenshots.push(`${item.id}-progress.png`);captured=1;
   }
   const answer=page.locator('.learning-answer-document .markdown-body');
   const text=(await answer.allTextContents()).join('');
   if(text.length>100&&text.length-lastText.length>400){lastText=text;await page.screenshot({path:resolve(out,`${item.id}-answer-progress.png`)});if(!entry.screenshots.includes(`${item.id}-answer-progress.png`))entry.screenshots.push(`${item.id}-answer-progress.png`);}
   await new Promise(r=>setTimeout(r,200));
  }
  entry.finished=await page.getByRole('button',{name:'发送问题',exact:true}).isVisible();
  entry.ended_at=new Date().toISOString();entry.wall_seconds=(Date.parse(entry.ended_at)-Date.parse(entry.submitted_at))/1000;
  await page.screenshot({path:resolve(out,`${item.id}-complete.png`),fullPage:true});entry.screenshots.push(`${item.id}-complete.png`);
  entry.body=await page.locator('body').innerText();
  entry.answer=await page.locator('.learning-answer-document .markdown-body').allTextContents();
  if(entry.finished){
   const messages=page.locator('.learning-answer-document');
   if(await messages.count())await messages.last().screenshot({path:resolve(out,`${item.id}-answer.png`)});
  }
  recording=false;page.off('response',handler);
  writeFileSync(resolve(out,'electron-results.json'),JSON.stringify(result,null,2));
  console.log(item.id,entry.finished?'terminal':'not terminal',entry.answer.join('').length,'answer characters');
  if(!entry.finished)break;
 }
}catch(e){result.errors.push(String(e));process.exitCode=1;if(page)await page.screenshot({path:resolve(out,'interaction-error.png')});}
finally{await app?.close();writeFileSync(resolve(out,'electron-results.json'),JSON.stringify(result,null,2));}
