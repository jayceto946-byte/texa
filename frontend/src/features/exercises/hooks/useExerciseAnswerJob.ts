import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { get, post } from '../../../api/client';
import type { ExerciseRecord } from '../../../types';
interface Options { exercise: ExerciseRecord | null; bookQuery: string; onMessage: (message: string) => void; onRecordSaved: (record: ExerciseRecord) => void }
type AnswerStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'unavailable';
type Job = { id: string; status: string; message?: string; result?: { answer?: string } };
export function useExerciseAnswerJob({ exercise, bookQuery, onMessage, onRecordSaved }: Options) {
  const key = `${bookQuery}:${exercise?.id || ''}`;
  const selection = useRef(key); useLayoutEffect(() => { selection.current = key; return () => { selection.current = ''; }; }, [key]);
  const submitting = useRef(false);
  const drafts = useRef(new Map<string, string>());
  const [answerDraft, updateDraft] = useState('');
  const [answerBusy, setBusy] = useState(false);
  const [jobId, setJobId] = useState('');
  const [answerStatus, setStatus] = useState<AnswerStatus>('idle');
  const [answerStatusMessage, setMessage] = useState('');
  const [saveMessage, setSaveMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const setAnswerDraft = useCallback((text: string) => { drafts.current.set(selection.current, text); updateDraft(text); setSaveMessage(''); }, []);
  const apply = useCallback((job: Job) => {
    if (job.status === 'queued' || job.status === 'running') { setJobId(job.id); setBusy(true); setStatus(job.status); setMessage(job.message || '正在后台生成答案'); }
    else {
      setJobId(''); setBusy(false);
      if (job.status === 'completed' && job.result?.answer?.trim()) { setAnswerDraft(job.result.answer); setStatus('completed'); setMessage('答案草稿已生成，保存后才写入题库。'); }
      else { setStatus('failed'); setMessage(job.message || '生成结果没有可用答案，请重试。'); }
    }
  }, [setAnswerDraft]);
  const reconnect = useCallback(async (recoverCurrent = false) => {
    if (!exercise?.id) return false;
    const requested = key;
    try {
      const res = await get('/exercises/answer/jobs/latest' + (bookQuery ? bookQuery + '&' : '?') + 'id=' + encodeURIComponent(exercise.id), 20000);
      if (selection.current !== requested) return false;
      if (!res?.success) throw Error('read');
      if (res.data) {
        // Preserve local editing and do not resurrect old completed jobs over saved answers.
        if (['queued', 'running'].includes(res.data.status) || (!drafts.current.has(requested) && (recoverCurrent || !exercise.answer))) apply(res.data);
        else if (res.data.status === 'failed') { setBusy(false); setStatus('failed'); setMessage(res.data.message || '上次生成失败'); }
        else { setBusy(false); setStatus(drafts.current.has(requested) ? 'completed' : 'idle'); setMessage(''); }
      } else { setBusy(false); setStatus(drafts.current.has(requested) ? 'completed' : 'idle'); setMessage(''); }
      return true;
    } catch { if (selection.current === requested) { setBusy(false); setStatus('unavailable'); setMessage('连接中断，执行结果尚未确定。请重新读取任务状态，勿重复创建。'); } return false; }
  }, [exercise, key, bookQuery, apply]);
  useEffect(() => {
    updateDraft(drafts.current.get(key) || ''); setJobId(''); setBusy(false); setStatus('idle'); setMessage(''); setSaveMessage('');
  }, [key]);
  useEffect(() => {
    setBusy(true);
    let active = true;
    // Defer so StrictMode cleanup cannot start two lookup chains.
    const timer = window.setTimeout(() => { if (active) void reconnect(); }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [reconnect]);
  useEffect(() => {
    if (!jobId) return;
    let stopped = false, reading = false;
    const requested = key;
    const poll = async () => {
      if (reading) return; reading = true;
      try { const res = await get('/exercises/answer/jobs/' + encodeURIComponent(jobId), 20000); if (stopped || selection.current !== requested) return; if (!res?.success || !res.data) throw Error('read'); apply(res.data); }
      catch { if (!stopped && selection.current === requested) { setStatus('unavailable'); setMessage('连接中断，后台任务可能仍在执行；正在重新读取状态。'); } }
      finally { reading = false; }
    }; void poll(); const timer = window.setInterval(poll, 1600); return () => { stopped = true; window.clearInterval(timer); };
  }, [jobId, key, apply]);
  const generateStandardAnswer = useCallback(async () => {
    if (!exercise || answerBusy || submitting.current || answerStatus === 'unavailable') return;
    submitting.current = true; const requested = key; setBusy(true); setStatus('queued'); setMessage('正在创建后台答案任务');
    try {
      const res = await post('/exercises/answer/jobs' + bookQuery, { id: exercise.id }, 20000); if (selection.current !== requested) return;
      if (!res?.success || !res.data?.id) { setBusy(false); setStatus('failed'); setMessage(res?.message || '后台拒绝创建答案任务'); return; } apply(res.data);
    } catch { if (selection.current === requested) { setBusy(false); setStatus('unavailable'); setMessage('创建请求中断，先读取现有任务状态。'); void reconnect(true); } }
    finally { submitting.current = false; }
  }, [exercise, answerBusy, answerStatus, key, bookQuery, apply, reconnect]);
  const saveStandardAnswer = useCallback(async () => {
    if (!exercise || !answerDraft.trim() || answerBusy || submitting.current) return;
    submitting.current = true; const requested = key; setSaving(true); setSaveMessage('正在保存…');
    try {
      const res = await post('/exercises/answer/save' + bookQuery, { id: exercise.id, answer: answerDraft, explanation: exercise.explanation || '' }); if (selection.current !== requested) return;
      if (!res?.success || !res.data?.id) throw Error(res?.message || '保存失败');
      drafts.current.delete(requested); updateDraft(''); onRecordSaved(res.data as ExerciseRecord); onMessage('标准答案已保存'); setStatus('idle'); setMessage(''); setSaveMessage('已保存到题库'); return true;
    } catch { if (selection.current === requested) setSaveMessage('保存未确认，当前草稿保留。请核对题库后重试。'); }
    finally { submitting.current = false; if (selection.current === requested) setSaving(false); }
  }, [exercise, answerDraft, answerBusy, key, bookQuery, onRecordSaved, onMessage]);
  return { answerDraft, setAnswerDraft, answerBusy, answerStatus, answerStatusMessage, saveMessage, saving, reconnect, generateStandardAnswer, saveStandardAnswer };
}
