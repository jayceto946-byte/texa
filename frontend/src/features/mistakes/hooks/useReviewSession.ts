import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, get, patch, post } from '../../../api/client';
import type { MistakeRecord } from '../../../types';

type ReviewItem = Pick<MistakeRecord, 'id' | 'question_text' | 'correct_answer' | 'explanation' | 'source' | 'subject' | 'chapter'>;
export type ReviewFeedback = { verdict: 'correct' | 'partial' | 'wrong' | 'unreadable'; summary: string; issues: string[]; suggestions: string[] };
export type ReviewSession = { id: string; revision: number; items: string[]; index: number; results: Record<string, string>; current_answer: string; revealed: boolean; current_item: ReviewItem | null; current_submission?: { filename: string; image_url: string }; feedback?: ReviewFeedback; grading?: boolean };

export function useReviewSession(sessionId: string, scope: string) {
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const query = `?book_name=${encodeURIComponent(scope)}`;
  const path = `/review/sessions/${encodeURIComponent(sessionId)}`;
  const identity = path + query;
  const latest = useRef({ identity, revision: 0 });
  useEffect(() => { latest.current = { identity, revision: 0 }; }, [identity]);
  const accept = useCallback((data: ReviewSession) => {
    if (latest.current.identity !== identity || data.revision < latest.current.revision) return false;
    latest.current.revision = data.revision;
    setSession(current => ({ ...current, ...data }));
    return true;
  }, [identity]);
  const load = useCallback(async () => {
    const result = await get(`${path}${query}`);
    if (!result?.success) throw new Error(result?.message || '无法恢复复习会话');
    if (accept(result.data as ReviewSession)) setAnswer(result.data.current_answer || '');
  }, [path, query, accept]);
  const refresh = useCallback(async () => {
    try { await load(); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '无法恢复复习会话'); }
    finally { setLoading(false); }
  }, [load]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!session?.grading || busy) return;
    const timer = window.setInterval(() => { void load().catch(() => setError('批改状态暂不可读取，请重试读取。')); }, 2000);
    return () => window.clearInterval(timer);
  }, [session?.grading, busy, load]);

  const action = async (perform: () => Promise<void>) => {
    if (busy || session?.grading) return;
    setBusy(true); setError('');
    try { await perform(); }
    catch (cause) {
      // A failed model request releases its lease and advances the revision.
      await load().catch(() => undefined);
      setError(cause instanceof Error ? cause.message : '操作失败，请重试');
    } finally { setBusy(false); }
  };
  const saveText = async () => {
    if (!session) throw new Error('请先恢复复习会话');
    if (answer === session.current_answer) return session.revision;
    const result = await patch(`${path}${query}`, { expected_revision: session.revision, answer, revealed: false });
    if (!result?.success) throw new Error(result?.message || '保存作答失败');
    accept(result.data);
    return result.data.revision as number;
  };
  const saveAnswer = () => action(async () => { await saveText(); });
  const reveal = () => action(async () => {
    if (!session || session.revealed) return;
    const revision = await saveText();
    const result = session.current_submission
      ? await post(`${path}/feedback${query}`, { expected_revision: revision }, 360000)
      : await patch(`${path}${query}`, { expected_revision: revision, answer: '', revealed: true });
    if (!result?.success) throw new Error(result?.message || '读取反馈失败');
    await load();
  });
  const upload = (file: File) => action(async () => {
    if (!session || session.revealed) return;
    if (!/\.(png|jpe?g|webp|bmp)$/i.test(file.name) || file.size > 20 * 1024 * 1024) throw new Error('请选择 20MB 以内的 PNG、JPEG、WebP 或 BMP 图片');
    const revision = await saveText();
    const form = new FormData(); form.append('file', file); form.append('expected_revision', String(revision));
    const response = await apiFetch(`${path}/image${query}`, { method: 'POST', body: form }, 60000);
    const result = await response.json();
    if (!response.ok || !result?.success) throw new Error(result?.detail || result?.message || '上传作答图片失败');
    accept(result.data);
  });
  const removeImage = () => action(async () => {
    if (!session || session.revealed) return;
    const result = await post(`${path}/image/remove${query}`, { expected_revision: session.revision });
    if (!result?.success) throw new Error(result?.message || '移除图片失败');
    accept(result.data);
  });
  const submit = (result: string) => action(async () => {
    if (!session) return;
    const response = await post(`${path}/results${query}`, { expected_revision: session.revision,
      operation_id: `review:${session.id}:${session.index}`, result, hint_used: result === 'prompted_correct', judgement_source: 'user_confirmed' });
    if (!response?.success) throw new Error(response?.message || '记录复习结果失败');
    await load();
  });
  return { session, answer, setAnswer, error, loading, busy: busy || Boolean(session?.grading), refresh, saveAnswer, reveal, upload, removeImage, submit };
}
