import type { ExerciseCandidate } from '../../../types';
import { contentIssues, editCandidate, mergeProjections, canSubmitCandidate } from './candidateContract';

export type CandidateFilter = 'all' | 'issues' | 'metadata' | 'duplicates';

export function summarizeCandidates(candidates: ExerciseCandidate[]) {
  const needsLlm = candidates.filter((item) => item.needs_llm).length;
  const refined = candidates.filter((item) => item.refined_by_llm).length;
  const issues = candidates.filter((item) => (item.validation_issues || []).length > 0).length;
  const duplicates = candidates.filter((item) => Boolean(item.duplicate_of)).length;
  return {
    total: candidates.length,
    needsLlm,
    confident: candidates.length - needsLlm,
    refined,
    issues,
    duplicates,
    content: candidates.filter(c => contentIssues(c).length > 0).length,
    metadata: candidates.filter(c => (c.issues || []).some(i => i.category === 'metadata')).length,
    ready: candidates.filter(canSubmitCandidate).length,
  };
}

export function filterCandidates(candidates: ExerciseCandidate[], filter: CandidateFilter) {
  return candidates.filter((item) => {
    if (filter === 'issues') return item.projection ? contentIssues(item).length > 0 : (item.validation_issues || []).length > 0;
    if (filter === 'metadata') return (item.issues || []).some(i => i.category === 'metadata');
    if (filter === 'duplicates') return Boolean(item.duplicate_of);
    return true;
  });
}

export function mergeSelectedCandidates(
  candidates: ExerciseCandidate[],
  selectedIds: ReadonlySet<string>,
): { candidates: ExerciseCandidate[]; merged: ExerciseCandidate } | null {
  const selected = candidates.filter((item) => selectedIds.has(item.id));
  const selectedIndexes = candidates
    .map((item, index) => selectedIds.has(item.id) ? index : -1)
    .filter((index) => index >= 0);
  if (selectedIndexes.some((index, offset) => index !== selectedIndexes[0] + offset)) return null;

  if (selected.length < 2) return null;

  const projections = selected.flatMap(c => c.projection ? [c.projection] : []);
  const projection = projections.length ? mergeProjections(projections) : null;
  if (projections.length && (projections.length !== selected.length || !projection)) return null;
  const firstIndex = candidates.findIndex((item) => item.id === selected[0].id);
  const merged: ExerciseCandidate = {
    ...selected[0],
    question_text: selected.map((item) => item.question_text.trim()).filter(Boolean).join('\n\n'),
    answer: selected.map((item) => item.answer.trim()).filter(Boolean).join('\n\n'),
    explanation: selected.map((item) => item.explanation.trim()).filter(Boolean).join('\n\n'),
    tags: Array.from(new Set(selected.flatMap((item) => item.tags))),
    linked_concepts: selected.flatMap((item) => item.linked_concepts || []),
    validation_issues: ['已人工合并，请复核题干边界'],
    duplicate_of: '',
    needs_review: true,
    ...(projection ? { projection, issues: [...new Map(selected.flatMap(c => c.issues || []).map(i => [i.key, i])).values()] } : {}),
    review: null,
  };
  const reviewedMerged = editCandidate(merged, { projection: merged.projection ? { ...merged.projection } : undefined });
  const remaining = candidates.filter((item) => !selectedIds.has(item.id));
  remaining.splice(Math.max(0, firstIndex), 0, reviewedMerged);
  return { candidates: remaining, merged: reviewedMerged };
}

export function splitCandidateAtBlankLine(
  candidate: ExerciseCandidate,
  suffix: string,
): ExerciseCandidate[] | null {
  const boundary = candidate.question_text.search(/\n\s*\n/);
  if (boundary < 0) return null;
  const left = candidate.question_text.slice(0, boundary).trim();
  const right = candidate.question_text.slice(boundary).trim();
  if (!left || !right) return null;
  return [
    { ...editCandidate(candidate, { question_text: left, answer: '', explanation: '' }), id: `${candidate.id}-${suffix}-1`, review: null, duplicate_of: '', validation_issues: ['拆分后请复核题干边界，源解保留在另一子题及来源中'] },
    { ...editCandidate(candidate, { question_text: right }), id: `${candidate.id}-${suffix}-2`, review: null, duplicate_of: '', validation_issues: ['拆分后请复核题干边界'] },
  ];
}
