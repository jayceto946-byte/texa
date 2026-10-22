const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRemoteConnection } = require('./remote-connection.cjs');
function fixture(config = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'texa-remote-test-'));
  const statePath = path.join(dir,'state.json');
  let target = 'http://127.0.0.1:49155', ready = true;
  const calls = [];
  const run = async (file,args) => {
    calls.push(args);
    if (args[0] === 'status') return JSON.stringify({BackendState:'Running',Self:{DNSName:'texa.tail123.ts.net.'}});
    if (args[1] === 'status') return JSON.stringify(config);
    if (args.includes('off')) config = {};
    else config = {TCP:{443:{HTTPS:true}},Web:{'texa.tail123.ts.net:443':{Handlers:{'/':{Proxy:target}}}}};
    return '';
  };
  const service = createRemoteConnection({statePath,getTarget:()=>target,isReady:()=>ready,run});
  return {service,calls,setTarget:v=>target=v,setReady:v=>ready=v,save:v=>fs.writeFileSync(statePath,JSON.stringify(v)),cleanup:()=>fs.rmSync(dir,{recursive:true,force:true})};
}
test('one click uses actual port; restart follows changed port; disable removes owned mapping',async t=>{
 const f=fixture();t.after(f.cleanup);
 let result=await f.service.setEnabled(true);assert.equal(result.enabled,true);assert.equal(result.url,'https://texa.tail123.ts.net/');
 assert.ok(f.calls.some(args=>args.includes('http://127.0.0.1:49155')));
 f.setTarget('http://127.0.0.1:49156');await f.service.restore();assert.ok(f.calls.some(args=>args.includes('http://127.0.0.1:49156')));
 assert.equal((await f.service.setEnabled(false)).enabled,false);
});
test('unrelated root handler remains untouched',async t=>{
 const f=fixture({Web:{'texa.tail123.ts.net:443':{Handlers:{'/':{Proxy:'http://127.0.0.1:9000'}}}}});t.after(f.cleanup);
 await assert.rejects(f.service.setEnabled(true),/其他服务占用/);assert.ok(f.calls.every(args=>args.length===2||args[1]==='status'));
});
test('never enables or edits Funnel',async t=>{
 const f=fixture({AllowFunnel:{'texa.tail123.ts.net:443':true}});t.after(f.cleanup);await assert.rejects(f.service.setEnabled(true),/公网共享/);
});
test('existing exact target can be adopted after device rename',async t=>{
 const f=fixture({Web:{'old.tail123.ts.net:443':{Handlers:{'/':{Proxy:'http://127.0.0.1:49155'}}}}});t.after(f.cleanup);
 assert.equal((await f.service.setEnabled(true)).enabled,true);
});
test('not ready and nonlocal backend never mutate Tailscale',async t=>{
 const f=fixture();t.after(f.cleanup);f.setReady(false);await assert.rejects(f.service.setEnabled(true),/尚未就绪/);assert.equal(f.calls.length,0);
 f.setReady(true);f.setTarget('http://example.com:80');await assert.rejects(f.service.setEnabled(true),/本地服务/);assert.equal(f.calls.length,0);
});
test('missing Tailscale returns actionable state without commands',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'texa-no-cli-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const service=createRemoteConnection({statePath:path.join(dir,'state'),getTarget:()=> 'http://127.0.0.1:49200',isReady:()=>true,run:async()=>{throw Object.assign(new Error('missing'),{code:'ENOENT'});}});
 const result=await service.status();assert.match(result.message,/未找到.*命令行/);assert.equal(result.error_code,'cli_unavailable');assert.equal(result.enabled,false);
});

test('first enable accepts null Serve config and creates the current user address', async t => {
 const f=fixture(null);t.after(f.cleanup);
 assert.equal((await f.service.status()).message,'手机连接未开启');
 assert.equal((await f.service.setEnabled(true)).enabled,true);
});

function windowsService(t, run, env = {}) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'texa-windows-remote-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 return createRemoteConnection({statePath:path.join(dir,'state'),getTarget:()=> 'http://127.0.0.1:49200',isReady:()=>true,platform:'win32',env,run});
}
const running = JSON.stringify({BackendState:'Running',Self:{DNSName:'my-pc.my-network.ts.net.'}});
const missing = () => Object.assign(new Error('missing'),{code:'ENOENT'});

test('Windows discovers native Program Files outside PATH and enables HTTPS for its own tailnet', async t => {
 const calls=[];let config=null;
 const executable=String.raw`D:\Native Apps\Tailscale\tailscale.exe`;
 const service=windowsService(t, async(file,args)=>{
   calls.push({file,args});
   if(file!==executable)throw missing();
   if(args[0]==='status')return running;
   if(args[1]==='status')return JSON.stringify(config);
   config={Web:{'my-pc.my-network.ts.net:443':{Handlers:{'/':{Proxy:'http://127.0.0.1:49200'}}}}};
   return '';
 },{ProgramW6432:String.raw`D:\Native Apps`,ProgramFiles:String.raw`C:\Program Files (x86)`});
 const result=await service.setEnabled(true);
 assert.equal(result.enabled,true);assert.equal(result.url,'https://my-pc.my-network.ts.net/');
 assert.ok(calls.every(call=>call.file===executable));
 assert.ok(calls.some(call=>call.args.includes('http://127.0.0.1:49200')));
});

test('Windows tries other installation roots and PATH when a candidate is absent', async t => {
 for(const executable of [String.raw`E:\Apps\Tailscale\tailscale.exe`,'tailscale.exe']){
   const calls=[];
   const service=windowsService(t,async(file,args)=>{
     calls.push(file);if(file!==executable)throw missing();return args[0]==='status'?running:'null';
   },{ProgramW6432:String.raw`D:\Missing`,ProgramFiles:String.raw`E:\Apps`});
   assert.equal((await service.status()).url,'https://my-pc.my-network.ts.net/');
   assert.ok(calls.includes(executable));
 }
});

test('a cached executable can be rediscovered after installation moves', async t => {
 let moved=false;
 const service=windowsService(t,async(file,args)=>{
   const executable=moved?'tailscale.exe':String.raw`C:\Program Files\Tailscale\tailscale.exe`;
   if(file!==executable)throw missing();return args[0]==='status'?running:'{}';
 });
 assert.equal((await service.status()).error_code,undefined);moved=true;
 assert.equal((await service.status()).error_code,undefined);
});

test('Serve errors after confirmed login identify phase and do not expose command output', async t => {
 const cases=[
   [{stderr:'access is denied',code:1},'permission_denied',/管理权限/],
   [{stderr:'flag provided but not defined: -yes',code:1},'cli_unsupported',/更新 Tailscale/],
   [{stdout:'Serve is not enabled on your tailnet. https://login.tailscale.com/f/serve?secret=do-not-show',killed:true},'https_required',/HTTPS Certificates/],
   [{code:'ETIMEDOUT',killed:true},'cli_timeout',/超时/],
   [{stderr:'failed to connect to local tailscaled',code:1},'daemon_unavailable',/本机 Tailscale 服务/],
   [{stderr:'unknown internal failure secret=do-not-show',code:1},'serve_failed',/已连接.*读取 HTTPS 共享配置/],
 ];
 for(const [failure,code,message] of cases){
   const service=windowsService(t,async(_,args)=>{
     if(args[0]==='status')return running;throw Object.assign(new Error('do-not-show'),failure);
   });
   const result=await service.status();
   assert.equal(result.error_code,code);assert.match(result.message,message);
   assert.doesNotMatch(JSON.stringify(result),/do-not-show|f\/serve|尚未登录/);
 }
});

test('login, disconnected, malformed and missing DNS states remain distinct', async t => {
 for(const [output,code] of [
   [JSON.stringify({BackendState:'NeedsLogin'}),'login_required'],
   [JSON.stringify({BackendState:'Stopped'}),'daemon_not_running'],
   ['not-json secret=do-not-show','status_invalid'],
   [JSON.stringify({BackendState:'Running',Self:{}}),'dns_unavailable'],
 ]){
   const calls=[];const service=windowsService(t,async(_,args)=>{calls.push(args);return output;});
   assert.equal((await service.status()).error_code,code);
   assert.ok(calls.every(args=>args[0]==='status'));
 }
});

test('malformed Serve config blocks changes without leaking the response', async t => {
 const calls=[];const service=windowsService(t,async(_,args)=>{
   calls.push(args);return args[0]==='status'?running:'private invalid response';
 });
 assert.equal((await service.status()).error_code,'serve_invalid');
 await assert.rejects(service.setEnabled(true),/共享配置返回格式异常/);
 assert.ok(calls.every(args=>args[0]==='status'||args[1]==='status'));
});

test('write failures and failed verification are never reported as success', async t => {
 let statusReads=0;
 const service=windowsService(t,async(_,args)=>{
   if(args[0]==='status')return running;
   if(args[1]==='status'){
     if(++statusReads>1)throw new Error('query failed');
     return JSON.stringify({Web:{'my-pc.my-network.ts.net:443':{Handlers:{'/':{Proxy:'http://127.0.0.1:49200'}}}}});
   }
   return '';
 });
 await assert.rejects(service.setEnabled(false),/读取 HTTPS 共享配置/);
 const failedWrite=windowsService(t,async(_,args)=>{
   if(args[0]==='status')return running;if(args[1]==='status')return 'null';throw new Error('write failed');
 });
 await assert.rejects(failedWrite.setEnabled(true),/更新 HTTPS 共享配置失败/);
});
