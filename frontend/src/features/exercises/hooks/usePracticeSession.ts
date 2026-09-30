import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { post } from '../../../api/client';
import type { ExercisePracticeSession, ExerciseRecord } from '../../../types';

type SessionAction = 'pause' | 'resume' | 'abandon';

interface UsePracticeSessionOptions {
  records: ExerciseRecord[];
  setRecords: Dispatch<SetStateAction<ExerciseRecord[]>>;
  practiceSession: ExercisePracticeSession | null;
  setPracticeSession: Dispatch<SetStateAction<ExercisePracticeSession | null>>;
  bookQuery: string;
  targetSubject: string;
  statusFilter: string;
  refreshOverview: () => Promise<void>;
}

export function usePracticeSession({
  records,
  setRecords,
  practiceSession,
  setPracticeSession,
  bookQuery,
  targetSubject,
  statusFilter,
  refreshOverview,
}: UsePracticeSessionOptions) {
  const [practiceId, setPracticeId] = useState('');
  const [practiceAnswer, setPracticeAnswer] = useState('');
  const [practiceSolutionOpen, setPracticeSolutionOpen] = useState(false);
  const [practiceMessage, setPracticeMessage] = useState('');
  const [candidateId, setCandidateId] = useState('');
  const [sessionLimit, setSessionLimit] = useState(20);
  const [sessionShuffle, setSessionShuffle] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);

  const showPracticeMessage = useCallback((message: string) => {
    setPracticeMessage(message);
  }, []);

  const practicePool = useMemo(() => {
    const rank: Record<string, number> = { needs_review: 0, practicing: 1, new: 2, mastered: 3 };
    return [...records].sort((a, b) =>
      (rank[a.status] ?? 2) - (rank[b.status] ?? 2)
      || (a.practice_count || 0) - (b.practice_count || 0));
  }, [records]);

  const currentPractice = useMemo(() => {
    if (practiceSession && ['active', 'paused', 'completed'].includes(practiceSession.status)) {
      return practiceSession.current_exercise || null;
    }
    if (practiceId) return records.find((item) => item.id === practiceId) || null;
    return practicePool.find((item) => item.status !== 'mastered') || practicePool[0] || null;
  }, [practiceId, practicePool, practiceSession, records]);

  const resetAnswer = useCallback(() => {
    setPracticeAnswer('');
    setPracticeSolutionOpen(false);
  }, []);

  const startPracticeSession = useCallback(async () => {
    setSessionBusy(true);
    setPracticeMessage('');
    try {
      const res = await post(`/exercises/practice-sessions${bookQuery}`, {
        subject: targetSubject,
        status: statusFilter,
        limit: sessionLimit,
        shuffle: sessionShuffle,
      });
      if (!res?.success) {
        setPracticeMessage(res?.message || '无法开始练习会话');
        return;
      }
      setPracticeSession(res.data as ExercisePracticeSession);
      resetAnswer();
      setPracticeMessage(res.message || '练习会话已开始');
    } catch (error) {
      setPracticeMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSessionBusy(false);
    }
  }, [bookQuery, resetAnswer, sessionLimit, sessionShuffle, setPracticeSession, statusFilter, targetSubject]);

  const changePracticeSessionStatus = useCallback(async (action: SessionAction) => {
    if (!practiceSession) return;
    setSessionBusy(true);
    try {
      const res = await post(`/exercises/practice-sessions/${encodeURIComponent(practiceSession.id)}/${action}${bookQuery}`, {});
      if (!res?.success) {
        setPracticeMessage(res?.message || '练习会话状态更新失败');
        return;
      }
      setPracticeSession(res.data as ExercisePracticeSession);
      setPracticeMessage(action === 'pause' ? '练习已暂停，可稍后继续' : action === 'resume' ? '练习已继续' : '本轮练习已结束');
    } catch (error) {
      setPracticeMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSessionBusy(false);
    }
  }, [bookQuery, practiceSession, setPracticeSession]);

  const selectPractice = useCallback((record?: ExerciseRecord | null) => {
    const next = record
      || practicePool.find((item) => item.id !== currentPractice?.id && item.status !== 'mastered')
      || practicePool.find((item) => item.id !== currentPractice?.id)
      || practicePool[0]
      || null;
    setPracticeId(next?.id || '');
    resetAnswer();
    setPracticeMessage('');
  }, [currentPractice?.id, practicePool, resetAnswer]);

  const submitPractice = useCallback(async (quality: number, addToMistake = false) => {
    if (!currentPractice) return;
    if (practiceSession && practiceSession.status !== 'active') {
      setPracticeMessage('请先继续当前练习会话');
      return;
    }
    setSessionBusy(true);
    try {
      const sessionMode = Boolean(practiceSession);
      const path = sessionMode
        ? `/exercises/practice-sessions/${encodeURIComponent(practiceSession!.id)}/answer${bookQuery}`
        : `/exercises/practice${bookQuery}`;
      const res = await post(path, sessionMode ? {
        exercise_id: currentPractice.id,
        user_answer: practiceAnswer,
        quality,
        add_to_mistake: addToMistake,
      } : {
        id: currentPractice.id,
        user_answer: practiceAnswer,
        quality,
        add_to_mistake: addToMistake,
      });
      if (!res?.success) {
        setPracticeMessage(res?.message || '练习记录失败');
        return;
      }
      const updatedRecord = (sessionMode ? res.record : res.data) as ExerciseRecord;
      setCandidateId(res.candidate_id || '');
      setRecords((current) => current.map((item) => item.id === currentPractice.id ? updatedRecord : item));
      if (sessionMode) {
        const nextSession = res.data as ExercisePracticeSession;
        setPracticeSession(nextSession);
        resetAnswer();
        const summary = nextSession.summary;
        setPracticeMessage(res.candidate_id ? '本次做错的题目与作答已准备，确认后才会进入错题本。' : nextSession.status === 'completed'
          ? `本轮完成：${summary?.answered || 0} 题，平均自评 ${summary?.average_quality || 0}`
          : res.message || '已记录，进入下一题');
      } else {
        setPracticeMessage(res.candidate_id ? '本次做错的题目与作答已准备，确认后才会进入错题本。' : addToMistake && res.mistake_id ? '已记录练习，并转入错题本' : '已记录练习结果');
      }
      await refreshOverview();
    } catch (error) {
      setPracticeMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSessionBusy(false);
    }
  }, [bookQuery, currentPractice, practiceAnswer, practiceSession, refreshOverview, resetAnswer, setPracticeSession, setRecords]);

  const sendPracticeToMistake = useCallback(async () => {
    if (!currentPractice) return;
    try {
      const res = await post(`/exercises/to-mistake${bookQuery}`, {
        id: currentPractice.id,
        user_answer: practiceAnswer,
        mistake_type: ['思路卡住'],
      });
      if (!res?.success) {
        setPracticeMessage(res?.message || '转入错题本失败');
        return;
      }
      setPracticeMessage('已转入错题本');
      setRecords((current) => current.map((item) => item.id === currentPractice.id ? res.data as ExerciseRecord : item));
      await refreshOverview();
    } catch (error) {
      setPracticeMessage(error instanceof Error ? error.message : String(error));
    }
  }, [bookQuery, currentPractice, practiceAnswer, refreshOverview, setRecords]);

  const clearDeletedPractice = useCallback((id: string) => {
    if (practiceId !== id) return;
    setPracticeId('');
    resetAnswer();
  }, [practiceId, resetAnswer]);

  return {
    practicePool,
    currentPractice,
    practiceAnswer,
    setPracticeAnswer,
    practiceSolutionOpen,
    setPracticeSolutionOpen,
    practiceMessage,
    candidateId,
    showPracticeMessage,
    sessionLimit,
    setSessionLimit,
    sessionShuffle,
    setSessionShuffle,
    sessionBusy,
    startPracticeSession,
    changePracticeSessionStatus,
    selectPractice,
    submitPractice,
    sendPracticeToMistake,
    clearDeletedPractice,
  };
}
