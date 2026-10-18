import type { ExerciseCandidate, CandidateIssue, CandidateProjection, CandidateReview } from '../../../types';

export const issueLabels: Record<string, string> = {
  solution_in_stem: '题干可能混有解答，请对照并分离', boundary_uncertain: '题目边界或附图归属待核对',
  missing_required_input: '缺少独立练习所需输入', dependency_uncertain: '资源关系待核对', formula_review: '公式或源表与解答需对照核对',
  source_unavailable: '来源不可回查，请重新分析', edited_content: '正文已修改，请确认本题结构',
  missing_concepts: '尚未识别知识点', unknown_type: '题型待补充', difficulty_hint: '难度建议', duplicate: '重复题', legacy_notice: '题目属性提示',
};
export function issueLabel(item: ExerciseCandidate, issue: CandidateIssue) {
  const dep = item.projection?.dependencies.find(d => d.id === issue.dependency_id);
  return issue.code === 'missing_required_input' && dep?.kind === 'figure'
    ? `${dep.label}已在来源${dep.block_ids.length ? '定位' : '查找，尚未找到'}，独立练习尚不可读取`
    : `${issueLabels[issue.code] || '内容待核对'}${dep?.label ? `（${dep.label}）` : ''}`;
}
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalJson((value as Record<string, unknown>)[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
type CandidateBody = Pick<ExerciseCandidate, 'question_text' | 'answer' | 'explanation'> & Partial<Pick<ExerciseCandidate, 'projection'>>;
export function contentJson(item: CandidateBody, includeProjection = true) {
  return canonicalJson({ question_text: item.question_text, answer: item.answer, explanation: item.explanation, ...(includeProjection ? { projection: item.projection ?? null } : {}) });
}
export async function candidateHash(item: CandidateBody, includeProjection = true) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(contentJson(item, includeProjection)));
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
}
export const contentIssues = (item: ExerciseCandidate) => (item.issues || []).filter(i => i.category === 'content');
export const editedIssue: CandidateIssue = { key: 'edited_content:', category: 'content', code: 'edited_content', block_ids: [], dependency_id: null };
export function editCandidate(item: ExerciseCandidate, updates: Partial<ExerciseCandidate>): ExerciseCandidate {
  const changed = (['question_text', 'answer', 'explanation', 'projection'] as const).some(k => k in updates && updates[k] !== item[k]);
  const next = { ...item, ...updates };
  if (!changed || !next.projection) return next;
  return { ...next, review: null, projection: { ...next.projection, method: 'user_edited' }, issues: [...(next.issues || []).filter(i => i.code !== 'edited_content'), editedIssue] };
}
export type Decisions = Record<string, CandidateReview['resolutions'][number]['decision']>;
const figureLabels = (text: string) => Array.from(text.matchAll(/图\s*([A-Za-z]|\d+(?:\s*[.．-]\s*\d+)+)/g), m => '图' + m[1].replace(/\s/g, '').replace(/[．-]/g, '.'));
export function canSubmitCandidate(item: ExerciseCandidate): boolean {
  if (!item.question_text.trim()) return false;
  if (!item.projection) return true; // File/manual import retains the legacy contract.
  const p = item.projection;
  if (!item.issues || p.method === 'unresolved') return false;
  const decisions = Object.fromEntries((item.review?.resolutions || []).map(r => [r.issue_key, r.decision]));
  if (p.method === 'user_edited' && (!item.review || decisions['edited_content:'] !== 'corrected')) return false;
  if (figureLabels(item.question_text).length) return false; // F3 is not delivered.
  return contentIssues(item).every(i => {
    const decision = decisions[i.key];
    if (!item.review || !decision || i.code === 'source_unavailable') return false;
    if (i.code === 'missing_required_input') {
      const dep = p.dependencies.find(d => d.id === i.dependency_id);
      return p.method === 'user_edited' && (dep?.kind === 'figure'
        ? dep.requirement === 'reference' && decision === 'not_applicable'
        : dep?.kind === 'prior_context' && dep.resolution === 'embedded' && decision === 'corrected' && !/前例|上例|例\s*\d+(?:[.．]\d+)+\s*中|上述(?:条件|参数)/.test(item.question_text));
    }
    return ['edited_content', 'solution_in_stem', 'boundary_uncertain', 'dependency_uncertain', 'formula_review'].includes(i.code);
  });
}
export function mergeProjections(projections: CandidateProjection[]): CandidateProjection | null {
  const first = projections[0];
  if (projections.some(p => p.canonical_hash !== first.canonical_hash || canonicalJson(p.scope) !== canonicalJson(first.scope))) return null;
  const spans = <T,>(values: T[]) => [...new Map(values.map(v => [canonicalJson(v), v])).values()];
  return { ...first, method: 'user_edited', unit_ids: [...new Set(projections.flatMap(p => p.unit_ids))],
    parts: { question: spans(projections.flatMap(p => p.parts.question)), answer: spans(projections.flatMap(p => p.parts.answer)), explanation: spans(projections.flatMap(p => p.parts.explanation)), context: spans(projections.flatMap(p => p.parts.context)), unassigned: spans(projections.flatMap(p => p.parts.unassigned)) },
    dependencies: [...new Map(projections.flatMap(p => p.dependencies).map(d => [d.id, d])).values()] };
}
