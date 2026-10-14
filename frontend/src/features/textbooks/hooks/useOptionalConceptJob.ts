import { useEffect, useState } from 'react';
import { get } from '../../../api/client';

type ConceptJobState = { id: string; status: string; error: string };
export function useOptionalConceptJob(jobId: string) {
  const [state, setState] = useState<ConceptJobState>({ id: '', status: '', error: '' });
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const result = await get(`/jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        if (!result.success) throw new Error('无法读取概念抽取状态');
        const status = result.data.status;
        setState({ id: jobId, status, error: '' });
        if (!['completed', 'failed', 'cancelled', 'interrupted'].includes(status)) timer = setTimeout(() => { void poll(); }, 2000);
      } catch {
        if (active) setState({ id: jobId, status: 'unknown', error: '概念抽取状态暂不可用；教材已导入完成。' });
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId]);
  return state.id === jobId ? state : { id: jobId, status: 'queued', error: '' };
}
