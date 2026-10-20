/** Real Electron + isolated production notes service. Never uses production learning data. */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'before';
const base = resolve('docs/qa/notes-audit-fixes-2026-10-19');
const out = resolve(base, phase, new Date().toISOString().replaceAll(':', '-'));
mkdirSync(out, { recursive: true });
const ids = JSON.parse(readFileSync(resolve(base, 'notes-fixture-ids.json')));
const result = { phase, checks: [], measurements: {}, screenshots: [], errors: [] };
let app, page;
const record = () => writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2));
const check = (ok, name) => { result.checks.push({ name, pass: !!ok }); record(); if (!ok) throw Error(name); };
const ready = async () => { await page.evaluate(() => document.fonts.ready); await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(el => !el.getBoundingClientRect().height)); };
const shot = async name => { await ready(); if (phase !== 'before' && await page.locator('.note-page-header').count()) await verifyHeader(name); const path = resolve(out, name + '.png'); await page.screenshot({ path, scale: 'css', animations: 'disabled' }); result.screenshots.push(path); record(); };
const size = (w, h) => app.evaluate(({ BrowserWindow }, [width, height]) => BrowserWindow.getAllWindows()[0].setContentSize(width, height), [w, h]);
const api = (path, body, method) => page.evaluate(async ({ path, body, method }) => {
  const response = await fetch('/api/notes' + path, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const value = await response.json(); if (!response.ok || !value.success) throw Error(value.code || response.status); return value.data;
}, { path, body, method });
const go = async path => { await page.goto('http://127.0.0.1:18136' + path); await page.locator('.app-shell').waitFor(); await page.locator('.note-document').waitFor(); await ready(); };
const saved = async () => { await page.getByText('草稿已保存', { exact: true }).waitFor(); };
async function verifyHeader(name) {
  const geometry = await page.locator('.note-page-header').evaluate(header => {
    const outer=header.getBoundingClientRect();
    const items=[header.querySelector('h1'), header.querySelector('.note-save-status,.note-header-state'), ...header.querySelectorAll('.note-actions>button,.note-actions>a')].filter(Boolean).map(el=>({text:el.textContent,rect:el.getBoundingClientRect().toJSON(),scroll:el.scrollWidth,client:el.clientWidth}));
    const inside=items.every(({rect:r})=>r.width>0 && r.height>0 && r.left>=outer.left && r.right<=outer.right+.5 && r.top>=outer.top && r.bottom<=outer.bottom+.5);
    const overlap=items.some((a,i)=>items.slice(i+1).some(b=>Math.min(a.rect.right,b.rect.right)-Math.max(a.rect.left,b.rect.left)>1 && Math.min(a.rect.bottom,b.rect.bottom)-Math.max(a.rect.top,b.rect.top)>1));
    return {outer:outer.toJSON(),items,inside,overlap};
  });
  result.measurements[name+'-header']=geometry;
  check(geometry.inside && !geometry.overlap, name+': header states and controls visible without overlap');
}

async function measureReading(w) {
  result.measurements[`${w}-reading`] = await page.locator('.note-reading').evaluate(el => {
    const metrics = x => { const c = getComputedStyle(x); return { fontSize: c.fontSize, lineHeight: c.lineHeight, width: x.getBoundingClientRect().width }; };
    return { paragraph: metrics(el.querySelector('p')), list: metrics(el.querySelector('li')), formula: metrics(el.querySelector('.katex')), root: metrics(el.querySelector('.markdown-body')), header: [...document.querySelector('.note-page-header').querySelectorAll('*')].map(x=>{const c=getComputedStyle(x);return {tag:x.tagName,cls:x.className,text:x.textContent.slice(0,30),rect:x.getBoundingClientRect().toJSON(),display:c.display,gridArea:c.gridArea,width:c.width,flex:c.flex};}), headerStyle: (()=>{const c=getComputedStyle(document.querySelector('.note-page-header'));return {display:c.display,gridTemplateAreas:c.gridTemplateAreas,gridTemplateColumns:c.gridTemplateColumns};})(), headerHeight: document.querySelector('.note-page-header').getBoundingClientRect().height, statusVisible: !!document.querySelector('.note-header-state')?.getBoundingClientRect().height };
  });
}
try {
  const userData = resolve('/private/tmp/texa-notes-audit-electron-' + Date.now()); mkdirSync(userData, { recursive: true });
  writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18136', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18136' } });
  page = await app.firstWindow(); page.setDefaultTimeout(20000); page.on('pageerror', e => { result.errors.push(String(e)); record(); });
  await size(1280, 820); await page.locator('.app-shell').waitFor();
  check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
  if (phase === 'adjacent') {
    for (const [w,h] of [[1280,820],[760,820]]) {
      await size(w,h); await page.goto('http://127.0.0.1:18136/'); await page.locator('.composer-textarea').waitFor(); await ready(); await shot(`${w}-learning`);
      check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),`${w}: adjacent learning page has no horizontal overflow`);
      check(await page.getByRole('button',{name:'发送问题',exact:true}).isVisible(),`${w}: adjacent composer remains available`);
      await page.goto('http://127.0.0.1:18136/notes'); await page.locator('.note-list-controls').waitFor(); await ready(); await shot(`${w}-notes-list`);
      check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),`${w}: notes library has no horizontal overflow`);
    }
  } else {
  if (phase !== 'before') {
    const seeded = JSON.parse(execFileSync(resolve('venv310/bin/python'), [resolve('scripts/qa-notes-audit-seed.py'), base], { encoding: 'utf8' }));
    ids.note_id = seeded.note_id; result.measurements.isolatedNoteId = seeded.note_id;
  }
  const fresh = await api('/drafts', { kind: 'edit', note_id: ids.note_id, base_revision: 1 });
  const editorPath = '/notes/drafts/' + fresh.id;
  result.measurements.draftId = fresh.id;
  await go(editorPath); await page.locator('math-field').last().waitFor(); await shot('1280-edit-top');
  const field = page.getByRole('textbox', { name: '第 4 块正文', exact: true });
  await field.fill((await field.inputValue()) + '\n\n尚未正式发布的新内容：误删恢复验证。'); await saved();
  const beforeDelete = await api('/drafts/' + fresh.id);
  const originalBlock = beforeDelete.content.blocks[3];
  await shot('new-content-saved-draft');
  await page.getByRole('button', { name: '删除第 4 块', exact: true }).click(); await saved();
  const deleted = await api('/drafts/' + fresh.id);
  check(!deleted.content.blocks.some(b => b.block_id === originalBlock.block_id), 'deleted block absent after real autosave');
  check((await api('/' + ids.note_id)).revision === 1, 'delete autosave does not publish');
  if (phase !== 'before') check(await page.getByRole('button',{name:'撤销删除',exact:true}).evaluate(el=>el===document.activeElement),'deleted control hands focus to visible undo');
  await shot('deleted-after-autosave');
  if (phase === 'before') {
    check(!await page.getByRole('button', { name: /撤销删除/ }).count(), 'baseline confirms no delete recovery action');
  } else {
    await page.getByRole('button', { name: '阅读预览', exact: true }).click();
    await page.getByRole('button', { name: '撤销删除', exact: true }).click(); await saved();
    const restored = await api('/drafts/' + fresh.id);
    result.measurements.undoOriginal = originalBlock; result.measurements.undoRestored = restored.content.blocks[3];
    const stable = b => Object.fromEntries(['block_id','type','role','group_id','data','source_ref_ids','evidence_ref_ids'].map(k=>[k,b[k]]));
    check(JSON.stringify(stable(restored.content.blocks[3])) === JSON.stringify(stable(originalBlock)), 'undo after autosave restores content, ID, associations and position across preview');
    check(restored.content.blocks[3].verification.status !== 'verified', 'restored block retains server-owned unverified semantics');
    check((await api('/' + ids.note_id)).revision === 1, 'undo autosave does not publish');
    check(await page.locator('#'+originalBlock.block_id).evaluate(el=>el===document.activeElement),'undo returns focus to the restored block');
    await shot('undo-restored');
  }
  for (const [w, h] of [[1280,820], [1024,768], [760,820]]) {
    await size(w, h); await go('/notes/' + ids.note_id); await measureReading(w); await shot(`${w}-reading`);
    if (phase !== 'before') {
      const m = result.measurements[`${w}-reading`];
      check(m.paragraph.fontSize === '16px' && m.paragraph.lineHeight === '30.4px' && m.list.fontSize === '16px', `${w}: effective paragraph/list reading styles`);
      check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${w}: no document horizontal overflow`);
    }
    await go('/notes/' + ids.note_id + '?revision=1'); await shot(`${w}-history`);
    result.measurements[`${w}-historyState`] = await page.locator('.note-header-state').evaluate(el => ({ text: el.textContent, visible: !!el.getBoundingClientRect().height, display: getComputedStyle(el).display }));
    if (phase !== 'before') check(await page.getByText('历史版本 1 · 只读', { exact: false }).isVisible(), `${w}: visible history readonly state`);
  }
  if (phase !== 'before') {
    // Extended interaction assertions are defined below as the implementation lands.
    await verifyAfter({ app, page, api, go, saved, size, shot, check, result, ids, fresh, editorPath });
  }
  }
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); process.exitCode = 1; if (page) { await shot('failure').catch(() => {}); writeFileSync(resolve(out, 'failure.txt'), await page.locator('body').innerText().catch(() => '')); } }
finally { record(); writeFileSync(resolve(base, phase + '-latest.json'), JSON.stringify({ path: out }, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); console.log(JSON.stringify({ out, checks: result.checks, errors: result.errors, screenshots: result.screenshots.length }, null, 2)); }
async function verifyAfter({ app, page, api, go, saved, size, shot, check, result, ids, fresh, editorPath }) {
  const settle = async () => { await page.evaluate(() => document.fonts.ready); await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); };
  const visibleBlock = id => page.locator('[data-note-block="' + id + '"]').evaluate(el => { const s = document.querySelector('.note-scroll').getBoundingClientRect(); const r = el.getBoundingClientRect(); return { visible: r.bottom > s.top && r.top < s.bottom, y: r.top-s.top, height:r.height, top:document.querySelector('.note-scroll').scrollTop }; });
  for (const [w,h] of [[1280,820],[1024,768],[760,820]]) {
    await size(w,h); await go(editorPath); await page.locator('math-field').last().waitFor(); await settle(); await shot(`${w}-edit-top`);
    const p = page.getByRole('textbox', { name: '第 4 块正文', exact: true });
    await p.focus(); await settle(); await shot(`${w}-edit-focused`);
    result.measurements[`${w}-edit`] = await p.evaluate(el => { const c = getComputedStyle(el); const block = el.closest('.note-edit-block'); return { fontSize:c.fontSize,lineHeight:c.lineHeight,clientHeight:el.clientHeight,scrollHeight:el.scrollHeight, headingHeight:document.querySelector('.note-edit-heading textarea').getBoundingClientRect().height, blockHeight:document.querySelector('.note-edit-heading').getBoundingClientRect().height, outline:c.outline, boxShadow:c.boxShadow, border:c.border, currentBorder:getComputedStyle(block).borderColor, inactiveBorder:getComputedStyle(document.querySelector('.note-edit-block')).borderColor, headerHeight:document.querySelector('.note-page-header').getBoundingClientRect().height }; });
    check(result.measurements[`${w}-edit`].clientHeight >= result.measurements[`${w}-edit`].scrollHeight-1, `${w}: representative paragraph grows without nested scrolling`);
    check(result.measurements[`${w}-edit`].headingHeight < 60, `${w}: short heading field avoids fixed 85px height`);
    check(!await page.locator('article>.note-document-title').count(), `${w}: one editable document title`);
    await page.getByRole('button', { name:'阅读预览',exact:true }).click(); await page.locator('#review-p2 .markdown-body').waitFor(); await settle();
    const readingPosition = await visibleBlock('review-p2');
    result.measurements[`${w}-editToRead`] = readingPosition;
    check(readingPosition.visible, `${w}: same edited block visible in preview`);
    check(await page.getByRole('button', {name:'编辑笔记',exact:true}).evaluate(el => el===document.activeElement), `${w}: mode toggle retains keyboard focus`);
    await shot(`${w}-preview-same-block`);
    // Scroll to a different equation in reading mode, then activate the toggle by keyboard.
    await page.locator('#review-e4').evaluate(el => { const s=document.querySelector('.note-scroll');s.scrollTop+=el.getBoundingClientRect().top-s.getBoundingClientRect().top-16; });
    const toggle=page.getByRole('button',{name:'编辑笔记',exact:true}); await toggle.focus(); await toggle.press('Enter');
    await page.locator('#review-e4 math-field').waitFor(); await settle();
    const editPosition = await visibleBlock('review-e4'); result.measurements[`${w}-readToEdit`] = editPosition;
    check(editPosition.visible, `${w}: reading equation stays visible after keyboard edit toggle`);
    check(await page.getByRole('button',{name:'阅读预览',exact:true}).evaluate(el=>el===document.activeElement), `${w}: edit toggle does not steal focus into MathLive`);
    await shot(`${w}-equation-after-toggle`);
    const math = page.getByLabel('第 13 块公式',{exact:true}); await math.focus(); await shot(`${w}-equation-focus`);
    check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),`${w}: editing document has no horizontal overflow`);
  }
  await size(1280,820); await go(editorPath); await page.locator('math-field').last().waitFor();
  const p=page.getByRole('textbox',{name:'第 4 块正文',exact:true}); await p.focus();
  await page.keyboard.press('Shift+Tab'); check(await page.getByRole('button',{name:'删除第 4 块',exact:true}).evaluate(el=>el===document.activeElement),'Shift+Tab reaches delete from prose field');
  await page.keyboard.press('Shift+Tab'); check(await page.getByRole('button',{name:'下移第 4 块',exact:true}).evaluate(el=>el===document.activeElement),'Shift+Tab reaches move-down');
  await page.keyboard.press('Shift+Tab'); check(await page.getByRole('button',{name:'上移第 4 块',exact:true}).evaluate(el=>el===document.activeElement),'Shift+Tab reaches move-up');
  await shot('keyboard-tool-focus');
  for (let i=0;i<3;i++) await page.keyboard.press('Tab');
  check(await p.evaluate(el=>el===document.activeElement),'Tab returns through controls to prose');
  const formula=page.getByLabel('第 13 块公式',{exact:true}); await formula.scrollIntoViewIfNeeded(); await formula.click();
  const formulaPersisted=page.waitForResponse(r=>r.url().endsWith('/api/notes/drafts/'+fresh.id) && r.request().method()==='PATCH' && r.ok());
  const latexBefore=await formula.evaluate(el=>el.value); await formula.press('End'); await page.keyboard.type('+1'); await formulaPersisted; await saved();
  const formulaDraft=await api('/drafts/'+fresh.id); const latexAfter=formulaDraft.content.blocks.find(b=>b.block_id==='review-e4').data.latex;
  check(latexAfter!==latexBefore,'MathLive keyboard edit persists through existing autosave'); await shot('formula-keyboard-edit');
  await page.getByRole('button',{name:'阅读预览',exact:true}).click(); await page.locator('#review-e4 .katex').first().waitFor(); await settle();
  check((await visibleBlock('review-e4')).visible,'edited formula remains visible in rendered preview'); await shot('formula-keyboard-preview');
  await page.getByRole('button',{name:'编辑笔记',exact:true}).click(); await page.locator('#review-e4 math-field').waitFor(); await settle();
  check((await formula.evaluate(el=>el.value))===latexAfter,'formula content survives edit/preview roundtrip');
  // Extremely long content is bounded, while the representative paragraph grows fully.
  const original=await p.inputValue(); await p.fill(original+'\n\n'+('极长段落用于检查控件高度上限，不进入正式笔记。'.repeat(180))); await saved();
  result.measurements.extreme=await p.evaluate(el=>({height:el.getBoundingClientRect().height,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,viewport:innerHeight}));
  check(result.measurements.extreme.height<=result.measurements.extreme.viewport*.6+1 && result.measurements.extreme.scrollHeight>result.measurements.extreme.clientHeight,'extreme prose capped with accessible internal scrolling'); await shot('extreme-prose-bounded');
  await p.fill(original); await saved();
  // Real autosave failure: abort transport, leave editor text, then retry through existing writer.
  await page.route('**/api/notes/drafts/'+fresh.id,async route=>{if(route.request().method()==='PATCH')await route.abort('failed');else await route.continue();});
  await p.fill(original+'\n\n网络失败时保留的文字。'); await page.getByText('草稿保存失败',{exact:true}).waitFor(); await shot('autosave-error');
  check((await p.inputValue()).includes('网络失败时保留的文字'),'autosave failure retains editable text');
  await page.unroute('**/api/notes/drafts/'+fresh.id); await page.getByRole('button',{name:'重试保存草稿',exact:true}).click(); await saved();
  // Explicit save flushes the last edit before publishing, even within the debounce interval.
  await p.fill(original+'\n\n保存前立即输入的文字。'); await page.getByRole('button',{name:'保存修改',exact:true}).click(); await page.waitForURL('**/notes/'+ids.note_id);
  const formal=await api('/'+ids.note_id);
  check(formal.revision===2 && formal.blocks[3].data.markdown.endsWith('保存前立即输入的文字。'),'explicit save flushes latest input then publishes exactly one revision'); await shot('explicit-save-v2');
  const a=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:2}); const b=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:2});
  await go('/notes/drafts/'+a.id); await page.getByRole('textbox',{name:'第 4 块正文',exact:true}).fill('冲突时不能丢失的修改'); await saved();
  await api('/drafts/'+b.id+'/save',{operation_id:'audit-parallel-save-'+ids.note_id,expected_draft_revision:b.draft_revision,base_note_revision:2});
  await size(760,820); await page.getByRole('button',{name:'保存修改',exact:true}).click(); await page.getByText('正式笔记版本已变化',{exact:true}).waitFor(); await page.getByText('正式笔记版本已变化',{exact:true}).scrollIntoViewIfNeeded(); await shot('760-version-conflict');
  check(await page.getByRole('button',{name:'保存修改',exact:true}).isDisabled(),'formal conflict disables publish');
  check((await api('/drafts/'+a.id)).content.blocks[3].data.markdown==='冲突时不能丢失的修改' && (await api('/'+ids.note_id)).revision===3,'formal conflict preserves draft and current authority');
  const closeDraft=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:3});
  await go('/notes/drafts/'+closeDraft.id);
  await page.route('**/api/notes/drafts/'+closeDraft.id,async route=>{if(route.request().method()==='PATCH')await route.abort('failed');else await route.continue();});
  const closeField=page.getByRole('textbox',{name:'第 4 块正文',exact:true});
  await closeField.fill('退出失败时仍需保留并可编辑的文字');
  await page.getByRole('link',{name:'返回笔记',exact:true}).click(); await page.getByText('草稿保存失败',{exact:true}).waitFor();
  check(page.url().endsWith('/notes/drafts/'+closeDraft.id) && await closeField.inputValue()==='退出失败时仍需保留并可编辑的文字','route flush failure keeps editor and text');
  await page.evaluate(()=>{window.auditCloseEvents=[];window.kaoyanDesktop.onPrepareClose(aborted=>{window.auditCloseEvents.push(aborted===true);return true;});});
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].close());
  await page.waitForFunction(()=>window.auditCloseEvents?.includes(true));
  check(await closeField.isEnabled() && await closeField.inputValue()==='退出失败时仍需保留并可编辑的文字','native close veto retains text and unfreezes editing'); await shot('native-close-flush-error');
  await page.unroute('**/api/notes/drafts/'+closeDraft.id); await page.getByRole('button',{name:'重试保存草稿',exact:true}).click(); await saved();
  const current=await api('/'+ids.note_id); await api('/'+ids.note_id+'/status',{operation_id:'audit-archive-'+ids.note_id,expected_revision:current.revision,status:'archived'},'PATCH');
  for(const [w,h] of [[1280,820],[1024,768],[760,820]]) {
    await size(w,h); await go('/notes/'+ids.note_id); check(await page.locator('.note-header-state').isVisible() && (await page.locator('.note-header-state').innerText()).includes('已归档'),`${w}: archived state remains visible`); await shot(`${w}-archived`);
    check(await page.getByRole('button',{name:'编辑',exact:true}).isDisabled(),`${w}: archived note cannot enter edit`);
  }
  // The actual close handshake is run on an isolated dirty draft with a failed flush.
  const manual=await api('/drafts',{kind:'edit',note_id:ids.note_id,base_revision:3}).catch(()=>null);
  result.measurements.archiveBlocksEditDraft=manual===null;
  check(manual===null,'archived authority rejects a new edit draft');
  await page.emulateMedia({reducedMotion:'reduce'}); await go('/notes/'+ids.note_id+'?revision=1'); await shot('reduced-motion-history');
  check(await page.getByText('历史版本 1 · 只读',{exact:false}).isVisible(),'reduced motion retains history status');
}
