import { describe, expect, it } from 'vitest';
import type { ExerciseCandidate } from '../../../types';
import {
  filterCandidates,
  mergeSelectedCandidates,
  splitCandidateAtBlankLine,
  summarizeCandidates,
} from './candidateOperations';

function candidate(id: string, questionText = `题目 ${id}`): ExerciseCandidate {
  return {
    id,
    question_text: questionText,
    answer: `答案 ${id}`,
    explanation: '',
    source: 'test',
    subject: '数学',
    chapter: '第一章',
    suggested_type: '计算题',
    difficulty: 3,
    tags: [id],
    linked_concepts: [],
    confidence: 0.9,
    reasons: [],
    needs_llm: false,
    needs_review: false,
    validation_issues: [],
  };
}

describe('exercise candidate operations', () => {
  it('summarizes and filters validation state', () => {
    const items = [
      candidate('a'),
      { ...candidate('b'), needs_llm: true, validation_issues: ['边界待确认'] },
      { ...candidate('c'), duplicate_of: 'existing' },
    ];

    expect(summarizeCandidates(items)).toMatchObject({ total: 3, needsLlm: 1, issues: 1, duplicates: 1 });
    expect(filterCandidates(items, 'issues').map((item) => item.id)).toEqual(['b']);
    expect(filterCandidates(items, 'duplicates').map((item) => item.id)).toEqual(['c']);
  });

  it('merges adjacent candidates at their original position', () => {
    const items = [candidate('a'), candidate('b'), candidate('c')];
    const result = mergeSelectedCandidates(items, new Set(['b', 'c']));

    expect(result?.candidates.map((item) => item.id)).toEqual(['a', 'b']);
    expect(result?.merged.question_text).toBe('题目 b\n\n题目 c');
    expect(result?.merged.tags).toEqual(['b', 'c']);
  });

  it('rejects non-adjacent candidate merges', () => {
    const items = [candidate('a'), candidate('b'), candidate('c')];
    expect(mergeSelectedCandidates(items, new Set(['a', 'c']))).toBeNull();
  });

  it('splits only at an explicit blank line', () => {
    expect(splitCandidateAtBlankLine(candidate('a', '没有分隔'), 'fixed')).toBeNull();

    const parts = splitCandidateAtBlankLine(candidate('a', '第一问\n\n第二问'), 'fixed');
    expect(parts?.map((item) => item.id)).toEqual(['a-fixed-1', 'a-fixed-2']);
    expect(parts?.map((item) => item.question_text)).toEqual(['第一问', '第二问']);
    expect(parts?.[0].answer).toBe('');
  });
});

import { candidateHash, contentJson, editCandidate, canSubmitCandidate, editedIssue } from './candidateContract';
import type { CandidateProjection, ExerciseCandidate as CandidateV1 } from '../../../types';
const projection = (unit = 'b0'): CandidateProjection => ({ version: 1, canonical_hash: 'a'.repeat(64), unit_ids: [unit], scope: { chapter: '', page_start: null, page_end: null, source_mode: 'exercise_sections' }, method: 'whole_unit', parts: { question: [{ block_id: unit, start: 0, end: null }], answer: [], explanation: [], context: [], unassigned: [] }, dependencies: [] });
const v1 = (id: string): CandidateV1 & { projection: CandidateProjection } => ({ ...candidate(id), projection: projection(id), issues: [], review: null });
describe('candidate v1 review and source preservation', () => {
  it('matches Python UTF8 hash including emoji/newline and excludes metadata', async () => {
    const value = { ...candidate('x'), question_text: '中文😀\n$x$', answer: '', explanation: '', projection: null };
    expect(await candidateHash(value)).toBe('c9902b649ae1e73c6ccdc4df4733b628aed0a7ee1ac85583a1c544a0fc617d58');
    const metadataEdit = { ...value, tags: ['other'] };
    expect(contentJson(value)).toBe(contentJson(metadataEdit));
  });
  it('invalidates confirmation on every body or mapping edit, keeps metadata confirmation', () => {
    const value = { ...v1('a'), review: { content_hash: 'b'.repeat(64), resolutions: [] } };
    for (const updates of [{ question_text: 'new' }, { answer: 'new' }, { explanation: 'new' }, { projection: { ...projection('a') } }]) {
      const edited = editCandidate(value, updates);
      expect(edited.review).toBeNull(); expect(edited.projection?.method).toBe('user_edited'); expect(canSubmitCandidate(edited)).toBe(false);
    }
    expect(editCandidate(value, { tags: ['new'], difficulty: 1 }).review).toEqual(value.review);
  });
  it('ordinary empty answer and metadata issues do not require confirmation; selection never creates it', () => {
    const value = { ...v1('a'), answer: '', explanation: '', tags: [], issues: [{ key: 'missing_concepts:', code: 'missing_concepts', category: 'metadata' as const, block_ids: [], dependency_id: null }] };
    expect(canSubmitCandidate(value)).toBe(true);
    expect(summarizeCandidates([value]).ready).toBe(1);
    expect(value.review).toBeNull();
  });
  it('keeps overlapping content, metadata and duplicate sets separate', () => {
    const value = { ...v1('a'), duplicate_of: 'existing', issues: [editedIssue, { ...editedIssue, category: 'metadata' as const, key: 'metadata' }] };
    expect(summarizeCandidates([value])).toMatchObject({ content: 1, metadata: 1, duplicates: 1 });
    expect(filterCandidates([value], 'issues')).toHaveLength(1); expect(filterCandidates([value], 'metadata')).toHaveLength(1);
  });
  it('merge only adjacent compatible versions, retain all units and source solutions, clear review', () => {
    const a = v1('a'), b = v1('b'); a.explanation = 'source solution';
    const merged = mergeSelectedCandidates([a, b], new Set(['a', 'b']))?.merged;
    expect(merged?.projection?.unit_ids).toEqual(['a', 'b']); expect(merged?.explanation).toBe('source solution'); expect(merged?.review).toBeNull(); expect(canSubmitCandidate(merged!)).toBe(false);
    b.projection = { ...b.projection, canonical_hash: 'c'.repeat(64) };
    expect(mergeSelectedCandidates([a, b], new Set(['a', 'b']))).toBeNull();
  });
  it('split preserves source/answer only once, requires both new bodies to be confirmed', () => {
    const item = { ...v1('a'), question_text: '第一问\n\n第二问', explanation: 'source solution' };
    const parts = splitCandidateAtBlankLine(item, 'fixed')!;
    expect(parts[0].answer).toBe(''); expect(parts[0].explanation).toBe(''); expect(parts[1].explanation).toBe('source solution');
    expect(parts.every(p => p.projection?.unit_ids[0] === 'a' && p.review === null && !canSubmitCandidate(p))).toBe(true);
  });
  it('a generic current hash confirmation cannot bypass a required image', () => {
    const item = v1('a'); item.projection.dependencies.push({ id: 'fig', kind: 'figure', label: '图A', requirement: 'required', block_ids: ['f'], asset_ids: ['asset-A'], resolution: 'identified' });
    item.issues = [{ ...editedIssue, code: 'missing_required_input', key: 'missing_required_input:fig', dependency_id: 'fig' }];
    const confirmed = { ...item, review: { content_hash: 'a'.repeat(64), resolutions: [{ issue_key: 'missing_required_input:fig', decision: 'source_checked' as const }] } };
    expect(canSubmitCandidate(confirmed)).toBe(false);
  });
});
