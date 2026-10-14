import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { get, post, isRemoteBrowser, ApiError } from '../../api/client';
import { readBrowserStorage, writeBrowserStorage } from '../../utils/browserStorage';
import { FocusContext, type FocusSnapshot, type FocusCommand, type FocusTask, type FocusMode } from './FocusContext';
import { acceptFocusSnapshot, projectFocus } from './timeProjection';
const pendingKey = `texa:focus-pending:v3:${encodeURIComponent(readBrowserStorage('sessionStorage','kaoyan_desktop_api_base') || location.origin)}`;
export default function FocusProvider({children}: {children: ReactNode}) {
  const [data,setData] = useState<FocusSnapshot | null>(null), [busy,setBusy] = useState(false), [error,setError] = useState('');
  const [pending,setPending] = useState(Boolean(readBrowserStorage('localStorage',pendingKey)));
  const [setupTask,setSetupTask] = useState<FocusTask | null>(null);
  const [projection,setProjection] = useState({elapsed:0,remaining:null as number | null,overtime:0});
  const pendingOperation = useRef(readBrowserStorage('localStorage',pendingKey));
  const current = useRef<FocusSnapshot | null>(null), gate = useRef(false), startGate = useRef(false), epoch = useRef(0), received = useRef(0), mounted = useRef(true);
  const accept = useCallback((next: FocusSnapshot) => {
    if (!mounted.current || !acceptFocusSnapshot(current.current,next)) return;
    current.current = next; received.current = performance.now(); setData(next); setProjection(projectFocus(next,received.current,received.current));
  },[]);
  const refresh = useCallback(async () => {
    const generation = ++epoch.current;
    try {
      const response = await get('/focus',10000);
      if (generation !== epoch.current || !mounted.current) return current.current;
      if (!response.success) throw new Error('专注状态暂不可读取');
      accept(response.data); return current.current;
    } catch (reason) {
      if (generation === epoch.current && mounted.current) setError(`${reason instanceof Error ? reason.message : '连接暂不可用'}。尚未同步，请核对后再操作。`);
      return null;
    }
  },[accept]);
  const clearPending = useCallback(() => {
    pendingOperation.current=null; writeBrowserStorage('localStorage',pendingKey,null); setPending(false);
  },[]);
  const command = useCallback(async (value: FocusCommand) => {
    if (gate.current || pendingOperation.current) return false;
    gate.current=true; setBusy(true); setError('');
    try {
      const snapshot=await refresh();
      if (!snapshot) return false;
      const payload={...value,expected_revision:snapshot.revision,operation_id:crypto.randomUUID()};
      const raw=JSON.stringify(payload);
      // Do not send a write that cannot be recovered after a renderer restart.
      writeBrowserStorage('localStorage',pendingKey,raw);
      if (readBrowserStorage('localStorage',pendingKey)!==raw) throw new Error('无法保存操作标识，请检查浏览器存储');
      pendingOperation.current=raw; setPending(true);
      const response=await post('/focus/commands',payload,6000);
      if (!response.success) throw new Error('操作未确认');
      clearPending(); if(value.operation==='complete'||value.operation==='delete')setSetupTask(null); await refresh(); return true;
    } catch (reason) {
      if (reason instanceof ApiError && reason.status>=400 && reason.status<500) {clearPending();await refresh();}
      setError(`${reason instanceof Error ? reason.message : '操作结果未确认'}；${pendingOperation.current?'请核对本次操作。':'本次操作未提交，请按当前状态重试。'}`); return false;
    }
    finally { gate.current=false; setBusy(false); }
  },[clearPending,refresh]);
  const reconcile = useCallback(async () => {
    if (gate.current) return;
    if (!pendingOperation.current) { await refresh(); return; }
    gate.current=true;setBusy(true);
    try {
      const payload=JSON.parse(pendingOperation.current);
      const receipt=await get(`/focus/operations/${encodeURIComponent(payload.operation_id)}`,6000);
      if (receipt.data) { clearPending(); setError(''); await refresh(); }
      else {
        const snapshot=await refresh();
        if (!snapshot) return;
        if (snapshot.revision!==payload.expected_revision) { clearPending();setError('该操作未提交，状态已更新，请按当前状态操作。');return; }
        const response=await post('/focus/commands',payload,6000); // Replay the same id and CAS, never a replacement write.
        if (!response.success) throw new Error('操作尚未确认');
        clearPending();setError('');await refresh();
      }
    } catch (reason) {if(reason instanceof ApiError && reason.status>=400&&reason.status<500){clearPending();await refresh();}setError(reason instanceof Error ? reason.message : '核对失败，请稍后重试');}
    finally { gate.current=false;setBusy(false); }
  },[clearPending,refresh]);
  const prepareStart=useCallback((task:FocusTask|null)=>{
    if(!task){setSetupTask(null);return;}
    const active=current.current?.current_session && current.current.current_session.status!=='ended';
    if(active)setSetupTask(task);
    else void command({operation:'select',task_id:task.id}).then(ok=>{if(ok)setSetupTask(task);});
  },[command]);
  const selectTask = useCallback(async (task: FocusTask) => {
    const snapshot=await refresh();if (!snapshot) return false;
    const open=snapshot.current_session && snapshot.current_session.status!=='ended';
    if (open && snapshot.current_task?.id!==task.id && !window.confirm('结束本次专注并选择另一项任务？已记录时间会保留，所选任务不会自动开始。')) return false;
    return command({operation:open && snapshot.current_task?.id!==task.id?'switch':'select',task_id:task.id});
  },[command,refresh]);
  const startTask = useCallback(async (task: FocusTask,mode: FocusMode,minutes: number) => {
    if (startGate.current || gate.current || pendingOperation.current) return false;
    startGate.current=true;setBusy(true);
    try {
      const snapshot=await refresh();if (!snapshot || pendingOperation.current) return false;
      const switching=snapshot.current_session && snapshot.current_session.status!=='ended' && snapshot.current_task?.id!==task.id;
      if (switching && !window.confirm('结束本次专注并开始所选任务？已记录时间会保留。')) return false;
      const response=await get(`/goals/${encodeURIComponent(task.goal_id)}`);
      let goal=response.data;
      if (!goal || ['completed','cancelled'].includes(goal.status)) throw new Error('这个目标已结束，请选择其他任务');
      if (['draft','paused'].includes(goal.status)) {
        if (goal.status==='paused' && !window.confirm(`恢复搁置目标后开始学习？${goal.schedule?.kind==='schedule'?'同时恢复已设置的 AI 定时安排；可在目标的 AI 辅助视图取消安排。':''}`)) return false;
        const activated=await post(`/goals/${task.goal_id}/commands`,{operation:'activate',expected_revision:goal.revision});
        goal=activated.data;
      }
      const ok=await command({operation:switching?'switch':'start',task_id:task.id,expected_goal_revision:goal.revision,mode,duration_seconds:minutes*60,start_after_switch:Boolean(switching)});
      if (!ok && task.goal_status!=='active') setError('目标已开始学习，但本次专注尚未确认。请核对专注操作后重试。');
      if (ok) { setSetupTask(null);writeBrowserStorage('localStorage','texa:focus-preference:v3',JSON.stringify({mode,minutes})); }
      return ok;
    } catch (reason) {setError(reason instanceof Error ? reason.message : '开始学习失败');return false;}
    finally {startGate.current=false;setBusy(false);}
  },[command,refresh]);
  const invalidate=useCallback(()=>{epoch.current++;},[]);
  useEffect(() => {
    mounted.current=true; let cancelled=false;let timer:number|undefined;
    const poll=async () => {if (cancelled) return; if (!gate.current && !pendingOperation.current && (!isRemoteBrowser() || document.visibilityState==='visible')) await refresh(); if (!cancelled) timer=window.setTimeout(()=>void poll(),current.current?.status==='running'?5000:15000);};
    void poll();
    const resume=()=>{if (document.visibilityState==='visible' && !gate.current && !pendingOperation.current) void refresh();};
    window.addEventListener('online',resume);window.addEventListener('pageshow',resume);document.addEventListener('visibilitychange',resume);
    return ()=>{cancelled=true;mounted.current=false;invalidate();clearTimeout(timer);window.removeEventListener('online',resume);window.removeEventListener('pageshow',resume);document.removeEventListener('visibilitychange',resume);};
  },[refresh,invalidate]);
  useEffect(()=>{const timer=window.setInterval(()=>setProjection(projectFocus(pendingOperation.current&&current.current?{...current.current,status:'paused'}:current.current,received.current,performance.now())),1000);return ()=>clearInterval(timer);},[]);
  useEffect(()=>window.kaoyanDesktop?.onFocusPower?.(()=>{void (async()=>{if(pendingOperation.current)await reconcile();if(current.current?.status==='running')await command({operation:'pause',reason:'suspend'});else await refresh();})();}),[command,refresh,reconcile]);
  return <FocusContext.Provider value={{data,busy,error,pending,elapsed:projection.elapsed,remaining:projection.remaining,refresh,command,reconcile,setupTask,prepareStart,startTask,selectTask}}>{children}</FocusContext.Provider>;
}
