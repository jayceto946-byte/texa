import { describe, expect, it } from 'vitest';
import type { CandidateSourceRegistry, ExerciseCandidate } from '../../../types';
import { assignSourceSuffix } from './sourceAssignment';
import { canSubmitCandidate } from './candidateContract';

function fixture() {
  const text = '题干😀给定条件求结果。\n演算过程：这是原解。';
  const registry = { canonical_hash: 'a'.repeat(64), units: [], source_blocks: [{ block_id: 'b', order: 0, block_type: 'paragraph', text }] } as unknown as CandidateSourceRegistry;
  const candidate = { id: 'c', question_text: text, answer: '', explanation: '', tags: [], issues: [], review: { content_hash: 'old', resolutions: [] }, projection: {
    version: 1, canonical_hash: registry.canonical_hash, unit_ids: ['b'], method: 'unresolved',
    scope: { chapter: '', page_start: null, page_end: null, source_mode: 'file' }, dependencies: [],
    parts: { question: [], answer: [], explanation: [], context: [], unassigned: [{ block_id: 'b', start: 0, end: null }] },
  } } as unknown as ExerciseCandidate;
  return { candidate, registry, text };
}

describe('source role assignment', () => {
  it('uses Unicode source offsets and retains all source bytes across the boundary', () => {
    const { candidate, registry, text } = fixture();
    const utf16 = text.indexOf('演算过程');
    const result = assignSourceSuffix(candidate, registry, 'b', utf16, 'explanation');
    expect(result.question_text + result.explanation).toBe(text);
    expect(result.projection?.parts.explanation[0].start).toBe(Array.from(text.slice(0, utf16)).length);
    expect(result.projection?.parts.question[0].end).toBe(result.projection?.parts.explanation[0].start);
    expect(result.review).toBeNull();
    expect(result.projection?.method).toBe('user_edited');
    expect(canSubmitCandidate(result)).toBe(false);
    expect(candidate.question_text).toBe(text);
    expect(candidate.projection?.parts.unassigned).toHaveLength(1);
  });
  it('can refine an existing split without overlapping or dropping source spans', () => {
    const { candidate, registry, text } = fixture();
    const first = assignSourceSuffix(candidate, registry, 'b', text.indexOf('演算过程'), 'explanation');
    const result = assignSourceSuffix(first, registry, 'b', text.indexOf('这是'), 'answer');
    expect(result.question_text + result.explanation + result.answer).toBe(text);
    expect(result.answer).toBe('这是原解。');
    expect(assignSourceSuffix(result, registry, 'foreign', 0, 'context')).toBe(result);
    expect(assignSourceSuffix(result, registry, 'b', text.length, 'context')).toBe(result);
  });
});
