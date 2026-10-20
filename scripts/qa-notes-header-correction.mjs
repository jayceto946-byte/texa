import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'after';
const base=resolve('docs/qa/notes-header-correction-2026-10-19');
const out=resolve(base,phase,new Date().toISOString().replaceAll(':','-'));mkdirSync(out,{recursive:true});
const ids=JSON.parse(readFileSync(resolve(base,'notes-fixture-ids.json')));
const result={phase,checks:[],measurements:{},screenshots:[],errors:[]};
let app,page;
const record=()=>writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));
const check=(ok,name)=>{result.checks.push({name,pass:!!ok});record();if(!ok)throw Error(name);};
const ready=async()=>{await page.evaluate(()=>document.fonts.ready);await page.waitForFunction(()=>![...document.querySelectorAll('[data-texa-markdown-loading]')].some(x=>x.getBoundingClientRect().height));};
const shot=async name=>{await ready();const p=resolve(out,name+'.png');await page.screenshot({path:p,scale:'css',animations:'disabled'});result.screenshots.push(p);record();};
const size=(w,h)=>app.evaluate(({BrowserWindow},[w,h])=>BrowserWindow.getAllWindows()[0].setContentSize(w,h),[w,h]);
const go=async path=>{await page.goto('http://127.0.0.1:18136'+path);await page.locator('.note-document').waitFor();await ready();};
const api=(path,body)=>page.evaluate(async({path,body})=>{const r=await fetch('/api/notes'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const v=await r.json();if(!r.ok||!v.success)throw Error(v.code||r.status);return v.data;},{path,body});
async function geometry(name) {
  const m=await page.locator('.note-page-header').evaluate(el=>{
    const rect=x=>x?.getBoundingClientRect().toJSON();
    const header=rect(el),title=rect(el.querySelector('h1')),state=rect(el.querySelector('.note-header-state,.note-save-status'));
    const trigger=document.querySelector('.context-sidebar-trigger');
    const controls=[...el.querySelectorAll('.note-actions>a,.note-actions>button')].map(x=>({label:x.textContent,rect:rect(x)}));
    return{header,title,state,trigger:trigger&&rect(trigger),controls,utilities:[...document.querySelectorAll('.note-document>details>summary')].map(x=>({label:x.textContent,rect:rect(x)})),overflow:document.body.scrollWidth>innerWidth};
  });
  result.measurements[name]=m;record();
  if(phase==='after') {
    const center=r=>r.y+r.height/2;
    check(!m.overflow,name+': no horizontal overflow');
    check(m.header.height<=56.5,name+': one command row');
    check(m.controls.every(x=>Math.abs(center(x.rect)-center(m.header))<=1),name+': commands share header centerline');
    check(Math.abs(center(m.title)-center(m.header))<=1,name+': title shares command centerline');
    if(m.trigger)check(Math.abs(center(m.trigger)-center(m.header))<=1,name+': sidebar trigger shares command centerline');
    if(m.state)check(m.state.x-(m.title.x+m.title.width)<=16,name+': state stays with page identity');
  }
}
try {
 const data=resolve('/private/tmp/texa-notes-header-electron-'+Date.now());mkdirSync(data,{recursive:true});writeFileSync(resolve(data,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
 app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:data,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18136',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18136'}});
 page=await app.firstWindow();page.setDefaultTimeout(20000);page.on('pageerror',e=>{result.errors.push(String(e));record();});await page.locator('.app-shell').waitFor();
 for(const[w,h]of [[760,820],[1024,768],[1280,820]]) {
  await size(w,h);
  for(const[scene,path]of [['history','/notes/'+ids.note_id+'?revision=1'],['current','/notes/'+ids.note_id],['draft','/notes/drafts/'+ids.draft_id]]) {
   await go(path);if(scene==='draft')await page.locator('math-field').last().waitFor();
   await geometry(`${w}-${scene}`);await shot(`${w}-${scene}`);
  }
 }
 if(phase==='after') {
  await size(760,820);await go('/notes/'+ids.note_id+'?revision=1');
  check(await page.locator('.note-meta-details').count()===1,'one compact document utility disclosure');
  const summary=page.locator('.note-meta-details>summary');await summary.focus();await summary.press('Space');
  check(await page.getByRole('navigation',{name:'笔记目录'}).isVisible(),'keyboard opens grouped contents and note information');await shot('760-information-open');
  await page.getByRole('link',{name:'三、线性变换中的表示与不变量',exact:true}).click();
  const visible=await page.locator('#review-h3').evaluate(el=>{const r=el.getBoundingClientRect();const s=document.querySelector('.note-scroll').getBoundingClientRect();return r.top>=s.top-1&&r.top<s.bottom;});
  check(visible,'contents link reaches its actual heading');await shot('760-contents-target');
  await go('/notes/'+ids.note_id+'?revision=1');await page.getByRole('button',{name:'展开侧栏',exact:true}).click();await shot('760-navigation-open');
  await page.getByRole('button',{name:'收起侧栏',exact:true}).click();await geometry('760-navigation-closed');await shot('760-navigation-closed');
  await go('/notes/'+ids.note_id);await page.getByRole('button',{name:'归档',exact:true}).click();await page.getByRole('button',{name:'恢复',exact:true}).waitFor();
  await geometry('760-archived');await shot('760-archived');check(await page.locator('.note-header-state').isVisible(),'archive state stays visible');
  await page.getByRole('button',{name:'恢复',exact:true}).click();await page.getByRole('button',{name:'归档',exact:true}).waitFor();
  const n=await api('/'+ids.note_id);const a=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:n.revision});const b=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:n.revision});
  await go('/notes/drafts/'+a.id);await api('/drafts/'+b.id+'/save',{operation_id:'header-conflict-'+Date.now(),expected_draft_revision:b.draft_revision,base_note_revision:n.revision});
  await page.getByRole('button',{name:'保存修改',exact:true}).click();await page.getByText('正式笔记版本已变化',{exact:true}).waitFor();await geometry('760-conflict');await shot('760-conflict');
  check(await page.getByRole('button',{name:'保存修改',exact:true}).isDisabled(),'conflict still prevents publication');
  await page.emulateMedia({reducedMotion:'reduce'});await go('/notes/'+ids.note_id+'?revision=1');await shot('760-reduced-motion');
  for (const [w,h] of [[760,820],[1280,820]]) {
    await size(w,h);
    await page.goto('http://127.0.0.1:18136/notes');await page.locator('.note-list-controls').waitFor();await shot(`${w}-notes-list`);check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),`${w}: adjacent notes library has no overflow`);
    await page.goto('http://127.0.0.1:18136/');await page.locator('.composer-textarea').waitFor();await shot(`${w}-learning`);check(await page.getByRole('button',{name:'发送问题',exact:true}).isVisible(),`${w}: adjacent learning composer available`);
  }
 }
 check(!result.errors.length,'no renderer exceptions');
} catch(e) {result.errors.push(String(e));process.exitCode=1;await shot('failure').catch(()=>{});}
finally {record();writeFileSync(resolve(base,phase+'-latest.json'),JSON.stringify({path:out},null,2));await app?.evaluate(({app})=>app.exit(0)).catch(()=>{});await app?.close().catch(()=>{});console.log(JSON.stringify({out,checks:result.checks,errors:result.errors,screenshots:result.screenshots.length},null,2));}
