/** Isolated Electron renderer QA for production components, with in-memory API fixtures. */
const { app, BrowserWindow } = require('electron');
const { mkdtempSync, mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const out = resolve('/tmp/texa-integrated-icons');
mkdirSync(out, { recursive:true });
app.setPath('userData', mkdtempSync('/tmp/texa-integrated-icons-profile-'));
const result = { environment:'macOS Electron 37; actual business components on isolated Vite fixture; no live backend/model/storage', checks:[], errors:[], screenshots:[] };
app.whenReady().then(async()=>{
  const win = new BrowserWindow({width:1280,height:848,show:false,webPreferences:{contextIsolation:true}});
  const js=s=>win.webContents.executeJavaScript(s);
  const delay=ms=>new Promise(r=>setTimeout(r,ms));
  const check=(name,passed)=>{result.checks.push({name,passed});if(!passed)throw Error(name)};
  const shot=async name=>{writeFileSync(resolve(out,name+'.png'),(await win.webContents.capturePage()).toPNG());result.screenshots.push(name+'.png')};
  win.webContents.on('console-message',event=>{if(event.level==='error')result.errors.push(event.message)});
  try {
    for(const scene of ['chat','notes','books','goals']){
      await win.loadURL(`http://127.0.0.1:5173/icon-workspace-preview.html?scene=${scene}&platform=darwin`);
      for(let n=0;n<80;n++){if(await js("document.querySelectorAll('[data-texa-icon]').length>5"))break;await delay(100)}
      await js('document.fonts.ready'); await delay(300);
      check(scene+' uses production icons',await js("document.querySelectorAll('[data-texa-icon]').length>5"));
      check(scene+' has approved mistake navigation',await js("!!document.querySelector('a[href=\"/mistakes\"] [data-texa-icon=\"mistakes\"]')"));
      check(scene+' navigation stroke is 1.8',await js("getComputedStyle(document.querySelector('.app-rail-link [data-texa-icon]')).strokeWidth==='1.8px'"));
      await shot(scene+'-1280');
      if(scene==='chat')for(const [width,height] of [[1024,796],[760,848]]){
        win.setSize(width,height);await delay(200);
        check('no document overflow '+width,await js('document.documentElement.scrollWidth<=innerWidth'));
        check('send retains accessible name '+width,await js("!!document.querySelector('button[aria-label=\"发送问题\"] [data-texa-icon=\"send\"]')"));
        await shot('chat-'+width);
      }
      win.setSize(1280,848);
    }
    check('fixture does not connect to backend',await js("performance.getEntriesByType('resource').filter(r=>new URL(r.name).pathname.startsWith('/api/')).length===0"));
  }catch(error){result.errors.push(String(error))}
  writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));app.exit(result.errors.length?1:0);
});
