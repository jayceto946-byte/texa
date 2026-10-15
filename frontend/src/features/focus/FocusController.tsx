import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Check, ChevronUp, Pause, Play, Timer, X } from 'lucide-react';
import Dialog from '../../components/ui/Dialog';
import { panelPlacement } from './panelPlacement';
import { completionTransition } from './controllerState';
import { get } from '../../api/client';
import { focusDuration, focusTime, useFocus, type FocusMode, type FocusTask } from './FocusContext';
import { focusPreference } from './preferences';
export default function FocusController() {
  const focus=useFocus(),navigate=useNavigate(),location=useLocation();
  const [placement,setPlacement]=useState({sheet:false,bottom:60,maxHeight:420});
  const [open,setOpen]=useState(false),[resting,setResting]=useState(false),[choosing,setChoosing]=useState(false),[otherGoals,setOtherGoals]=useState(false);
  const [choices,setChoices]=useState<FocusTask[]>([]),[nextOffset,setNextOffset]=useState<number|null>(null),[choiceError,setChoiceError]=useState('');
  const preference=focusPreference();
  const [mode,setMode]=useState<FocusMode>(preference?.mode || 'countdown'),[minutes,setMinutes]=useState(preference?.minutes || 25);
  const tray=useRef<HTMLDivElement>(null),toggle=useRef<HTMLButtonElement>(null),returnFocus=useRef<HTMLElement|null>(null),lastSession=useRef(''),lastStatus=useRef('');
  const [announcement,setAnnouncement]=useState('');const announcedOvertime=useRef(''),lastCompletedTask=useRef('');
  const task=focus.setupTask || focus.data?.current_task;
  const session=focus.setupTask&&focus.setupTask.id!==focus.data?.current_task?.id?null:focus.data?.current_session;
  const active=session&&session.status!=='ended';const running=active&&focus.data?.status==='running';
  const done=task?.status==='completed'&&!focus.pending;const over=running&&session?.target_seconds!=null&&focus.remaining===0;
  const disabled=focus.busy||focus.pending;
  const close=()=>{setOpen(false);setChoosing(false);focus.prepareStart(null);if(returnFocus.current?.isConnected&&!returnFocus.current.closest('[hidden]'))returnFocus.current.focus();else toggle.current?.focus();};
  useEffect(()=>{
    if (focus.setupTask) {returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;setResting(false);setOpen(true);}
  },[focus.setupTask]);
  useEffect(()=>{
    const id=focus.data?.current_session?.id||'',status=focus.data?.status||'';
    if(id!==lastSession.current || status!==lastStatus.current){setAnnouncement(status==='running'?'专注已开始':status==='paused'?'计时已暂停':status==='finished'?'本次专注已保存':'');lastSession.current=id;lastStatus.current=status;}
    const completion=completionTransition(lastCompletedTask.current,task,focus.pending);
    lastCompletedTask.current=completion.identity;
    if(completion.reveal&&!resting)setOpen(true);
  },[focus.data?.current_session?.id,focus.data?.status,done,resting,task,focus.pending]);
  useEffect(()=>{if(over&&session&&announcedOvertime.current!==session.id){announcedOvertime.current=session.id;setAnnouncement('时间到，可以继续学习，实际时间仍在记录。');}},[over,session]);
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{if(tray.current&&!tray.current.contains(event.target as Node)&&!(event.target as HTMLElement).closest('.focus-sheet'))close();};
    const keyboard=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!(event.target as HTMLElement)?.closest('[aria-modal="true"]')){event.preventDefault();close();}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',keyboard);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',keyboard);};
  });
  useLayoutEffect(()=>{
    if(!open||!tray.current)return;
    const container=tray.current.closest('.workspace-main');
    const activeRoute=container?.querySelector('.persistent-route-panel:not([hidden])');
    const observed=new Set<HTMLElement>();
    const update=()=>{
      const rect=tray.current?.getBoundingClientRect(),main=container?.getBoundingClientRect();
      if(!rect||!main)return;
      const header=activeRoute?.querySelector('.learning-workspace-header,.goals-header,.app-page-header')?.getBoundingClientRect();
      const blockers=Array.from(activeRoute?.querySelectorAll<HTMLElement>('.chat-composer,.review-session-actions,.exercise-practice-actions')||[]);
      blockers.forEach(node=>{if(!observed.has(node)){observed.add(node);observer.observe(node);}});
      const visible=blockers.map(node=>node.getBoundingClientRect()).filter(value=>value.height>0&&value.bottom>main.top&&value.top<rect.top);
      const next=panelPlacement({width:window.innerWidth,mainWidth:main.width,contentTop:header?.bottom||main.top,trayBottom:rect.bottom,trayHeight:rect.height,blockerTop:visible.length?Math.min(...visible.map(value=>value.top)):null});
      setPlacement(previous=>previous.sheet===next.sheet&&previous.bottom===next.bottom&&previous.maxHeight===next.maxHeight?previous:next);
    };
    const observer=new ResizeObserver(update);
    if(container)observer.observe(container);
    // Lazy routes can add their composer after the controller has opened.
    const contentObserver=new MutationObserver(update);
    if(activeRoute)contentObserver.observe(activeRoute,{subtree:true,childList:true});
    window.addEventListener('resize',update);activeRoute?.addEventListener('scroll',update,true);update();
    return()=>{observer.disconnect();contentObserver.disconnect();window.removeEventListener('resize',update);activeRoute?.removeEventListener('scroll',update,true);};
  },[open,location.pathname,task?.id]);
  const loadChoices=async(offset=0)=>{try{const response=await get(`/focus?task_status=pending&offset=${offset}${!otherGoals&&task?`&goal_id=${encodeURIComponent(task.goal_id)}`:''}`);setChoices(previous=>offset?[...previous,...response.data.tasks]:response.data.tasks);setNextOffset(response.data.next_offset);setChoiceError('');}catch{setChoiceError('任务队列暂不可读取，请重试。');}};
  useEffect(()=>{if(choosing)void loadChoices();},[choosing,otherGoals,task?.goal_id,focus.data?.revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const begin=(value:FocusTask)=>{const recent=focusPreference();if(recent)void focus.startTask(value,recent.mode,recent.minutes);else focus.prepareStart(value);};
  if(!task&&!focus.error&&!focus.pending&&!focus.setupTask)return null;
  if(resting&&!active&&!focus.error&&!focus.pending&&!focus.setupTask)return null;
  const number=active?over?`+${focusTime(Math.max(0,focus.elapsed-(session?.target_seconds||0)))}`:session?.mode==='stopwatch'?focusTime(focus.elapsed):focusTime(focus.remaining||0):mode==='stopwatch'?'00:00':focusTime(minutes*60);
  const status=focus.pending?'保存结果待核对':done?'已完成':active?over?focus.data?.reason==='overtime_acknowledged'?'已继续':'时间到':running?'专注中':'已暂停':session?'本次已结束':'待开始';
  const panel=<section className="focus-mini-panel" style={placement.sheet?undefined:{bottom:placement.bottom,maxHeight:placement.maxHeight}} aria-label="当前专注控制面板">
      <header><span>{task?.goal_title || '专注'}</span><button className="app-ghost-button" onClick={()=>{close();navigate(task?`/goals?goal=${encodeURIComponent(task.goal_id)}&task=${encodeURIComponent(task.id)}`:'/goals');}}>任务管理</button><button className="app-icon-button" aria-label="关闭专注面板" onClick={close}><X size={14}/></button></header>
      {task&&<h3 title={task.title}>{done&&<Check size={16}/>}<span>{task.title}</span></h3>}
      {focus.error&&<p className="focus-sync-error" role="alert">{focus.error}</p>}
      {focus.pending&&<button className="app-primary-button" disabled={focus.busy} onClick={()=>void focus.reconcile()}>核对未确认操作</button>}
      {!focus.pending&&focus.error&&<button className="app-ghost-button" onClick={()=>void focus.refresh()}>重新读取状态</button>}
      {focus.data?.reason==='interrupted'&&<p className="focus-sync-error">上次专注中断，已记录至 {focus.data.checkpoint_at?new Date(focus.data.checkpoint_at*1000).toLocaleTimeString(): '最后检查点'}。未确认尾段未补计。</p>}
      {focus.data?.reason==='legacy_interrupted'&&<p className="goals-muted">保留旧版累计，未包含旧时段未结算部分。</p>}
      {task&&!choosing&&<>{active?<><p className="focus-mode-label">{session.mode==='stopwatch'?'正计时':`倒计时 · ${(session.target_seconds||0)/60} 分钟`} · {status}</p><div className="focus-number">{number}</div><p className="focus-session-total">本次 {focusDuration(focus.elapsed*1000)} · 任务累计 {focusDuration(task.active_ms+(focus.elapsed*1000-(focus.data?.active_ms||0)))}</p><div className="focus-actions focus-primary-actions">{over&&focus.data?.reason!=='overtime_acknowledged'&&<button className="app-primary-button" disabled={disabled} onClick={()=>void focus.command({operation:'acknowledge'})}>继续学习</button>}<button className={running?'app-secondary-button':'app-primary-button'} disabled={disabled} onClick={()=>running?void focus.command({operation:'pause'}):void focus.startTask(task,session.mode,(session.target_seconds||1500)/60)}>{running?'暂停计时':'继续计时'}</button><button className="app-secondary-button" disabled={disabled} onClick={()=>void focus.command({operation:'complete',task_id:task.id})}>完成任务</button></div><div className="focus-actions"><button className="app-ghost-button" disabled={disabled} onClick={()=>void focus.command({operation:'finish'})}>结束本次</button><button className="app-ghost-button" disabled={disabled} onClick={()=>setChoosing(true)}>切换任务</button></div></>:done?<><button className="app-ghost-button" disabled={disabled} onClick={()=>void focus.command({operation:'reopen',task_id:task.id})}>撤销完成</button><p className="focus-session-total">已完成 · 本次 {focusDuration(session?.active_ms || 0)} · 任务累计 {focusDuration(task.active_ms)}</p>{focus.data?.next_task?<><p>下一项：{focus.data.next_task.title}</p><button className="app-primary-button" disabled={disabled} onClick={()=>begin(focus.data!.next_task!)}>开始下一项</button></>:<p>本目标暂无待办，检查目标完成条件。</p>}<div className="focus-actions"><button className="app-ghost-button" onClick={()=>setChoosing(true)}>选择其他任务</button><button className="app-ghost-button" onClick={()=>{close();setResting(true);}}>先休息</button></div></>:<><p className="focus-mode-label">{session?'本次已结束，投入已保存。开始新一段会创建新时段。':'选择计时方式后开始。'}</p><div className="focus-mode-options"><button aria-pressed={mode==='countdown'} className="app-secondary-button" onClick={()=>setMode('countdown')}>倒计时</button><button aria-pressed={mode==='stopwatch'} className="app-secondary-button" onClick={()=>setMode('stopwatch')}>正计时</button></div>{mode==='countdown'&&<div className="focus-duration-options">{[25,50].map(value=><button key={value} aria-pressed={minutes===value} className="app-ghost-button" onClick={()=>setMinutes(value)}>{value}分</button>)}<label>自定义<input className="app-field" aria-label="专注分钟" type="number" min={1} max={120} value={minutes} onChange={event=>setMinutes(Number(event.target.value))}/> 分</label></div>}<div className="focus-number">{number}</div><div className="focus-actions focus-primary-actions"><button className="app-primary-button" disabled={disabled||!Number.isInteger(minutes)||minutes<1||minutes>120} onClick={()=>void focus.startTask(task,mode,minutes)}>{task.goal_status==='draft'?'开始学习':task.goal_status==='paused'?'恢复目标并开始':session?'开始新一段':'开始专注'}</button><button className="app-secondary-button" disabled={disabled} onClick={()=>void focus.command({operation:'complete',task_id:task.id})}>完成任务</button></div><div className="focus-actions"><button className="app-ghost-button" onClick={()=>setChoosing(true)}>选择其他任务</button><button className="app-ghost-button" onClick={()=>{close();setResting(true);}}>先休息</button></div></>}</>}
      {choosing&&<div className="focus-task-chooser"><div className="focus-actions"><button className="app-ghost-button" onClick={()=>setChoosing(false)}>返回控制</button><button className="app-secondary-button" aria-pressed={otherGoals} onClick={()=>setOtherGoals(!otherGoals)}>{otherGoals?'全部目标':'其他目标'}</button></div><p className="goals-muted">选择只切换任务，计时由你开始。</p><div className="focus-task-choices">{choices.map(item=><button className="app-ghost-button" key={item.id} disabled={disabled} onClick={()=>void focus.selectTask(item).then(ok=>{if(ok){setChoosing(false);focus.prepareStart(null);}})}><span>{item.title}</span><small>{item.goal_title}</small></button>)}</div>{nextOffset!==null&&<button className="app-ghost-button" onClick={()=>void loadChoices(nextOffset)}>更多任务</button>}{choiceError&&<p role="alert">{choiceError}<button className="app-ghost-button" onClick={()=>void loadChoices()}>重试</button></p>}</div>}
    </section>;
  return <div className="focus-tray" ref={tray} aria-label="专注控制器">
    <div className="focus-docked"><Timer size={15}/><strong title={task?.title}>{task?.title || '专注操作尚未确认'}</strong><span className="focus-docked-time">{focus.pending?'保存结果待核对':active?(over?status:!running?'已暂停':session?.mode==='stopwatch'?'已专注':'剩余'):status} {task&&(done?focusDuration(task.active_ms):!active&&session?focusDuration(session.active_ms):number)}</span>{active&&<button className="app-icon-button" disabled={disabled} aria-label={running?'暂停当前专注':'继续当前专注'} onClick={()=>running?void focus.command({operation:'pause'}):task&&void focus.startTask(task,session.mode,(session.target_seconds||1500)/60)}>{running?<Pause size={15}/>:<Play size={15}/>}</button>}<button ref={toggle} className="app-icon-button" aria-label={open?'收起专注面板':'展开专注面板'} aria-expanded={open} onClick={()=>{returnFocus.current=toggle.current;setOpen(!open);}}><ChevronUp size={15} style={{transform:open?'rotate(180deg)':undefined}}/></button></div>
    <p className="sr-only" role="status">{announcement}</p>
    {placement.sheet?<Dialog open={open} title="专注控制" onClose={close} dismissOnBackdrop className="focus-sheet">{panel}</Dialog>:open&&panel}
  </div>;
}
