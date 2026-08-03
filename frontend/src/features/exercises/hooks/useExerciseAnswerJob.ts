import { useCallback, useEffect, useState } from 'react';
import { get, post } from '../../../api/client';
import type { ExerciseRecord } from '../../../types';

interface UseExerciseAnswerJobOptions {
  exercise: ExerciseRecord | null;
  bookQuery: string;
  onMessage: (message: string) => void;
  onRecordSaved: (record: ExerciseRecord) => void;
}

export function useExerciseAnswerJob({
  exercise,
  bookQuery,
  onMessage,
  onRecordSaved,
}: UseExerciseAnswerJobOptions) {
  const [answerDraft, setAnswerDraft] = useState('');
  const [answerBusy, setAnswerBusy] = useState(false);
  const [answerJobId, setAnswerJobId] = useState('');

  useEffect(() => {
    setAnswerDraft(exercise?.answer || '');
    setAnswerJobId('');
    setAnswerBusy(false);
    if (!exercise?.id) return;

    let cancelled = false;
    get('/exercises/answer/jobs/latest' + (bookQuery ? bookQuery + '&' : '?') + 'id=' + encodeURIComponent(exercise.id), 20000)
      .then((res) => {
        if (cancelled || !res?.success || !res.data) return;
        const job = res.data;
        if (job.status === 'queued' || job.status === 'running') {
          setAnswerJobId(job.id);
          setAnswerBusy(true);
          onMessage(job.message || '标准答案正在后台生成');
        } else if (job.status === 'completed' && !exercise.answer && job.result?.answer) {
          setAnswerDraft(job.result.answer);
          onMessage('解析已生成');
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [bookQuery, exercise?.answer, exercise?.id, onMessage]);

  useEffect(() => {
    if (!answerJobId) return;
    let stopped = false;
    const poll = async () => {
      try {
        const res = await get('/exercises/answer/jobs/' + encodeURIComponent(answerJobId), 20000);
        if (stopped) return;
        if (!res?.success || !res.data) {
          onMessage(res?.message || '答案任务状态读取失败');
          setAnswerBusy(false);
          setAnswerJobId('');
          return;
        }
        const job = res.data;
        if (job.status === 'completed') {
          setAnswerDraft(job.result?.answer || '');
          onMessage((job.message || '答案草稿已生成') + '（引用 ' + (job.result?.evidence_count || 0) + ' 条教材证据）');
          setAnswerBusy(false);
          setAnswerJobId('');
        } else if (['failed', 'cancelled', 'interrupted'].includes(job.status)) {
          onMessage(job.message || job.error || '标准答案生成失败');
          setAnswerBusy(false);
          setAnswerJobId('');
        } else {
          setAnswerBusy(true);
          onMessage(job.message || '标准答案正在后台生成');
        }
      } catch {
        // The durable backend job continues when polling is interrupted by navigation.
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1600);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [answerJobId, onMessage]);

  const generateStandardAnswer = useCallback(async () => {
    if (!exercise || answerBusy) return;
    setAnswerBusy(true);
    onMessage('正在创建后台答案任务');
    try {
      const res = await post('/exercises/answer/jobs' + bookQuery, { id: exercise.id }, 20000);
      if (!res?.success) {
        onMessage(res?.message || '生成标准答案失败');
        setAnswerBusy(false);
        return;
      }
      const jobId = res.job_id || res.data?.id || '';
      if (!jobId) {
        onMessage('后台未返回答案任务 ID');
        setAnswerBusy(false);
        return;
      }
      setAnswerJobId(jobId);
      onMessage(res.message || '标准答案已转入后台生成');
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error));
      setAnswerBusy(false);
    }
  }, [answerBusy, bookQuery, exercise, onMessage]);

  const saveStandardAnswer = useCallback(async () => {
    if (!exercise || !answerDraft.trim()) return;
    setAnswerBusy(true);
    onMessage('');
    try {
      const res = await post(`/exercises/answer/save${bookQuery}`, {
        id: exercise.id,
        answer: answerDraft,
        explanation: exercise.explanation || '',
      });
      if (!res?.success || !res.data?.id) {
        onMessage(res?.message || '保存标准答案失败');
        return;
      }
      onRecordSaved(res.data as ExerciseRecord);
      onMessage('标准答案已保存');
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setAnswerBusy(false);
    }
  }, [answerDraft, bookQuery, exercise, onMessage, onRecordSaved]);

  return {
    answerDraft,
    setAnswerDraft,
    answerBusy,
    generateStandardAnswer,
    saveStandardAnswer,
  };
}
