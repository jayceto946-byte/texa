import FocusBar from './FocusBar';
import { useState } from 'react';
import { useFocus } from './FocusContext';
export default function FocusPanel({ goalId, criteria }: {
    goalId: string;
    criteria: Array<{
        id: string;
        description?: string;
    }>;
}) {
    const focus = useFocus();
    const [title, setTitle] = useState(''), [minutes, setMinutes] = useState(25);
    const tasks = focus.data?.tasks.filter(item => item.goal_id === goalId) || [];
    return <section className="focus-task-panel"><h3>番茄任务</h3><FocusBar /><p>选择明确的学习内容与时间。时间到后，由你确认任务是否完成。</p><form onSubmit={event => { event.preventDefault(); void focus.command({ operation: 'create', goal_id: goalId, title: title.trim(), content: title.trim(), duration_seconds: minutes * 60 }); }}><label>任务内容<input value={title} onChange={e => setTitle(e.target.value)} maxLength={200} required placeholder="例如：阅读偏导定义并完成一道已有例题"/></label><label>专注分钟<input type="number" min={1} max={120} value={minutes} onChange={e => setMinutes(Number(e.target.value))}/></label><button type="submit" disabled={!focus.data || focus.busy || focus.pending || !title.trim()}>添加任务</button></form>{criteria.length > 0 && <details><summary>从已确认的完成条件选择任务</summary>{criteria.map(item => <button key={item.id} type="button" onClick={() => setTitle(item.description || '')}>{item.description}</button>)}</details>}{tasks.map(task => <div className="focus-task-row" key={task.id}><div><strong>{task.title}</strong><span>{task.duration_seconds / 60}分钟 · {task.status === 'completed' ? '已完成' : task.status === 'in_progress' ? '已开始' : '待开始'}</span></div><button type="button" disabled={focus.busy || focus.pending || task.status === 'completed'} onClick={() => void focus.command({ operation: 'start', task_id: task.id })}>{focus.data?.current_task?.id === task.id && focus.data.status === 'running' ? '计时中' : '开始计时'}</button></div>)}{!tasks.length && focus.data && <p>尚未添加番茄任务，可手动填写或从完成条件选择。</p>}{focus.error && <p role="alert">{focus.error}</p>}{focus.pending ? <button type="button" disabled={focus.busy} onClick={() => void focus.reconcile()}>核对未确认操作</button> : focus.error && <button type="button" onClick={() => void focus.refresh()}>重新读取专注状态</button>}</section>;
}
