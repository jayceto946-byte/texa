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
 const result=await service.status();assert.match(result.message,/安装并打开/);assert.equal(result.enabled,false);
});
