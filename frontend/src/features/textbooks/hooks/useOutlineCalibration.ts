import { useEffect, useState } from 'react';
import { apiFetch } from '../../../api/client';

export type OutlineExample = { block_id: string; level: number; role: string };
export type OutlineCandidate = { block_id: string; text: string; page: number | null; chapter: string; level: number; role: string; family: string };
type Chapter = { title: string; page_number: number; subsections: { title: string; level: number; page: number; heading_block_id: string }[] };
type Outline = { base_version: string; candidates: OutlineCandidate[]; chapters: Chapter[]; recovery: { examples: OutlineExample[]; max_depth: number; toc: { accepted: boolean; explicit?: boolean; matched: number; entries: number }[] } };
type Job = { id: string; status: string; message: string; progress: number };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await apiFetch(path, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
  const payload = await response.json();
  if (!response.ok || !payload.success) throw new Error(payload.detail || payload.message || '目录处理失败');
  return payload.data;
}

export function useOutlineCalibration(bookName: string) {
  const root = `/books/${encodeURIComponent(bookName)}/outline`;
  const storageKey = `texa:outline-job:${bookName}`;
  const [source, setSource] = useState<Outline | null>(null);
  const [proposal, setProposal] = useState<Outline | null>(null);
  const [examples, setExamples] = useState<OutlineExample[]>([]);
  const [maxDepth, setMaxDepth] = useState(6);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState(() => localStorage.getItem(storageKey) || '');
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let active = true;
    request<Outline>(root).then(data => {
      if (!active) return;
      setSource(data); setExamples(data.recovery.examples); setMaxDepth(data.recovery.max_depth);
    }).catch(cause => { if (active) setError(String(cause.message || cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [root]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await request<Job>(`/books/outline-jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        setJob(next);
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(next.status)) {
          localStorage.removeItem(storageKey);
          if (next.status === 'completed') {
            const data = await request<Outline>(root);
            if (!active) return;
            setSource(data); setProposal(null);
            setExamples(data.recovery.examples); setMaxDepth(data.recovery.max_depth);
            window.dispatchEvent(new Event('books:changed'));
          } else setError(next.message);
          setJobId('');
        } else timer = setTimeout(poll, 1200);
      } catch (cause) {
        if (active) { setError(cause instanceof Error ? cause.message : String(cause)); timer = setTimeout(poll, 4000); }
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId, root, storageKey]);

  const changeExamples = (next: OutlineExample[]) => { setExamples(next); setProposal(null); setJob(null); };
  const changeDepth = (next: number) => { setMaxDepth(next); setProposal(null); setJob(null); };
  const body = () => ({ base_version: source?.base_version, examples, max_depth: maxDepth });
  const preview = async () => {
    setBusy(true); setError('');
    try { setProposal(await request<Outline>(`${root}/preview`, body())); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!proposal) return;
    setBusy(true); setError('');
    try {
      const next = await request<Job>(`${root}/apply`, body());
      localStorage.setItem(storageKey, next.id); setJob(next); setJobId(next.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  return { source, proposal, examples, maxDepth, loading, busy: busy || !!jobId, error, job,
    changeExamples, changeDepth, preview, apply };
}
