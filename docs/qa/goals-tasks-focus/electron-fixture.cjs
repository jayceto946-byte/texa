// Launch only this isolated QA wrapper; it runs the current desktop main/preload.
const {app} = require('electron');
const path = require('node:path');
const fs = require('node:fs');
app.setName('Texa Focus QA');
const qa = process.env.KAOYAN_USER_DATA_DIR;
if (!qa || !qa.startsWith('/private/tmp/texa-focus-qa')) throw Error('Disposable QA userData required');
fs.mkdirSync(qa,{recursive:true});
fs.writeFileSync(path.join(qa,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
app.on('browser-window-created', (_event, window) => {
  window.webContents.on('console-message', (_event, _level, message) => console.log('[QA renderer]', message));
  window.webContents.on('did-finish-load', () => {
    setTimeout(async () => {
      if (window.isDestroyed()) return;
      const value = await window.webContents.executeJavaScript(`({url:location.pathname,width:innerWidth,height:innerHeight,scrollY,root:document.getElementById('root')?.getBoundingClientRect().toJSON(),inert:[...document.querySelectorAll('[inert]')].map(e=>e.id||e.className),dialog:!!document.querySelector('[role=dialog]'),text:document.body.innerText.slice(0,500)})`).catch(error=>({error:error.message}));
      console.log('[QA DOM]', JSON.stringify(value));
    },1000);
  });
});
require('../../../desktop/main.cjs');
