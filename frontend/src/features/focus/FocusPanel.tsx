import { useState } from 'react';
import { Check, Play, Plus, Timer } from 'lucide-react';
import FocusBar from './FocusBar';
import { useFocus } from './FocusContext';
export default function FocusPanel({ goalId, criteria }: {goalId: string; criteria: Array<{id: string; description?: string}>}) {
  const focus = useFocus();
  const [title, setTitle] = useState('');
  const [minutes, setMinutes] = useState(25);
  const [adding, setAdding] = useState(false);
  const tasks = focus.data?.tasks.filter(item => item.goal_id === goalId) || [];
  const completed = tasks.filter(item => item.status === 'completed').length;
  const current = focus.data?.current_task?.goal_id === goalId;
  return <section className="focus-task-panel" aria-label="番茄任务">
    <div className="focus-panel-heading"><div><h3><Timer size={18}/>番茄任务</h3><p className="goals-muted">一次只做一件事，完成后由你记录。</p></div><span className="focus-task-count">{completed} / {tasks.length} 已完成</span></div>
    {current && <FocusBar expanded/>}
    <div className="focus-task-list">{tasks.map((task,index) => {
      const selected = focus.data?.current_task?.id === task.id;
      return <div className="focus-task-row" data-current={selected} data-completed={task.status === 'completed'} key={task.id}>
        <span className="focus-task-number">{task.status === 'completed' ? <Check size={16}/> : String(index+1).padStart(2,'0')}</span>
        <div><strong>{task.title}</strong><span>{task.duration_seconds / 60} 分钟{task.status === 'completed' ? ' · 已完成' : selected ? ' · 当前任务' : ''}</span></div>
        {task.status !== 'completed' && <button className="app-secondary-button" type="button" disabled={focus.busy || focus.pending || (selected && focus.data?.status === 'running')} onClick={() => void focus.command({ operation: 'start', task_id: task.id })}><Play size={14}/>{selected && focus.data?.status === 'running' ? '专注中' : task.elapsed_seconds ? '继续' : '开始'}</button>}
      </div>;
    })}</div>
    {!tasks.length && focus.data && <div className="focus-task-empty"><Timer size={28}/><p>把目标拆成一件可以开始的任务</p><span>写下学习内容，给它一段专注时间。</span></div>}
    {!adding ? <button className="app-ghost-button focus-add-task" onClick={() => setAdding(true)}><Plus size={16}/>添加番茄任务</button> : <form className="focus-task-form" onSubmit={event => {event.preventDefault(); void focus.command({operation:'create',goal_id:goalId,title:title.trim(),content:title.trim(),duration_seconds:minutes*60});}}>
      <label>这段时间做什么<input autoFocus className="app-field" value={title} onChange={e=>setTitle(e.target.value)} maxLength={200} required placeholder="例如：读懂偏导定义，完成一道例题"/></label>
      {criteria.length > 0 && <label className="focus-criteria-pick">使用目标完成条件<select className="app-field" value="" onChange={e=>setTitle(e.target.value)}><option value="">选择一项，修改为具体任务</option>{criteria.map(item=><option key={item.id} value={item.description}>{item.description}</option>)}</select></label>}
      <div className="focus-form-footer"><label>专注时长<span><input className="app-field" type="number" min={1} max={120} value={minutes} onChange={e=>setMinutes(Number(e.target.value))}/> 分钟</span></label><div><button type="button" className="app-ghost-button" onClick={()=>setAdding(false)}>收起</button><button className="app-primary-button" type="submit" disabled={!focus.data || focus.busy || focus.pending || !title.trim()}>保存任务</button></div></div>
    </form>}
    {focus.error && <p role="alert" className="goal-error">{focus.error}</p>}
    {focus.pending ? <button className="app-secondary-button" disabled={focus.busy} onClick={()=>void focus.reconcile()}>核对未确认操作</button> : focus.error && <button className="app-ghost-button" onClick={()=>void focus.refresh()}>重新读取专注状态</button>}
  </section>;
}
