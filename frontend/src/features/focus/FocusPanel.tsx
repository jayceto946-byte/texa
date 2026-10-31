import Selector from '../../components/ui/Selector';
import { TexaEdit, TexaDelete } from '../../components/icons';
import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Check, Play, Plus } from 'lucide-react';
import { focusDuration, type FocusTask } from './FocusContext';
import { useTaskQueue } from './hooks/useTaskQueue';
import { focusPreference } from './preferences';
export default function FocusPanel({goalId,criteria,focusNewTask=false}: {goalId:string;criteria:Array<{id:string;description?:string}>;focusNewTask?:boolean}) {
  const {tasks,next,error,loading,reload,focus,pageOffset,taskId}=useTaskQueue(goalId);
  const rowRoot=useRef<HTMLElement>(null);
  const [title,setTitle]=useState(''),[splitting,setSplitting]=useState(false),[criterion,setCriterion]=useState(criteria[0]?.id || ''),[actions,setActions]=useState(['']);
  const [editing,setEditing]=useState<FocusTask|null>(null),[editTitle,setEditTitle]=useState(''),[completedOpen,setCompletedOpen]=useState(false);
  const [undo,setUndo]=useState<{id:string}|null>(null),[saved,setSaved]=useState('');
  useEffect(()=>{if(!undo)return;const timer=window.setTimeout(()=>setUndo(null),8000);return()=>clearTimeout(timer);},[undo]);
  const pending=tasks.filter(task=>task.status!=='completed'),completed=tasks.filter(task=>task.status==='completed');
  useEffect(()=>{if(tasks.some(task=>task.id===taskId&&task.status==='completed'))setCompletedOpen(true);},[taskId,tasks]);
  useEffect(()=>{if(!taskId)return;const frame=requestAnimationFrame(()=>{const row=Array.from(rowRoot.current?.querySelectorAll<HTMLElement>('[data-task-id]')||[]).find(node=>node.dataset.taskId===taskId);row?.scrollIntoView({block:'nearest'});});return()=>cancelAnimationFrame(frame);},[taskId,tasks,completedOpen]);
  const disabled=focus.busy||focus.pending;
  const begin=(task:FocusTask)=>{const preference=focusPreference();if(preference)void focus.startTask(task,preference.mode,preference.minutes);else focus.prepareStart(task);};
  const complete=async(task:FocusTask)=>{if(await focus.command({operation:'complete',task_id:task.id})){setUndo({id:task.id});setSaved('操作已保存，专注记录已保留。');}};
  const reorder=async(index:number,delta:number)=>{const ordered=[...pending];[ordered[index],ordered[index+delta]]=[ordered[index+delta],ordered[index]];await focus.command({operation:'reorder',goal_id:goalId,task_ids:ordered.map(task=>task.id)});};
  const related=tasks.filter(task=>task.criterion_ids.includes(criterion)).length;
  return <section ref={rowRoot} className="study-task-panel" aria-label="学习任务">
    <div className="study-task-heading"><h3>任务</h3>{criteria.length>0&&<button className="app-ghost-button" onClick={()=>setSplitting(!splitting)}>从完成条件拆任务</button>}</div>
    {splitting&&<form className="criterion-task-editor" onSubmit={event=>{event.preventDefault();void focus.command({operation:'create_batch',goal_id:goalId,tasks:actions.filter(value=>value.trim()).map(value=>({title:value.trim(),criterion_ids:[criterion]}))}).then(ok=>{if(ok){setSplitting(false);setActions(['']);setSaved('任务已加入队列。');}});}}>
      <label>选择完成条件<Selector ariaLabel="选择完成条件" value={criterion} onChange={value => setCriterion(value)} options={criteria.map((item, index) => ({ value: item.id, label: item.description || `条件 ${index + 1}` }))}/></label>
      <p>{criteria.find(item=>item.id===criterion)?.description}</p><small>{related?`已有 ${related} 项相关任务 · `:''}把结果改写成具体行动，章节和题号由你填写。</small>
      {actions.map((value,index)=><label key={index}>行动 {index+1}<input className="app-field" value={value} required maxLength={200} placeholder="例如：阅读指定章节并整理定义" onChange={event=>setActions(previous=>previous.map((item,i)=>i===index?event.target.value:item))}/></label>)}
      <div className="focus-actions">{['阅读','整理','练习'].map(word=><button key={word} type="button" className="app-ghost-button" onClick={()=>setActions(previous=>previous.map((value,index)=>index===previous.length-1?`${word} ${value}`:value))}>{word}</button>)}<button type="button" className="app-ghost-button" disabled={actions.length>=20} onClick={()=>setActions([...actions,''])}>再加一项</button><button className="app-primary-button" disabled={disabled||!criterion||!actions.every(value=>value.trim())}>添加 {actions.length} 项任务</button></div>
    </form>}
    {loading&&!tasks.length?<p className="goals-muted" role="status">正在读取任务…</p>:!pending.length&&<p className="goals-muted">{completed.length?'任务已全部完成，检查目标完成条件。':'添加第一项具体任务。'}</p>}
    <div className="study-task-rows">{pending.map((task,index)=>{
      const current=focus.data?.current_task?.id===task.id,active=current&&focus.data?.current_session?.status!=='ended'&&Boolean(focus.data?.current_session);
      return <div key={task.id} className="study-task-row" data-current={current} data-task-id={task.id}>
        <input type="checkbox" aria-label={`完成任务：${task.title}`} disabled={disabled} checked={false} onChange={()=>void complete(task)}/>
        <div className="study-task-copy"><strong>{task.title}</strong><span>{current?`当前 · ${active?focus.data?.status==='running'?'专注中':'已暂停':'待开始'} · `:''}累计 {focusDuration(task.active_ms)}{task.legacy_elapsed_ms>0?' · 含旧版累计':''}</span></div>
        <div className="study-task-tools"><button className="app-icon-button" disabled={disabled} aria-label={`编辑任务：${task.title}`} onClick={()=>{setEditing(task);setEditTitle(task.title);}}><TexaEdit size={14}/></button><button className="app-icon-button" disabled={disabled||index===0||next!==null||pageOffset>0} aria-label={`上移任务：${task.title}`} onClick={()=>void reorder(index,-1)}><ArrowUp size={14}/></button><button className="app-icon-button" disabled={disabled||index===pending.length-1||next!==null||pageOffset>0} aria-label={`下移任务：${task.title}`} onClick={()=>void reorder(index,1)}><ArrowDown size={14}/></button></div>
        <button className="app-secondary-button" disabled={disabled} onClick={()=>active?focus.prepareStart(task):begin(task)}><Play size={13}/>{active?'控制':task.goal_status==='draft'?'开始学习':task.goal_status==='paused'?'恢复并开始':'开始专注'}</button>
      </div>;
    })}</div>
    <form className="study-task-add" onSubmit={event=>{event.preventDefault();void focus.command({operation:'create',goal_id:goalId,title:title.trim()}).then(ok=>{if(ok){setTitle('');setSaved('任务已加入队列。');}});}}><input autoFocus={focusNewTask} className="app-field" aria-label="添加一项具体任务" placeholder="添加一项具体任务…" value={title} maxLength={200} onChange={event=>setTitle(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&event.nativeEvent.isComposing)event.preventDefault();}}/><button className="app-secondary-button" disabled={disabled||!title.trim()} aria-label="添加任务"><Plus size={15}/></button></form>
    {title.trim()&&tasks.some(task=>task.title===title.trim())&&<p className="goals-muted">队列中已有同名任务，仍可添加。</p>}
    {editing&&<form className="study-task-edit" onSubmit={event=>{event.preventDefault();void focus.command({operation:'update',task_id:editing.id,title:editTitle,content:editing.content,criterion_ids:editing.criterion_ids}).then(ok=>{if(ok)setEditing(null);});}}><label>任务标题<input autoFocus className="app-field" required maxLength={200} value={editTitle} onChange={event=>setEditTitle(event.target.value)}/></label><div className="focus-actions"><button className="app-primary-button" disabled={disabled}>保存修改</button><button className="app-ghost-button" type="button" onClick={()=>setEditing(null)}>取消</button><button className="app-ghost-button" type="button" disabled={disabled} onClick={()=>{if(window.confirm('移除此任务？已记录专注时间与历史会保留；当前专注会结束。'))void focus.command({operation:'delete',task_id:editing.id}).then(ok=>{if(ok)setEditing(null);});}}><TexaDelete size={14}/>移除任务</button></div></form>}
    {!!completed.length&&<details open={completedOpen} onToggle={event=>setCompletedOpen(event.currentTarget.open)} className="study-task-completed"><summary>已完成 {completed.length}</summary>{completed.map(task=><div className="study-task-row" key={task.id} data-task-id={task.id}><Check size={15}/><div className="study-task-copy"><strong>{task.title}</strong><span>累计 {focusDuration(task.active_ms)}</span></div><button className="app-ghost-button" disabled={disabled} onClick={()=>void focus.command({operation:'reopen',task_id:task.id})}>撤销完成</button></div>)}</details>}
    {pageOffset>0&&<button className="app-ghost-button" disabled={loading} onClick={()=>void reload(false,false)}>读取前面的任务</button>}
    {next!==null&&<button className="app-ghost-button" disabled={loading} onClick={()=>void reload(true)}>读取更多任务</button>}
    {saved&&<p role="status" className="goals-muted">{saved}{undo&&<button className="app-ghost-button" disabled={disabled} onClick={()=>void focus.command({operation:'reopen',task_id:undo.id}).then(ok=>{if(ok){setUndo(null);setSaved('已恢复为待办，专注记录保留。');}})}>撤销完成</button>}</p>}
    {error&&<p role="alert">{error}<button className="app-ghost-button" onClick={()=>void reload()}>重新读取</button></p>}
  </section>;
}
