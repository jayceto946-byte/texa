import { useState } from 'react';
import { post } from '../../../api/client';
import type { ExerciseRecord } from '../../../types';

export function useExerciseDeletion({ bookQuery, onDeleted }: {
  bookQuery: string;
  onDeleted: (ids: Set<string>, message: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<ExerciseRecord[]>([]);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  const request = (records: ExerciseRecord[]) => { setError(''); setPending(records); };
  const cancel = () => { if (!deleting) setPending([]); };
  const confirm = async () => {
    setDeleting(true); setError('');
    const ids = new Set(pending.map(record => record.id));
    try {
      const response = await post(`/exercises/delete${bookQuery}`, { exercise_ids: [...ids] });
      if (!response.success) throw new Error(response.message || '删除题目失败');
      setPending([]);
      await onDeleted(ids, response.message || `已删除 ${ids.size} 道题目`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setDeleting(false); }
  };
  return { pending, deleting, error, request, cancel, confirm };
}
