import type { MistakeRecord } from '../../types';

export interface ReviewSessionResult {
  id: string;
  title: string;
  quality: number;
  nextReview?: string;
}

export const estimateReviewMinutes = (count: number) => count > 0 ? Math.max(3, count * 3) : 0;

export function collectReviewConcepts(records: MistakeRecord[], limit = 4): string[] {
  const names = records.flatMap((record) => [
    ...(record.linked_concepts || []).map((concept) => concept.name),
    ...(record.tags || []),
  ]).map((name) => name.trim()).filter(Boolean);
  return Array.from(new Set(names)).slice(0, limit);
}

export function summarizeReviewSession(results: ReviewSessionResult[]) {
  return {
    mastered: results.filter((item) => item.quality >= 4).length,
    revisit: results.filter((item) => item.quality === 3).length,
    weak: results.filter((item) => item.quality <= 2).length,
  };
}

export function nextSuggestedReview(results: ReviewSessionResult[]): string {
  const dates = results.map((item) => item.nextReview || '').filter(Boolean).sort();
  return dates[0] || '';
}
