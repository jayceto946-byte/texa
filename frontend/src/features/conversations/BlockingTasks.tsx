import { useRef, useState } from 'react';
import { apiFetch } from '../../api/client';
import { useChatContext } from '../../contexts/ChatContext';
import type { BlockingConversationTask } from './api';

export default function BlockingTasks({ tasks, onChanged }: { tasks: BlockingConversationTask[]; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const operation = useRef<{ key: string; id: string } | null>(null);
  const { updateMessageByTaskId } = useChatContext();
  const finish = async (task: BlockingConversationTask) => {
    const key = `${task.id}:${task.run_id}:${task.revision}`;
    if (operation.current?.key !== key) operation.current = { key, id: crypto.randomUUID() };
    setBusy(true); setError('');
    try {
      const response = await apiFetch(`/chat/tasks/${encodeURIComponent(task.id)}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_id: operation.current.id, expected_run_id: task.run_id, expected_revision: task.revision }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.message || payload.detail || '未能结束任务');
      // Refresh the existing card rather than leaving a stale resume action.
      const current = payload.learning_task;
      updateMessageByTaskId(task.id, message => ({ ...message, learningTask: current }));
      operation.current = null;
      onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '未能结束任务'); }
    finally { setBusy(false); }
  };
  return <div className="conversation-blocking-tasks">{tasks.map((task, i) => <div key={task.id}><span>任务 {i + 1} · {({ running: '正在运行', interrupted: '已停止，可继续', waiting_for_input: '等待补充材料', waiting_for_confirmation: '等待确认', waiting_for_approval: '等待确认', paused: '已暂停' } as Record<string, string>)[task.status] || '尚未完成'}</span>{task.can_cancel && <button className="app-ghost-button" disabled={busy} onClick={() => void finish(task)}>结束未完成任务</button>}</div>)}{tasks.some(task => task.can_cancel) && <p>结束后不再继续此任务，已保存的内容会保留。</p>}{error && <p role="alert">{error}</p>}</div>;
}
