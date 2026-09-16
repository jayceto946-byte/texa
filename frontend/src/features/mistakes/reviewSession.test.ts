import { describe, expect, it } from 'vitest';
import type { MistakeRecord } from '../../types';
import { collectReviewConcepts, estimateReviewMinutes, nextSuggestedReview, summarizeReviewSession } from './reviewSession';

const record = (id: string, tags: string[], concepts: string[] = []): MistakeRecord => ({
  id,
  question_text: id,
  user_answer: '',
  correct_answer: '',
  source: '',
  subject: '数学',
  tags,
  mistake_type: [],
  difficulty: 3,
  created_at: '2026-09-16',
  linked_concepts: concepts.map((name) => ({ name })),
});

describe('review session summary', () => {
  it('uses existing review items to estimate time and collect distinct concepts', () => {
    expect(estimateReviewMinutes(0)).toBe(0);
    expect(estimateReviewMinutes(2)).toBe(6);
    expect(collectReviewConcepts([
      record('a', ['极限'], ['连续']),
      record('b', ['极限', '导数'], ['连续']),
    ])).toEqual(['连续', '极限', '导数']);
  });

  it('groups outcomes by existing SM-2 quality and keeps the earliest returned date', () => {
    const results = [
      { id: 'a', title: 'A', quality: 5, nextReview: '2026-09-20' },
      { id: 'b', title: 'B', quality: 3, nextReview: '2026-09-18' },
      { id: 'c', title: 'C', quality: 1, nextReview: '2026-09-17' },
    ];
    expect(summarizeReviewSession(results)).toEqual({ mastered: 1, revisit: 1, weak: 1 });
    expect(nextSuggestedReview(results)).toBe('2026-09-17');
  });
});
