/** Current production renderer + real Electron shell; backend must be isolated. */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import { livePrompt } from './qa-notes-review-content.mjs';
const { _electron } = createRequire(import.meta.url)('playwright');
const phase = process.argv[2] || 'notes';
const base = resolve('docs/qa/ui-pilot-closeout-2026-10-19');
const out = resolve(base, phase, new Date().toISOString().replaceAll(':', '-'));
mkdirSync(out, { recursive: true });
const ids = JSON.parse(readFileSync(resolve(base, `${['live', 'notes-detail'].includes(phase) ? 'live' : 'notes'}-fixture-ids.json`)));
const result = { phase, environment: 'macOS ARM64, real Electron 37, production frontend, isolated production backend/storage', screenshots: [], checks: [], observations: {}, errors: [] };
let app, page;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const check = (ok, name) => { result.checks.push({ name, pass: !!ok }); if (!ok) throw Error(name); };
const record = () => writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2));
async function ready() {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.querySelectorAll('[data-texa-markdown-loading]')].every(el => !el.getBoundingClientRect().height));
}
async function shot(name, locator) {
  await ready(); const path = resolve(out, name + '.png');
  await (locator || page).screenshot({ path, scale: 'css', animations: 'disabled' });
  result.screenshots.push(path); record();
}
const size = (w, h) => app.evaluate(({ BrowserWindow }, [width, height]) => BrowserWindow.getAllWindows()[0].setContentSize(width, height), [w, h]);
const api = (path, body, method) => page.evaluate(async ({ path, body, method }) => {
  const response = await fetch('/api' + path, { method: method || (body ? 'POST' : 'GET'), headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const value = await response.json(); if (!response.ok || !value.success) throw Error(value.code || response.status); return value.data;
}, { path, body, method });
const go = async path => { await page.goto('http://127.0.0.1:18136' + path); await page.locator('.app-shell').waitFor(); await ready(); };
const state = async () => page.evaluate(() => ({ active: { tag: document.activeElement?.tagName, label: document.activeElement?.getAttribute('aria-label'), text: document.activeElement?.textContent?.slice(0, 50) }, scrollTop: document.querySelector('.note-scroll')?.scrollTop, scrollHeight: document.querySelector('.note-scroll')?.scrollHeight, viewport: [innerWidth, innerHeight] }));
try {
  const userData = resolve('/private/tmp/texa-closeout-electron-' + Date.now()); mkdirSync(userData, { recursive: true });
  writeFileSync(resolve(userData, 'setup-complete.json'), JSON.stringify({ version: 3, complete: true }));
  app = await _electron.launch({ executablePath: resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'), args: [resolve('desktop')], env: { ...process.env, KAOYAN_USER_DATA_DIR: userData, KAOYAN_SKIP_BACKEND: '1', KAOYAN_BACKEND_URL: 'http://127.0.0.1:18136', KAOYAN_FRONTEND_DEV_URL: 'http://127.0.0.1:18136' } });
  page = await app.firstWindow(); page.setDefaultTimeout(20000); page.on('pageerror', e => { result.errors.push(String(e)); record(); });
  await size(1280, 820); await page.locator('.app-shell').waitFor();
  check(await page.evaluate(() => window.kaoyanDesktop?.isElectron), 'real Electron preload');
  if (phase === 'notes') {
    const editor = `/notes/drafts/${ids.draft_id}`;
    const preview = `/notes/drafts/${ids.preview_id}`;
    for (const [w, h] of [[1280, 820], [1024, 768], [760, 820]]) {
      await size(w, h);
      await go(preview); await page.getByRole('button', { name: '编辑笔记', exact: true }).waitFor();
      await shot(`${w}-preview-top`);
      await page.locator('#review-e4').scrollIntoViewIfNeeded(); await shot(`${w}-preview-matrix`);
      await go(editor); await page.getByRole('button', { name: '阅读预览', exact: true }).waitFor();
      await page.locator('math-field').last().waitFor(); await shot(`${w}-edit-top`);
      await page.getByRole('textbox', { name: '第 4 块正文', exact: true }).focus();
      await shot(`${w}-edit-focused-block`);
      result.observations[`${w}-focused`] = await state();
      result.observations[`${w}-blocks`] = await page.locator('.note-edit-block').evaluateAll(els => els.map(el => {
        const css = getComputedStyle(el); const bar = el.querySelector('.note-toolbar'); const r = el.getBoundingClientRect();
        return { id: el.id, className: el.className, focused: el.contains(document.activeElement), border: css.border, padding: css.padding, background: css.backgroundColor, toolbarOpacity: getComputedStyle(bar).opacity, toolbarVisibility: getComputedStyle(bar).visibility, toolbarDisplay: getComputedStyle(bar).display, y: r.y, height: r.height };
      }));
      await page.getByRole('button', { name: '上移第 4 块', exact: true }).hover(); await shot(`${w}-edit-toolbar-hover`);
      await page.locator('#review-e4').scrollIntoViewIfNeeded(); await page.getByLabel('第 13 块公式', { exact: true }).focus(); await shot(`${w}-edit-matrix-focus`);
      check(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${w}: no document horizontal overflow`);
    }
    await size(1280, 820); await go(editor); await page.getByRole('button', { name: '阅读预览', exact: true }).waitFor();
    await page.getByRole('textbox', { name: '第 4 块正文', exact: true }).focus();
    result.observations.toggleBefore = await state();
    await page.getByRole('button', { name: '阅读预览', exact: true }).click(); result.observations.togglePreview = await state(); await shot('toggle-preview-same-scroll');
    await page.getByRole('button', { name: '编辑笔记', exact: true }).click(); result.observations.toggleEdit = await state(); await shot('toggle-back-edit');
    // Real autosave requests/SQL. Delay PATCH dispatch for state observation only.
    const field = page.getByRole('textbox', { name: '第 2 块正文', exact: true });
    const original = await field.inputValue();
    await page.route('**/api/notes/drafts/' + ids.draft_id, async route => {
      if (route.request().method() === 'PATCH') await sleep(1600);
      await route.continue();
    });
    await field.fill(original + '\n\n补充：这句仅用于观察草稿保存状态。');
    await page.getByText('有未保存修改', { exact: true }).waitFor(); await shot('save-dirty');
    await page.getByText('正在保存草稿…', { exact: true }).waitFor(); await shot('save-pending');
    await page.getByText('草稿已保存', { exact: true }).waitFor(); await shot('save-saved');
    await page.unroute('**/api/notes/drafts/' + ids.draft_id);
    check((await api('/notes/' + ids.note_id)).revision === 1, 'autosave does not publish a formal revision');
    const response = page.waitForResponse(r => r.url().endsWith('/api/notes/drafts/' + ids.draft_id + '/save'));
    await page.getByRole('button', { name: '保存修改', exact: true }).click(); await response;
    await page.waitForURL('**/notes/' + ids.note_id); await page.getByText('已保存 · 版本 2', { exact: false }).waitFor(); await shot('formal-saved-v2');
    check((await api('/notes/' + ids.note_id)).revision === 2, 'explicit save publishes formal revision 2');
    await go('/notes/' + ids.note_id + '?revision=1'); await page.getByText('历史版本 1 · 只读', { exact: false }).waitFor(); await shot('history-v1-readonly');
    check(!await page.getByRole('button', { name: '编辑', exact: true }).count(), 'historical version has no edit action');
    // Two real edit drafts reproduce the existing formal-revision conflict.
    const a = await api('/notes/drafts', { kind: 'edit', note_id: ids.note_id, base_revision: 2 });
    const b = await api('/notes/drafts', { kind: 'edit', note_id: ids.note_id, base_revision: 2 });
    await go('/notes/drafts/' + a.id); await page.getByRole('button', { name: '保存修改', exact: true }).waitFor();
    await api('/notes/drafts/' + b.id + '/save', { operation_id: 'review-parallel-save', expected_draft_revision: b.draft_revision, base_note_revision: 2 });
    await page.getByRole('button', { name: '保存修改', exact: true }).click(); await page.getByText('正式笔记版本已变化', { exact: true }).waitFor(); await shot('formal-version-conflict');
    check(await page.getByRole('button', { name: '保存修改', exact: true }).isDisabled(), 'formal version conflict disables publish');
    result.observations.conflictDraftPreserved = (await api('/notes/drafts/' + a.id)).status === 'editable';
    check(result.observations.conflictDraftPreserved, 'conflict retains editable draft');
  } else if (phase === 'notes-detail') {
    await go('/notes/drafts/' + ids.draft_id); await page.getByRole('button', { name: '阅读预览', exact: true }).waitFor();
    await page.locator('math-field').last().waitFor(); await shot('same-draft-edit-top');
    await page.getByRole('textbox', { name: '第 4 块正文', exact: true }).focus(); await shot('same-draft-edit-focused');
    const geometry = () => page.evaluate(() => {
      const rect = el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
      return { header: rect(document.querySelector('.note-page-header')), document: rect(document.querySelector('.note-document')), scroll: { top: document.querySelector('.note-scroll').scrollTop, height: document.querySelector('.note-scroll').scrollHeight }, fields: [...document.querySelectorAll('.note-edit-block textarea')].map(el => { const c=getComputedStyle(el); return { label: el.getAttribute('aria-label'), focused: el===document.activeElement, rect: rect(el), scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, fontSize:c.fontSize, lineHeight:c.lineHeight, border:c.border, outline:c.outline, boxShadow:c.boxShadow }; }), active: document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent?.slice(0, 40) };
    });
    result.observations.edit = await geometry();
    await page.getByRole('button', { name: '阅读预览', exact: true }).click(); await ready(); await shot('same-draft-preview-after-toggle'); result.observations.previewAfterToggle = await geometry();
    await page.locator('.note-scroll').evaluate(el => { el.scrollTop=0; }); await shot('same-draft-preview-top');
    await page.locator('#review-p2').scrollIntoViewIfNeeded(); await shot('same-draft-preview-same-block');
    result.observations.previewText = await page.locator('.note-reading').evaluate(el => { const c=getComputedStyle(el.querySelector('.learning-reading-content')); return {fontSize:c.fontSize,lineHeight:c.lineHeight,rect:el.getBoundingClientRect().toJSON()}; });
    await page.getByRole('button', { name: '编辑笔记', exact: true }).click(); await page.locator('math-field').last().waitFor(); await shot('same-draft-edit-after-toggle'); result.observations.editAfterToggle = await geometry();
    await size(760,820); await shot('same-draft-760-header'); result.observations.narrow = await geometry();
    check(await page.evaluate(()=>document.body.scrollWidth<=innerWidth), 'same-draft narrow viewport has no document overflow');
  } else if (phase === 'native') {
    await go('/'); const field = page.locator('.composer-textarea'); await field.waitFor(); await field.focus();
    result.observations.nativeEvents = []; result.observations.streamRequests = 0;
    page.on('request', req => { if (req.url().endsWith('/api/chat/stream')) { result.observations.streamRequests++; record(); } });
    await page.exposeFunction('recordNativeEvent', event => { result.observations.nativeEvents.push(event); record(); });
    await page.evaluate(() => {
      for (const type of ['keydown', 'compositionstart', 'compositionupdate', 'compositionend', 'beforeinput', 'input']) document.querySelector('.composer-textarea').addEventListener(type, event => window.recordNativeEvent({ type, trusted: event.isTrusted, key: event.key, keyCode: event.keyCode, isComposing: event.isComposing, data: event.data, inputType: event.inputType, timestamp: performance.now(), value: event.target.value }));
    });
    const stop = resolve('/private/tmp/texa-closeout-native-done');
    console.log('Native probe ready; stop marker: ' + stop); record();
    for (let i = 0; i < 600 && !existsSync(stop); i++) await sleep(1000);
    result.observations.inputValue = await field.inputValue();
    await shot('native-final');
    result.observations.trustedComposition = result.observations.nativeEvents.some(e => e.type === 'compositionstart' && e.trusted);
  } else if (phase === 'live') {
    await go('/'); const field = page.locator('.composer-textarea'); await field.waitFor();
    result.observations.timeline = [];
    await page.exposeFunction('recordScrollFrame', frame => result.observations.timeline.push(frame));
    await page.evaluate(() => {
      const el = document.querySelector('.learning-workspace-scroll');
      if (!el) return;
      window.texaScrollProbe = setInterval(() => window.recordScrollFrame({ t: performance.now(), top: el.scrollTop, height: el.scrollHeight, viewport: el.clientHeight, textLength: [...el.querySelectorAll('.markdown-body')].reduce((n, v) => n + v.textContent.length, 0), returnVisible: !!document.querySelector('.reading-return-latest'), loading: !!document.querySelector('.composer-send.is-stopping') }), 75);
    });
    const wire = page.waitForResponse(r => r.url().endsWith('/api/chat/stream'));
    await field.fill(livePrompt); await page.getByRole('button', { name: '发送问题', exact: true }).click();
    const response = await wire;
    const streamText = response.text().then(text => { writeFileSync(resolve(out, 'real-sse.txt.gz'), gzipSync(text)); result.observations.sseBytes = Buffer.byteLength(text); });
    const scroll = page.locator('.learning-workspace-scroll');
    await page.waitForFunction(() => { const el = document.querySelector('.learning-workspace-scroll'); return el && el.scrollHeight - el.clientHeight > 500 && document.querySelector('.composer-send.is-stopping'); }, undefined, { timeout: 180000 });
    await shot('live-following-bottom'); result.observations.followingSample = await scroll.evaluate(el => ({ top: el.scrollTop, height: el.scrollHeight, viewport: el.clientHeight }));
    await scroll.hover(); await page.mouse.wheel(0, -580); await page.getByRole('button', { name: '回到最新对话' }).waitFor();
    result.observations.manualStart = await scroll.evaluate(el => ({ t: performance.now(), top: el.scrollTop, height: el.scrollHeight }));
    await shot('live-user-reading-up'); await sleep(2000);
    result.observations.manualEnd = await scroll.evaluate(el => ({ t: performance.now(), top: el.scrollTop, height: el.scrollHeight }));
    await shot('live-preserved-reading');
    await page.getByRole('button', { name: '回到最新对话' }).click();
    result.observations.returnSample = await scroll.evaluate(el => ({ top: el.scrollTop, height: el.scrollHeight, viewport: el.clientHeight })); await shot('live-return-latest');
    await page.getByRole('button', { name: '发送问题', exact: true }).waitFor({ timeout: 240000 }); await streamText; await shot('live-complete');
    await page.evaluate(() => clearInterval(window.texaScrollProbe));
    check(result.observations.timeline.length > 2, 'actual rendered scroll samples collected');
    check(Math.abs(result.observations.manualEnd.top - result.observations.manualStart.top) <= 4, 'user reading position retained during stream');
    check(result.observations.returnSample.height - result.observations.returnSample.viewport - result.observations.returnSample.top <= 64, 'return latest reaches bottom');
  }
  check(result.errors.length === 0, 'no renderer exceptions');
} catch (error) { result.errors.push(String(error)); process.exitCode = 1; if (page) { await shot('failure').catch(() => {}); writeFileSync(resolve(out, 'failure.txt'), await page.locator('body').innerText().catch(() => '')); } }
finally { record(); writeFileSync(resolve(base, phase + '-latest.json'), JSON.stringify({ path: out }, null, 2)); await app?.evaluate(({ app }) => app.exit(0)).catch(() => {}); await app?.close().catch(() => {}); console.log(JSON.stringify({ out, checks: result.checks, errors: result.errors, screenshots: result.screenshots.length }, null, 2)); }
