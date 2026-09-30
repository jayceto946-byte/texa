import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { resolveAgentAction } from '../../api/client';
import type { AgentPendingAction, LearningTaskState } from '../../types';

const labels: Record<string, string> = {
  add_mistake: '加入错题本',
  mark_concept_reviewed: '记录概念复习',
  create_practice_session: '创建练习会话',
  record_practice_result: '记录作答结果',
  update_mistake: '更新错题备注',
};

export default function LearningTaskActions({ initialTask, onResume, onTaskChange }: { initialTask: LearningTaskState; onResume?: (task: LearningTaskState) => void; onTaskChange?: (task: LearningTaskState) => void }) {
  const [task, setTask] = useState(initialTask);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { setTask(initialTask); }, [initialTask]);
  const actions = Array.isArray(task.artifacts?.pending_actions)
    ? task.artifacts.pending_actions as AgentPendingAction[]
    : [];

  const resolve = async (action: AgentPendingAction, decision: 'confirm' | 'reject') => {
    if (!action.action_id || busy) return;
    setBusy(action.action_id);
    setError('');
    try {
      const response = await resolveAgentAction(action.action_id, decision);
      if (response.learning_task) {
        setTask(response.learning_task);
        onTaskChange?.(response.learning_task);
        if (decision === 'confirm' && response.action.status === 'confirmed' && response.learning_task.resumable) onResume?.(response.learning_task);
      } else {
        setTask((current) => ({
          ...current,
          artifacts: {
            ...current.artifacts,
            pending_actions: actions.map((item) => item.action_id === response.action.action_id ? response.action : item),
          },
        }));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作未完成');
    } finally {
      setBusy('');
    }
  };

  if (!actions.length) return null;
  return (
    <section className="mt-3 border-l-2 border-accent pl-3" aria-label="待确认学习操作">
      <h3 className="text-sm font-semibold text-text-primary">学习记录操作</h3>
      <div className="mt-2 space-y-2">
        {actions.map((action) => {
          const pending = !action.status || action.status === 'pending';
          const allowed = action.allowed_actions || (pending ? ['confirm', 'reject'] : []);
          return (
            <div key={action.action_id || action.type} className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="text-text-primary">{labels[action.type] || action.type}</span>
              {action.status === 'expired' && <span className="text-text-secondary">已过期，不能确认</span>}
              {pending && <pre className="w-full whitespace-pre-wrap break-all text-text-secondary">{JSON.stringify(action.payload, null, 2)}</pre>}
              {allowed.length > 0 ? (
                <span className="flex items-center gap-1.5">
                  {allowed.includes('reject') && <button type="button" disabled={Boolean(busy)} onClick={() => void resolve(action, 'reject')} className="app-secondary-button disabled:opacity-50">
                    <X className="h-3.5 w-3.5" /> 暂不执行
                  </button>}
                  {allowed.includes('confirm') && <button type="button" disabled={Boolean(busy)} onClick={() => void resolve(action, 'confirm')} className="app-primary-button disabled:opacity-50">
                    <Check className="h-3.5 w-3.5" /> {busy === action.action_id ? '执行中…' : '确认执行'}
                  </button>}
                </span>
              ) : (
                <span className="text-text-secondary">{action.status === 'confirmed' || action.status === 'executed' ? '已执行' : action.status === 'rejected' ? '已取消' : action.status === 'expired' ? '已过期，请取消此操作' : action.status === 'unknown' ? '写入结果未知，需核对记录；不可再次执行' : action.status === 'executing' ? '正在执行' : '执行失败'}</span>
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="mt-2 text-xs text-[var(--danger)]">{error}</p>}
    </section>
  );
}
