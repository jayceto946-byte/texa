import { useState } from 'react';
import { useFocus, focusTime } from './FocusContext';
export default function FocusBar() {
    const focus = useFocus();
    const [open, setOpen] = useState(false);
    const task = focus.data?.current_task;
    if (!task)
        return null;
    const running = focus.data?.status === 'running' && focus.remaining > 0;
    return <section className="focus-bar" aria-label="当前专注任务"><div className="focus-bar-summary"><strong>{task.title}</strong><span aria-label="剩余专注时间">{focusTime(focus.remaining)}</span><button type="button" disabled={focus.busy || focus.pending || focus.remaining === 0 || task.status === 'completed'} onClick={() => void focus.command({ operation: running ? 'pause' : 'start', task_id: task.id })}>{task.status === 'completed' ? '已完成' : running ? '暂停计时' : focus.remaining === 0 ? '时间到' : '继续计时'}</button><button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? '收起任务' : '展开任务'}</button></div>{open && <div className="focus-bar-detail"><p>{task.content || task.title}</p><p role="status">{task.status === 'completed' ? '任务已由你标记完成' : focus.remaining === 0 ? '本次时间已到，请确认任务完成情况' : running ? '专注计时中' : '计时已暂停'}；计时不会自动执行或完成学习任务。</p><select aria-label="切换专注任务" value={task.id} disabled={focus.busy || focus.pending} onChange={e => void focus.command({ operation: 'switch', task_id: e.target.value })}>{focus.data?.tasks.filter(item => item.status !== 'completed' || item.id === task.id).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button type="button" disabled={focus.busy || focus.pending || task.status === 'completed'} onClick={() => void focus.command({ operation: 'complete', task_id: task.id })}>标记任务完成</button><button type="button" disabled={focus.busy || focus.pending} onClick={() => void focus.command({ operation: 'finish', task_id: task.id })}>结束本次计时</button></div>}{focus.error && <p role="alert">{focus.error}</p>}{focus.pending && <button type="button" disabled={focus.busy} onClick={() => void focus.reconcile()}>核对未确认操作</button>}</section>;
}
