import { useCallback, useMemo, useState } from 'react';
import type { ExerciseCandidate, CandidateSourceRegistry } from '../../../types';
import { candidateHash, contentJson, editCandidate, canSubmitCandidate, type Decisions } from './candidateContract';
import { assignSourceSuffix } from './sourceAssignment';
import {
  filterCandidates,
  mergeSelectedCandidates as mergeSelected,
  splitCandidateAtBlankLine,
  summarizeCandidates,
  type CandidateFilter,
} from './candidateOperations';


interface UseExerciseImportCandidatesOptions {
  onMessage: (message: string) => void;
}

export function useExerciseImportCandidates({ onMessage }: UseExerciseImportCandidatesOptions) {
  const [sourceRegistry, setSourceRegistry] = useState<CandidateSourceRegistry | null>(null);
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, Decisions>>({});
  const [confirmingId, setConfirmingId] = useState('');
  const [candidates, setCandidates] = useState<ExerciseCandidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [candidateFilter, setCandidateFilter] = useState<CandidateFilter>('all');
  const [editingCandidateId, setEditingCandidateId] = useState('');

  const importSummary = useMemo(() => summarizeCandidates(candidates), [candidates]);
  const filteredCandidates = useMemo(() => filterCandidates(candidates, candidateFilter), [candidateFilter, candidates]);

  const submittableCandidates = useMemo(() => candidates.filter(c => selectedIds.has(c.id) && canSubmitCandidate(c) && (!c.projection || sourceRegistry?.canonical_hash === c.projection.canonical_hash)), [candidates, selectedIds, sourceRegistry]);

  const resetImportCandidates = useCallback(() => {
    setCandidates([]);
    setSourceRegistry(null);
    setReviewDecisions({});
    setEditingCandidateId('');
    setSelectedIds(new Set());
  }, []);

  const replaceCandidates = useCallback((next: ExerciseCandidate[], registry: CandidateSourceRegistry | null = null) => {
    setSourceRegistry(registry);
    setReviewDecisions({});
    setEditingCandidateId('');
    setCandidates(next);
    setSelectedIds(new Set(next.map((item) => item.id)));
  }, []);

  const removeSelectedCandidates = useCallback(() => {
    setCandidates((current) => current.filter((item) => !selectedIds.has(item.id)));
    setSelectedIds(new Set());
  }, [selectedIds]);

  const removeCommittedCandidates = useCallback((ids: ReadonlySet<string>) => {
    setCandidates(current => current.filter(c => !ids.has(c.id)));
    setSelectedIds(current => new Set([...current].filter(id => !ids.has(id))));
  }, []);

  const selectAllCandidates = useCallback(() => {
    setSelectedIds(new Set(candidates.map((item) => item.id)));
  }, [candidates]);

  const clearCandidateSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);
  const updateCandidate = useCallback((id: string, updates: Partial<ExerciseCandidate>) => {
    if (['question_text', 'answer', 'explanation', 'projection'].some(key => key in updates)) setReviewDecisions(current => ({ ...current, [id]: {} }));
    setCandidates((items) => items.map((item) => item.id === id ? editCandidate(item, updates) : item));
  }, []);

  const assignSource = useCallback((candidate: ExerciseCandidate, blockId: string, offset: number, role: 'question' | 'answer' | 'explanation' | 'context') => {
    if (!sourceRegistry) return;
    const updated = assignSourceSuffix(candidate, sourceRegistry, blockId, offset, role);
    setReviewDecisions(current => ({ ...current, [candidate.id]: {} }));
    setCandidates(items => items.map(c => c.id === candidate.id ? updated : c));
  }, [sourceRegistry]);

  const chooseResolution = useCallback((candidate: ExerciseCandidate, issueKey: string, decision: Decisions[string]) => {
    const issue = candidate.issues?.find(i => i.key === issueKey);
    if (issue?.code === 'missing_required_input' && candidate.projection) {
      const projection = { ...candidate.projection, dependencies: candidate.projection.dependencies.map(d => d.id !== issue.dependency_id ? d : d.kind === 'figure' && decision === 'not_applicable' ? { ...d, requirement: 'reference' as const } : d.kind === 'prior_context' && decision === 'corrected' ? { ...d, resolution: 'embedded' as const } : d) };
      setCandidates(items => items.map(c => c.id === candidate.id ? editCandidate(c, { projection }) : c));
    } else {
      setCandidates(items => items.map(c => c.id === candidate.id ? c.projection?.method === 'unresolved' ? editCandidate(c, { projection: { ...c.projection, method: 'user_edited' } }) : { ...c, review: null } : c));
    }
    setReviewDecisions(current => ({ ...current, [candidate.id]: { ...current[candidate.id], [issueKey]: decision } }));
  }, []);

  const confirmCandidate = useCallback(async (candidate: ExerciseCandidate) => {
    const frozen = contentJson(candidate);
    const decisions = { ...(reviewDecisions[candidate.id] || {}), ...(candidate.projection?.method === 'user_edited' ? { 'edited_content:': 'corrected' as const } : {}) };
    const resolutions = Object.entries(decisions).map(([issue_key, decision]) => ({ issue_key, decision }));
    setConfirmingId(candidate.id);
    try {
      const hash = await candidateHash(candidate);
      setCandidates(items => items.map(c => c.id === candidate.id && contentJson(c) === frozen ? { ...c, review: { content_hash: hash, resolutions } } : c));
    } catch { onMessage('当前环境无法生成确认摘要，请保持候选并重试'); }
    finally { setConfirmingId(''); }
  }, [onMessage, reviewDecisions]);

  const mergeSelectedCandidates = useCallback(() => {
    const result = mergeSelected(candidates, selectedIds);
    if (!result) {
      onMessage('请至少选择两道相邻候选题进行合并');
      return;
    }
    setReviewDecisions({});
    setCandidates(result.candidates);
    setSelectedIds(new Set([result.merged.id]));
    setEditingCandidateId(result.merged.id);
  }, [candidates, onMessage, selectedIds]);

  const splitCandidate = useCallback((candidate: ExerciseCandidate) => {
    const parts = splitCandidateAtBlankLine(candidate, Date.now().toString(36));
    if (!parts) {
      onMessage('请先在题干编辑框中用空行标出拆分位置');
      setEditingCandidateId(candidate.id);
      return;
    }
    setReviewDecisions({});
    setCandidates((current) => {
      const index = current.findIndex((item) => item.id === candidate.id);
      const next = current.filter((item) => item.id !== candidate.id);
      next.splice(Math.max(0, index), 0, ...parts);
      return next;
    });
    setSelectedIds(new Set(parts.map((item) => item.id)));
    setEditingCandidateId(parts[0].id);
  }, [onMessage]);

  const toggleCandidate = useCallback((id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  return {
    candidates,
    sourceRegistry,
    submittableCandidates,
    reviewDecisions,
    chooseResolution,
    confirmCandidate,
    confirmingId,
    removeCommittedCandidates,
    selectedIds,
    candidateFilter,
    setCandidateFilter,
    editingCandidateId,
    setEditingCandidateId,
    importSummary,
    filteredCandidates,
    resetImportCandidates,
    updateCandidate,
    assignSource,
    replaceCandidates,
    removeSelectedCandidates,
    selectAllCandidates,
    clearCandidateSelection,
    mergeSelectedCandidates,
    splitCandidate,
    toggleCandidate,
  };
}
