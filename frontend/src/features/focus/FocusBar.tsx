import { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Pause, Play, Timer } from 'lucide-react';
import { useFocus, focusTime } from './FocusContext';
export default function FocusBar({expanded = false}: {expanded?: boolean}) {
  const focus = useFocus();
  const [open, setOpen] = useState(expanded);
  const task = focus.data?.current_task;
  if (!task) return null;
  const running = focus.data?.status === 'running' && focus.remaining > 0;
  const done = task.status === 'completed';
  const disabled = focus.busy || focus.pending;
  return <section className={`focus-bar ${expanded ? 'focus-timer-card' : ''}`} aria-label="当前专注任务">
    <div className="focus-bar-summary"><Timer size={16}/><strong>{task.title}</strong><span className="focus-clock" aria-label="剩余专注时间">{focusTime(focus.remaining)}</span><button className="app-secondary-button" type="button" disabled={disabled || focus.remaining === 0 || done} onClick={()=>void focus.command({operation:running?'pause':'start',task_id:task.id})}>{running ? <Pause size={14}/> : <Play size={14}/>} {done?'已完成':running?'暂停':focus.remaining===0?'时间到':'开始'}</button>{!expanded && <button className="app-icon-button" type="button" aria-label={open?'收起任务':'展开任务'} aria-expanded={open} onClick={()=>setOpen(!open)}>{open?<ChevronUp size={16}/>:<ChevronDown size={16}/>}</button>}</div>
    {open && <div className="focus-bar-detail"><p className="focus-status" role="status">{done?'任务已完成':focus.remaining===0?'时间到，确认一下完成情况':running?'正在专注':'已暂停，可以随时继续'}</p><div className="focus-detail-actions"><label className="sr-only" htmlFor={expanded?'goal-focus-switch':'chat-focus-switch'}>切换专注任务</label><select id={expanded?'goal-focus-switch':'chat-focus-switch'} className="app-field" value={task.id} disabled={disabled} onChange={e=>void focus.command({operation:'switch',task_id:e.target.value})}>{focus.data?.tasks.filter(item=>item.status!=='completed'||item.id===task.id).map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select><button className="app-secondary-button" disabled={disabled||done} onClick={()=>void focus.command({operation:'complete',task_id:task.id})}><Check size={14}/>标记完成</button><button className="app-ghost-button" disabled={disabled} onClick={()=>void focus.command({operation:'finish',task_id:task.id})}>结束计时</button></div></div>}
    {focus.error && <p role="alert">{focus.error}</p>}{focus.pending&&<button className="app-secondary-button" disabled={focus.busy} onClick={()=>void focus.reconcile()}>核对未确认操作</button>}
  </section>;
}
