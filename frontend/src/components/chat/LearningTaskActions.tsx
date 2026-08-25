import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { resolveAgentAction } from '../../api/client';
import type { AgentPendingAction, LearningTaskState } from '../../types';

const labels: Record<string, string> = {
  add_mistake: '加入错题本',
  mark_concept_reviewed: '记录概念复习',
  create_practice_session: '创建练习会话',
};

export default function LearningTaskActions({ initialTask }: { initialTask: LearningTaskState }) {
  const [task, setTask] = useState(initialTask);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
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
      <h3 className="text-sm font-semibold text-text-primary">确认后才会写入学习记录</h3>
      <div className="mt-2 space-y-2">
        {actions.map((action) => {
          const pending = !action.status || action.status === 'pending';
          return (
            <div key={action.action_id || action.type} className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="text-text-primary">{labels[action.type] || action.type}</span>
              {pending ? (
                <span className="flex items-center gap-1.5">
                  <button type="button" disabled={Boolean(busy)} onClick={() => void resolve(action, 'reject')} className="app-secondary-button disabled:opacity-50">
                    <X className="h-3.5 w-3.5" /> 暂不执行
                  </button>
                  <button type="button" disabled={Boolean(busy)} onClick={() => void resolve(action, 'confirm')} className="app-primary-button disabled:opacity-50">
                    <Check className="h-3.5 w-3.5" /> {busy === action.action_id ? '执行中…' : '确认执行'}
                  </button>
                </span>
              ) : (
                <span className="text-text-secondary">{action.status === 'confirmed' ? '已执行' : action.status === 'rejected' ? '已取消' : '执行失败'}</span>
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="mt-2 text-xs text-[var(--danger)]">{error}</p>}
    </section>
  );
}
