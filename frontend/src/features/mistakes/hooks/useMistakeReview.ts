import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';
import { post } from '../../../api/client';
import type { MistakeRecord } from '../../../types';

interface UseMistakeReviewOptions {
  bookQuery: string;
  setRecords: Dispatch<SetStateAction<MistakeRecord[]>>;
  setDueRecords: Dispatch<SetStateAction<MistakeRecord[]>>;
  refreshDue: () => Promise<void>;
  refreshStats: () => Promise<void>;
}

export function useMistakeReview({
  bookQuery,
  setRecords,
  setDueRecords,
  refreshDue,
  refreshStats,
}: UseMistakeReviewOptions) {
  const [expandedReviewId, setExpandedReviewId] = useState('');
  const [reviewMessage, setReviewMessage] = useState('');

  const showReviewMessage = useCallback((message: string) => {
    setReviewMessage(message);
  }, []);

  const expandReview = useCallback((id: string) => {
    setExpandedReviewId(id);
  }, []);

  const toggleReview = useCallback((id: string) => {
    setExpandedReviewId((current) => current === id ? '' : id);
  }, []);

  const clearDeletedReview = useCallback((id: string) => {
    setExpandedReviewId((current) => current === id ? '' : current);
  }, []);

  const handleReview = useCallback(async (id: string, quality: number): Promise<MistakeRecord | null> => {
    setReviewMessage('');
    try {
      const res = await post(`/mistakes/review${bookQuery}`, { id, quality });
      if (!res?.success) {
        setReviewMessage(res?.message || '复习记录失败');
        return null;
      }
      const updated = res.data as MistakeRecord | undefined;
      if (updated) {
        setRecords((current) => current.map((item) => item.id === updated.id ? updated : item));
        setDueRecords((current) => current.map((item) => item.id === updated.id ? updated : item));
        setReviewMessage(res.message || `已记录复习，下次复习：${updated.next_review || '待计算'}`);
      } else {
        setReviewMessage(res.message || '已记录复习');
      }
      await refreshDue();
      await refreshStats();
      return updated || null;
    } catch (error) {
      setReviewMessage(error instanceof Error ? error.message : String(error));
      return null;
    }
  }, [bookQuery, refreshDue, refreshStats, setDueRecords, setRecords]);

  return {
    expandedReviewId,
    reviewMessage,
    showReviewMessage,
    expandReview,
    toggleReview,
    clearDeletedReview,
    handleReview,
  };
}
