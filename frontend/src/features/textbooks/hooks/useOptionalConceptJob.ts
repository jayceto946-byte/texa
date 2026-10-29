import { useEffect, useState } from 'react';
import { get, post } from '../../../api/client';

export type ConceptJob = { id: string; status: string; progress: number; message: string; error?: string; result?: { concept_count?: number } };
const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted']);

export function useOptionalConceptJob(bookName: string, jobId = '') {
  const key = `${bookName}:${jobId}`;
  const [state, setState] = useState<{ key: string; job: ConceptJob | null; error: string; loaded: boolean }>({ key: '', job: null, error: '', loaded: false });
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!bookName) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await get(`/jobs?type=textbook_kg_enhancement&book_name=${encodeURIComponent(bookName)}&limit=1`);
        if (!result.success) throw new Error(result.message || '无法读取概念抽取状态');
        if (!active) return;
        const job: ConceptJob | null = result.data?.[0] || null;
        setState({ key, job, error: '', loaded: true });
        timer = setTimeout(() => { void poll(); }, job && !terminal.has(job.status) ? 2000 : 10000);
      } catch (cause) {
        if (!active) return;
        setState(current => ({ key, job: current.key === key ? current.job : null, loaded: true, error: cause instanceof Error ? cause.message : '无法读取概念抽取状态' }));
        timer = setTimeout(() => { void poll(); }, 4000);
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [bookName, key, revision]);
  const current = state.key === key ? state : { job: null, error: '', loaded: false };
  const perform = async (path: string, body: unknown = {}) => {
    setBusy(true);
    try {
      const result = await post(path, body);
      if (!result.success) throw new Error(result.message || '操作失败，请重试');
      setState({ key, job: result.data, error: '', loaded: true });
      setRevision(value => value + 1);
    } catch (cause) {
      setState(previous => ({ ...previous, key, error: cause instanceof Error ? cause.message : '操作失败，请重试' }));
    } finally { setBusy(false); }
  };
  return { ...current, busy,
    cancel: () => current.job && perform(`/jobs/${encodeURIComponent(current.job.id)}/cancel`),
    start: () => perform('/kg/enhance', { book_name: bookName, allow_external_llm: true }),
  };
}
