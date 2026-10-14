import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,extname} from 'node:path';
const {chromium}=createRequire(import.meta.url)('playwright');
const root=process.cwd(),out='/tmp/texa-refine-evidence';mkdirSync(out,{recursive:true});
const up=spawn(process.execPath,['scripts/visual-preview-server.mjs'],{env:{...process.env,TEXA_VISUAL_PORT:'18043'},stdio:'ignore'});
const task={id:'focus-qa',goal_id:'goal-visual-1',title:'读懂极限定义并完成一道例题',content:'读懂极限定义并完成一道例题',duration_seconds:1500,elapsed_seconds:180,status:'in_progress',revision:1};
let focus={revision:1,tasks:[task],current_task:task,status:'paused',remaining_seconds:1320,server_time:Date.now()/1000};
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.ttf':'font/ttf'};
const server=createServer(async(req,res)=>{try{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/api/focus'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,data:{...focus,server_time:Date.now()/1000}}));return;}
 if(url.pathname==='/api/focus/commands'){let body='';for await(const c of req)body+=c;const p=JSON.parse(body);if(p.operation==='create'){focus.tasks.push({...task,id:'focus-qa-2',title:p.title,content:p.content,status:'pending',duration_seconds:p.duration_seconds});}else focus.status=p.operation==='pause'?'paused':'running';focus.revision++;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true,data:focus}));return;}
 if(url.pathname.startsWith('/api/')||url.pathname==='/health'){const response=await fetch('http://127.0.0.1:18043'+req.url);res.setHeader('Content-Type','application/json');let value=await response.json();if(url.pathname==='/api/chat/conversations')value.data={items:value.data.map(x=>({...x,management:{state:'active',pinned:false,revision:0}})),has_more:false,next_cursor:null};if(url.pathname.endsWith('/management'))value={success:true,data:{state:'active',pinned:false,revision:0}};res.end(JSON.stringify(value));return;}
 const file=resolve(root,'frontend/dist',url.pathname.slice(1));let data;try{data=readFileSync(file);res.setHeader('Content-Type',mime[extname(file)]||'application/octet-stream');}catch{data=readFileSync(resolve(root,'frontend/dist/index.html'));res.setHeader('Content-Type','text/html');}res.end(data);
}catch(e){res.writeHead(500);res.end(String(e));}});
await new Promise(r=>server.listen(18042,'127.0.0.1',r));
if(process.env.TEXA_REFINE_SERVER_ONLY==='1'){process.on('SIGTERM',()=>{server.close();up.kill();process.exit();});await new Promise(()=>{});}
let browser;const result={checks:[],errors:[]};
try{
 browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const ctx=await browser.newContext();await ctx.addInitScript(()=>{
 localStorage.setItem('texa:setup-complete:v3','1');localStorage.setItem('texa_appearance_theme','mineral');
 let enabled=false;window.kaoyanDesktop={isElectron:true,platform:'darwin',getSetupComplete:async()=>true,isMaximized:async()=>false,isFullScreen:async()=>false,setStartupAppearance:async()=>true,getBackendStatus:async()=>({status:'ready',message:''}),getRemoteS0Status:async()=>({ready:true,enabled,url:'https://texa.tail123.ts.net/',message:enabled?'手机连接已开启':'手机连接未开启',target:'http://127.0.0.1:49151'}),setRemoteConnectionEnabled:async value=>{enabled=value;return window.kaoyanDesktop.getRemoteS0Status();},copyRemoteConnectionUrl:async()=>true,copyRemoteS0Token:async()=>true};
 });
 const page=await ctx.newPage();page.on('pageerror',e=>result.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')result.errors.push(m.text());});
 for(const width of [1280,1024,760,390]){
 await page.setViewportSize({width,height:820});
 for(const route of ['/','/goals','/books']){
 await page.goto('http://127.0.0.1:18042'+route);await page.waitForLoadState('networkidle');await page.waitForTimeout(250);
 if(route==='/goals'){
 const rows=page.locator('.goal-list-item');if(await rows.count()){if(width<640)await page.getByRole('button',{name:'目标列表',exact:true}).click();await rows.first().click();}
 await page.getByRole('button',{name:'添加番茄任务'}).click();await page.getByLabel('这段时间做什么').fill('复习极限定义');await page.waitForTimeout(200);
 }
 if(route==='/'&&width>=1024){const direct=await page.locator('.app-rail > .app-rail-primary').count();if(direct!==1)throw Error('desktop navigation wrapped '+await page.evaluate(()=>({url:location.href,rails:[...document.querySelectorAll('.app-rail')].map(e=>e.outerHTML),text:document.body.innerText.slice(0,500)})).then(JSON.stringify));}
 await page.screenshot({path:out+`/${width}-${route==='/'?'chat':route.slice(1)}.png`});
 const metric=await page.evaluate(()=>({body:document.body.scrollWidth,width:innerWidth}));if(metric.body>width)throw Error('body overflow '+JSON.stringify(metric));
 result.checks.push({width,route,...metric});
 }
 await page.goto('http://127.0.0.1:18042/settings');await page.waitForLoadState('networkidle');if(await page.getByRole('button',{name:'返回设置',exact:true}).isVisible())await page.getByRole('button',{name:'返回设置',exact:true}).click();await page.getByRole('button',{name:'手机连接',exact:true}).click();await page.getByRole('button',{name:'开启手机连接',exact:true}).click();await page.getByRole('button',{name:'复制地址',exact:true}).click();await page.screenshot({path:out+`/${width}-remote.png`});
 if(await page.locator('.remote-connection').innerText().then(t=>t.includes('tailscale serve')||t.includes('59999')))throw Error('raw command exposed');result.checks.push({width,case:'remote toggle and copy'});
 }
 await page.setViewportSize({width:1280,height:820});await page.goto('http://127.0.0.1:18042/');await page.waitForLoadState('networkidle');
 await page.getByRole('link',{name:'目标与任务',exact:true}).click();const motion=await page.locator('.persistent-route-panel:not([hidden])').evaluate(e=>e.getAnimations().map(a=>a.effect.getTiming().duration));result.checks.push({case:'route motion',motion});
 await page.emulateMedia({reducedMotion:'reduce'});await page.getByRole('link',{name:'学习',exact:true}).click();await page.waitForTimeout(100);result.checks.push({case:'reduced motion',activeAnimations:await page.locator('.persistent-route-panel:not([hidden])').evaluate(e=>e.getAnimations().length)});
}catch(e){result.errors.push(String(e));process.exitCode=1;}finally{writeFileSync(out+'/results.json',JSON.stringify(result,null,2));if(browser)await browser.close();server.close();up.kill();}
