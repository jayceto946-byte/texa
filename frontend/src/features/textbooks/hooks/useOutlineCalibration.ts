import { useEffect, useState } from 'react';
import { apiFetch } from '../../../api/client';

export type OutlineExample = { block_id: string; level: number; role: string };
export type OutlineEdit = { node_id: string; title: string; level: number; page: number; anchor_block_id?: string; created?: boolean; role: string };
export type OutlineCandidate = { block_id: string; text: string; page: number | null; chapter: string; level: number; role: string; family: string; visible: boolean; anchor_block_id?: string };
type Chapter = { title: string; page_number: number; end_page: number; subsections: { title: string; level: number; page: number; heading_block_id: string }[] };
export type Outline = { base_version: string; candidates: OutlineCandidate[]; chapters: Chapter[]; edits: OutlineEdit[]; page_count: number; recovery: { examples: OutlineExample[]; max_depth: number; toc: { accepted: boolean; matched: number; entries: number }[] } };
type Job = { id: string; status: string; message: string; progress: number };
export type SourceBlock = { block_id: string; text: string; block_type: string };

export async function outlineRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await apiFetch(path, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
  const payload = await response.json();
  if (!response.ok || !payload.success) throw new Error(payload.detail || payload.message || '目录处理失败');
  return payload.data;
}

export function useOutlineCalibration(bookName: string, importJobId?: string, onConfirmed?: (jobId: string) => void) {
  const root = importJobId ? `/books/import-jobs/${encodeURIComponent(importJobId)}/outline` : `/books/${encodeURIComponent(bookName)}/outline`;
  const storageKey = `texa:outline-job:${bookName}`;
  const [source, setSource] = useState<Outline | null>(null);
  const [proposal, setProposal] = useState<Outline | null>(null);
  const [examples, setExamples] = useState<OutlineExample[]>([]);
  const [edits, setEdits] = useState<OutlineEdit[]>([]);
  const [maxDepth, setMaxDepth] = useState(2);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [jobId, setJobId] = useState(() => importJobId ? '' : localStorage.getItem(storageKey) || '');
  const [job, setJob] = useState<Job | null>(null);
  const draftKey = source ? `texa:outline-draft:${root}:${source.base_version}` : '';

  useEffect(() => {
    let active = true;
    outlineRequest<Outline>(root).then(data => {
      if (!active) return;
      const saved = localStorage.getItem(`texa:outline-draft:${root}:${data.base_version}`);
      setSource(data); setExamples(data.recovery.examples); setMaxDepth(data.recovery.max_depth);
      setEdits(saved ? JSON.parse(saved) : data.edits || []);
      setError('');
    }).catch(cause => { if (active) setError(String(cause.message || cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [root, reload]);

  useEffect(() => { if (draftKey) localStorage.setItem(draftKey, JSON.stringify(edits)); }, [draftKey, edits]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await outlineRequest<Job>(`/books/outline-jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        setJob(next);
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(next.status)) {
          localStorage.removeItem(storageKey);
          if (next.status === 'completed') {
            if (draftKey) localStorage.removeItem(draftKey);
            const data = await outlineRequest<Outline>(root);
            if (!active) return;
            setSource(data); setProposal(null); setEdits(data.edits || []);
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
  }, [jobId, root, storageKey, draftKey]);

  const changeEdits = (next: OutlineEdit[]) => { setEdits(next); setProposal(null); setJob(null); };
  const changeDepth = (next: number) => { setMaxDepth(next); setProposal(null); };
  const body = () => ({ base_version: source?.base_version, examples, edits, max_depth: maxDepth });
  const preview = async () => {
    setBusy(true); setError('');
    try { setProposal(await outlineRequest<Outline>(`${root}/preview`, body())); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!source) return;
    setBusy(true); setError('');
    try {
      setProposal(await outlineRequest<Outline>(`${root}/preview`, body()));
      const next = await outlineRequest<Job>(`${root}/apply`, body());
      if (importJobId) { if (draftKey) localStorage.removeItem(draftKey); onConfirmed?.(next.id); }
      else { localStorage.setItem(storageKey, next.id); setJob(next); setJobId(next.id); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true); setError('');
    try { setEdits([]); setProposal(await outlineRequest<Outline>(`${root}/preview`, {...body(), edits:[]})); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  return { root, source, proposal, examples, edits, maxDepth, loading, busy: busy || !!jobId, error, job,
    changeEdits, changeDepth, preview, apply, reset, retry: () => setReload(value => value + 1) };
}
