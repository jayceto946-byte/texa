import { useCallback, useEffect, useRef, useState } from 'react';
import { get, post } from '../../../api/client';
import type { ExerciseRecord } from '../../../types';

interface UseExerciseAnswerJobOptions {
  exercise: ExerciseRecord | null;
  bookQuery: string;
  onMessage: (message: string) => void;
  onRecordSaved: (record: ExerciseRecord) => void;
}
type AnswerStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'unavailable';

export function useExerciseAnswerJob({ exercise, bookQuery, onMessage, onRecordSaved }: UseExerciseAnswerJobOptions) {
  const selection = useRef('');
  const submitting = useRef(false);
  const [answerDraft, setAnswerDraft] = useState('');
  const [answerBusy, setAnswerBusy] = useState(false);
  const [answerJobId, setAnswerJobId] = useState('');
  const [answerStatus, setAnswerStatus] = useState<AnswerStatus>('idle');
  const [answerStatusMessage, setAnswerStatusMessage] = useState('');
  useEffect(() => { selection.current = `${bookQuery}:${exercise?.id || ''}`; }, [bookQuery, exercise?.id]);

  const applyJob = useCallback((job: { id: string; status: string; message?: string; result?: { answer?: string } }) => {
    if (['queued', 'running'].includes(job.status)) {
      setAnswerJobId(job.id);
      setAnswerBusy(true);
      setAnswerStatus(job.status as AnswerStatus);
      setAnswerStatusMessage(job.message || '标准答案正在后台生成');
    } else {
      setAnswerBusy(false);
      setAnswerJobId('');
      if (job.status === 'completed' && job.result?.answer?.trim()) {
        setAnswerDraft(job.result.answer);
        setAnswerStatus('completed');
        setAnswerStatusMessage('答案草稿已生成，可阅读或编辑，保存后才写入题库。');
      } else {
        setAnswerStatus('failed');
        setAnswerStatusMessage(job.status === 'completed' ? '生成结果没有可用答案，请重试。' : job.message || '标准答案生成未完成，可重试。');
      }
    }
  }, []);

  useEffect(() => {
    setAnswerDraft(exercise?.answer || '');
    setAnswerJobId('');setAnswerBusy(false);setAnswerStatus('idle');setAnswerStatusMessage('');
    if (!exercise?.id) return;
    setAnswerBusy(true);
    let cancelled = false;
    void get('/exercises/answer/jobs/latest' + (bookQuery ? bookQuery + '&' : '?') + 'id=' + encodeURIComponent(exercise.id), 20000)
      .then(res => {
        if (cancelled) return;
        if (!res?.success) throw Error('status');
        setAnswerBusy(false);
        if (res.data && (res.data.status !== 'completed' || !exercise.answer)) applyJob(res.data);
      }).catch(() => { if (!cancelled) { setAnswerBusy(false);setAnswerStatus('unavailable');setAnswerStatusMessage('暂时无法读取生成状态，可重新连接任务。'); } });
    return () => { cancelled = true; };
  }, [bookQuery, exercise?.answer, exercise?.id, applyJob]);

  useEffect(() => {
    if (!answerJobId) return;
    let stopped = false, reading = false;
    const poll = async () => {
      if (reading) return;
      reading = true;
      try {
        const res = await get('/exercises/answer/jobs/' + encodeURIComponent(answerJobId), 20000);
        if (stopped) return;
        if (!res?.success || !res.data) throw Error('status');
        applyJob(res.data);
      } catch {
        if (!stopped) { setAnswerStatus('unavailable');setAnswerStatusMessage('连接中断，后台任务可能仍在执行；正在重新读取状态。'); }
      } finally { reading = false; }
    };
    void poll();const timer = window.setInterval(poll, 1600);
    return () => { stopped = true;window.clearInterval(timer); };
  }, [answerJobId, applyJob]);

  const generateStandardAnswer = useCallback(async () => {
    if (!exercise || answerBusy || submitting.current) return;
    submitting.current = true;
    const requestedSelection = selection.current;
    setAnswerBusy(true);setAnswerStatus('queued');setAnswerStatusMessage('正在创建后台答案任务');
    try {
      const res = await post('/exercises/answer/jobs' + bookQuery, { id: exercise.id }, 20000);
      if (selection.current !== requestedSelection) return;
      if (!res?.success || !res.data?.id) throw Error('create');
      applyJob(res.data);
    } catch {
      if (selection.current === requestedSelection) { setAnswerBusy(false);setAnswerStatus('failed');setAnswerStatusMessage('无法连接答案任务，请检查本地服务后重试。'); }
    } finally { submitting.current = false; }
  }, [answerBusy, bookQuery, exercise, applyJob]);

  const saveStandardAnswer = useCallback(async () => {
    if (!exercise || !answerDraft.trim() || answerBusy || submitting.current) return;
    submitting.current = true;
    const requestedSelection = selection.current;
    setAnswerBusy(true);
    try {
      const res = await post(`/exercises/answer/save${bookQuery}`, { id: exercise.id, answer: answerDraft, explanation: exercise.explanation || '' });
      if (selection.current !== requestedSelection) return;
      if (!res?.success || !res.data?.id) { onMessage(res?.message || '保存标准答案失败');return; }
      onRecordSaved(res.data as ExerciseRecord);onMessage('标准答案已保存');
      setAnswerStatus('idle');setAnswerStatusMessage('');
    } catch {
      if (selection.current === requestedSelection) onMessage('答案保存失败，当前草稿保留，请重试。');
    } finally {
      submitting.current = false;
      if (selection.current === requestedSelection) setAnswerBusy(false);
    }
  }, [answerDraft, answerBusy, bookQuery, exercise, onMessage, onRecordSaved]);

  return { answerDraft, setAnswerDraft, answerBusy, answerStatus, answerStatusMessage, generateStandardAnswer, saveStandardAnswer };
}
