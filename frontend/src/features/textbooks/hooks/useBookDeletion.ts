import { useEffect, useState } from 'react';
import { del, get, post } from '../../../api/client';

type Preview = { book_id: string; display_name: string; active_jobs: { id: string; status: string }[] };
export function useBookDeletion(reference: string, onDeleted: (name: string) => void) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const read = async () => {
      try {
        const result = await get(`/books/${encodeURIComponent(reference)}/lifecycle-preview`);
        if (!result.success) throw new Error(result.message || '无法读取删除范围');
        if (!active) return;
        setPreview(result.data);
        if (stopping && result.data.active_jobs.length) timer = setTimeout(() => { void read(); }, 1500);
        else if (stopping) { setStopping(false); setStep(2); }
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : '无法读取删除范围'); }
    };
    void read();
    return () => { active = false; clearTimeout(timer); };
  }, [reference, stopping]);
  const next = async () => {
    if (!preview) return;
    setError('');
    if (!preview.active_jobs.length) { setStep(2); return; }
    setBusy(true);
    try {
      for (const job of preview.active_jobs) {
        const result = await post(`/jobs/${encodeURIComponent(job.id)}/cancel`, {});
        if (!result.success) throw new Error(result.message || '停止任务失败');
      }
      setStopping(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '停止任务失败'); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!preview || name !== preview.display_name) return;
    setBusy(true); setError('');
    try {
      const query = new URLSearchParams({ confirm_book_id: preview.book_id, confirm_book_name: name });
      const result = await del(`/books/${encodeURIComponent(reference)}?${query}`, 60000);
      if (!result.success) throw new Error(result.message || '教材删除失败');
      onDeleted(result.data.storage_name);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '教材删除失败'); }
    finally { setBusy(false); }
  };
  return { preview, step, name, setName, busy, stopping, error, next, remove };
}
