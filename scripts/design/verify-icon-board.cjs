/** Run with desktop/node_modules/.bin/electron. Isolated renderer; no backend or user profile. */
const { app, BrowserWindow } = require('electron');
const { mkdirSync, writeFileSync, mkdtempSync } = require('node:fs');
const { resolve } = require('node:path');
const out = resolve(process.argv[2] || '/tmp/texa-icon-board-qa');
mkdirSync(out, { recursive: true });
app.setPath('userData', mkdtempSync('/tmp/texa-icon-board-profile-'));
const result = { environment: 'macOS ARM64 / Electron 37 / Vite isolated design entry', checks: [], errors: [], screenshots: [] };
const pause = ms => new Promise(r => setTimeout(r, ms));
app.whenReady().then(async () => {
  const w = new BrowserWindow({ width: 1280, height: 848, show: false, webPreferences: { contextIsolation: true } });
  const js = source => w.webContents.executeJavaScript(source);
  const check = (name, ok) => { result.checks.push({ name, passed: !!ok }); if (!ok) throw Error(name); };
  const shot = async name => { await pause(100); writeFileSync(resolve(out, name + '.png'), (await w.webContents.capturePage()).toPNG()); result.screenshots.push(name + '.png'); };
  const select = async (selector, value) => { await js(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;setter.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('change',{bubbles:true}));})()`); await pause(70); };
  try {
    await w.loadURL('http://127.0.0.1:5173/icon-workspace-preview.html?entry=/');
    await pause(6000);
    const original = await js('document.body.innerText');
    result.originalPreview = original.slice(0, 1000);
    if (original.includes('学习')) await shot('existing-workspace');
    await w.loadURL('http://127.0.0.1:5173/icon-design.html');
    await pause(1500);
    await js('document.fonts.ready');
    await js("document.documentElement.style.scrollBehavior='auto'");
    check('20 semantics / 60 selectable candidates', await js("document.querySelectorAll('.ib-candidate').length === 60"));
    const storageBefore = await js("localStorage.getItem('texa_appearance_theme')");
    await shot('board-1280');
    await select('.ib-controls select', '2');
    check('tier filter returns six navigation semantics', await js("document.querySelectorAll('.ib-icon-row').length===6"));
    await js("document.querySelector('#comparison').scrollIntoView();document.querySelector('[aria-label=\"B 错题\"]').click()"); await pause(100);
    check('candidate selection updates size heading', await js("document.querySelector('#sizes h2').textContent.includes('mistakes')"));
    await shot('navigation-comparison');
    await select('.ib-controls select', '3');
    await shot('identity-comparison');
    await js("document.querySelector('[aria-label=\"C 数学验证\"]').click();document.querySelector('#sizes').scrollIntoView()");
    await pause(100);
    check('C 16px has reduced path detail', await js("document.querySelector('#sizes .ib-size-row:last-child svg').innerHTML !== document.querySelectorAll('#sizes .ib-size-row:last-child svg')[1].innerHTML"));
    await shot('optical-sizes');
    for (const [width, height] of [[1280, 848], [1024, 796], [760, 848]]) {
      w.setSize(width, height); await pause(100);
      await js("document.querySelector('#context').scrollIntoView()");
      await shot('context-' + width);
      check('no document overflow at ' + width, await js('document.documentElement.scrollWidth<=innerWidth'));
    }
    w.setSize(1280, 848);
    for (const id of ['mineral','graphite','clay','notebook','codex']) {
      await select('.ib-masthead select', id);
      await js("document.querySelector('#context').scrollIntoView()");
      check(id + ' tokens applied', await js("getComputedStyle(document.querySelector('.icon-board')).getPropertyValue('--color-bg-primary').trim().length>0"));
      await shot('theme-' + id);
    }
    check('theme preference unchanged', await js("localStorage.getItem('texa_appearance_theme')") === storageBefore);
    await js("document.querySelector('.ib-nav-link').click();document.querySelector('.ib-composer textarea').focus()");
    w.webContents.insertText('教材检索图标测试'); await pause(150);
    check('typing enables send', await js("!document.querySelector('.ib-composer .app-primary-button').disabled"));
    await js("document.querySelector('.ib-composer .app-primary-button').click()"); await pause(100);
    check('send updates local status and clears draft', await js("document.querySelector('.ib-live').textContent.includes('已预览发送') && !document.querySelector('.ib-composer textarea').value"));
    await js("document.querySelector('.ib-state-button.state-0').focus()");
    check('keyboard focus visible', await js("document.activeElement.classList.contains('ib-state-button')"));
    const download = new Promise(resolveDownload => w.webContents.session.once('will-download', (_event, item) => { item.setSavePath(resolve(out, item.getFilename())); item.once('done', (_e, state) => resolveDownload(state)); }));
    await js("document.querySelector('#sizes .app-secondary-button').click()");
    check('SVG download completes', await download === 'completed');
    result.requests = await js("performance.getEntriesByType('resource').filter(r=>new URL(r.name).pathname.startsWith('/api/')).map(r=>r.name)");
    check('design board makes no API calls', result.requests.length === 0);
  } catch (error) { result.errors.push(String(error)); process.exitCode = 1; }
  writeFileSync(resolve(out, 'results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  app.exit(result.errors.length ? 1 : 0);
});
