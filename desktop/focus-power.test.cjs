const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
function bridge() {
  const ipc = new EventEmitter(), sent=[];
  ipc.invoke=async()=>true; ipc.sendSync=()=>({}); ipc.send=(...value)=>sent.push(value);
  let api;
  vm.runInNewContext(readFileSync(require.resolve('./preload.cjs'),'utf8'),{
    require:name=>{assert.equal(name,'electron');return {ipcRenderer:ipc,contextBridge:{exposeInMainWorld:(_key,value)=>{api=value;}}};},
    process:{platform:'darwin'},Set,Promise,
  });
  return {ipc,api,sent};
}
test('power bridge exposes only suspend/resume and unsubscribes without duplication',()=>{
  const {ipc,api}=bridge(),events=[];
  const remove=api.onFocusPower(value=>events.push(value));
  ipc.emit('focus:power',{},'suspend');ipc.emit('focus:power',{},'arbitrary-command');ipc.emit('focus:power',{},'resume');
  assert.deepEqual(events,['suspend','resume']);
  remove();ipc.emit('focus:power',{},'suspend');assert.equal(events.length,2);
});
test('failed note preparation still runs focus preparation and vetoes window closure',async()=>{
  const {ipc,api,sent}=bridge(),order=[];
  api.onPrepareClose(async()=>{order.push('note');return false;});
  api.onPrepareClose(async()=>{order.push('focus-paused');return true;});
  ipc.emit('window:prepare-close',{},'nonce');
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(order,['note','focus-paused']);assert.deepEqual(sent,[['window:prepared-close','nonce',false]]);
});
test('aborted close notifies handlers without silently restarting a focus run',async()=>{
  const {ipc,api}=bridge(),events=[];
  api.onPrepareClose(async aborted=>{events.push(aborted);return true;});
  ipc.emit('window:close-aborted',{});await Promise.resolve();assert.deepEqual(events,[true]);
});
