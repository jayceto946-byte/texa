import { useEffect, useState } from 'react';
import { getLearningTask } from '../../api/client';
import type { LearningTaskState } from '../../types';

type Effect = {
  id: string;
  status: 'pending' | 'completed';
  result?: { mistake_id?: string } | null;
};

export function learningEffects(task: LearningTaskState): Effect[] {
  const values = task.artifacts?.effects;
  if (!Array.isArray(values)) return [];
  return values.filter((value): value is Effect => Boolean(value && typeof value === 'object'
    && typeof value.id === 'string' && ['pending', 'completed'].includes(value.status)));
}

export default function LearningTaskEffects({ task }: { task: LearningTaskState }) {
  const [current, setCurrent] = useState(task);
  const [unavailable, setUnavailable] = useState(false);
  const pending = learningEffects(current).some((item) => item.status === 'pending');

  useEffect(() => {
    if (!pending) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let delay = 5000;
    const refresh = async () => {
      try {
        const next = await getLearningTask(task.id, controller.signal);
        if (controller.signal.aborted) return;
        if (next.id !== task.id || next.active_run_id !== task.active_run_id) return;
        setCurrent(next);
        setUnavailable(false);
        if (!learningEffects(next).some((item) => item.status === 'pending')) return;
      } catch {
        if (controller.signal.aborted) return;
        setUnavailable(true);
        delay = Math.min(30000, delay * 2);
      }
      timer = setTimeout(() => void refresh(), delay);
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [task.id, task.active_run_id, pending]);

  const items = learningEffects(current);
  if (!items.length) return null;
  const imported = items.some((item) => item.status === 'completed' && item.result?.mistake_id);
  // Feedback that finished without a visible import needs no persistent badge.
  if (!pending && !imported) return null;
  return (
    <p className="mt-3 text-xs leading-5 text-text-secondary" role="status">
      {pending
        ? unavailable ? '答案已保存，暂时无法读取学习记录的保存状态。连接恢复后自动更新。' : '答案已保存，学习记录待恢复。应用会自动重试。'
        : '已导入错题本。'}
    </p>
  );
}
