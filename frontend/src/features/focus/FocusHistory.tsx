import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { get } from '../../api/client';
import { focusDuration, useFocus, type FocusSession } from './FocusContext';
type HistorySession=FocusSession & {title:string;deleted_at:number|null};
const reasons:Record<string,string>={user_ended:'主动结束',task_completed:'任务完成',switched:'切换任务',task_deleted:'任务已移除',shutdown:'桌面退出',suspend:'系统休眠',interrupted:'意外中断',goal_paused:'目标搁置',goal_changed:'目标修改',goal_completed:'目标完成'};
export default function FocusHistory({goalId}:{goalId:string}) {
  const focus=useFocus(),location=useLocation();
  const [items,setItems]=useState<HistorySession[]>([]),[next,setNext]=useState<number|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const epoch=useRef(0);
  const load=async(offset=0)=>{const generation=++epoch.current;setLoading(true);try{const response=await get(`/focus/history?goal_id=${encodeURIComponent(goalId)}&offset=${offset}&timezone_name=${encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)}`);if(generation!==epoch.current)return;setItems(previous=>offset?[...previous,...response.data.sessions]:response.data.sessions);setNext(response.data.next_offset);setError('');}catch{if(generation===epoch.current)setError('专注记录暂不可读取，请重试。');}finally{if(generation===epoch.current)setLoading(false);}};
  useEffect(()=>{if(location.pathname==='/goals')void load();return()=>{epoch.current++;};},[goalId,focus.data?.revision,location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  return <section className="focus-history"><h3>专注记录</h3><p className="goals-muted">记录实际投入。结束时段不表示任务或目标完成。</p>{loading&&!items.length?<p role="status">正在读取记录…</p>:!items.length&&!error?<p className="goals-muted">尚无专注时段。旧版累计仍保留在任务中。</p>:null}{items.map(item=><div className="focus-history-row" key={item.id}><div><strong>{item.title}{item.deleted_at?' · 任务已移除':''}</strong><span>{new Date(item.started_at*1000).toLocaleString()} · {item.mode==='stopwatch'?'正计时':`倒计时 ${Math.floor((item.target_seconds||0)/60)}分`} · {item.status==='ended'?reasons[item.end_reason]||'本次已结束':item.status==='running'?'专注中':'已暂停'}</span></div><strong>{focusDuration(item.id===focus.data?.current_session?.id?focus.elapsed*1000:item.active_ms)}</strong></div>)}{next!==null&&<button disabled={loading} className="app-ghost-button" onClick={()=>void load(next)}>读取更多记录</button>}{error&&<p role="alert">{error}<button className="app-ghost-button" onClick={()=>void load()}>重试</button></p>}</section>;
}
