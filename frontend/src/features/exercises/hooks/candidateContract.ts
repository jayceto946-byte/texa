import type { ExerciseCandidate, CandidateIssue, CandidateProjection, CandidateReview } from '../../../types';

export const issueLabels: Record<string, string> = {
  solution_in_stem: '题干可能混有答案，请检查', boundary_uncertain: '请检查题目是否完整、配图是否正确',
  missing_required_input: '题目条件不完整', dependency_uncertain: '请检查配图是否属于本题', formula_review: '请检查公式和表格',
  source_unavailable: '原文件暂时无法读取，请重新导入', edited_content: '已编辑，建议核对',
  source_ocr_damage: '原文有未识别文字，请补全或删去有问题的部分',
  ai_content_correction: 'AI修改了来源文字或公式，请对照原文核对',
  missing_concepts: '尚未识别知识点', unknown_type: '题型待补充', difficulty_hint: '难度建议', duplicate: '重复题', legacy_notice: '题目属性提示',
  learned_boundary: '请检查题干与答案是否分开', answer_pairing_uncertain: '答案尚未找到对应题目，请检查题号',
};
export function issueLabel(item: ExerciseCandidate, issue: CandidateIssue) {
  const dep = item.projection?.dependencies.find(d => d.id === issue.dependency_id);
  return issue.code === 'missing_required_input' && dep?.kind === 'figure'
    ? `缺少${dep.label}，请补图或修改题干`
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
export const canImportCandidate = (item: ExerciseCandidate) => Boolean(item.question_text.trim());
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
  const delivered = new Set(p.dependencies.filter(d => d.kind === 'figure' && d.resolution === 'embedded' && d.asset_ids.length).map(d => d.label));
  if (figureLabels(item.question_text).some(label => !delivered.has(label))) return false;
  return contentIssues(item).every(i => {
    const decision = decisions[i.key];
    if (!item.review || !decision || i.code === 'source_unavailable') return false;
    if (i.code === 'missing_required_input') {
      const dep = p.dependencies.find(d => d.id === i.dependency_id);
      return p.method === 'user_edited' && (dep?.kind === 'figure'
        ? dep.requirement === 'reference' && decision === 'not_applicable'
        : dep?.kind === 'prior_context' && dep.resolution === 'embedded' && decision === 'corrected' && !/前例|上例|例\s*\d+(?:[.．]\d+)+\s*中|上述(?:条件|参数)/.test(item.question_text));
    }
    return ['edited_content', 'solution_in_stem', 'boundary_uncertain', 'dependency_uncertain', 'formula_review', 'learned_boundary', 'source_ocr_damage', 'ai_content_correction'].includes(i.code);
  });
}
export function mergeProjections(projections: CandidateProjection[]): CandidateProjection | null {
  const first = projections[0];
  const split=first.split;
  if (projections.some(p=>p.split) && (!split || projections.some(p=>p.split?.group_id!==split.group_id) || new Set(projections.map(p=>p.split?.index)).size!==split.siblings.length)) return null;
  if (new Set(projections.map(p => p.structure?.catalog_number).filter(Boolean)).size > 1) return null;
  if (new Set(projections.map(p => p.structure?.authored_focus).filter(Boolean)).size > 1) return null;
  if (projections.some(p => p.canonical_hash !== first.canonical_hash || p.source_id !== first.source_id || p.profile_version !== first.profile_version || canonicalJson(p.scope) !== canonicalJson(first.scope))) return null;
  const spans = <T,>(values: T[]) => [...new Map(values.map(v => [canonicalJson(v), v])).values()];
  return { ...first, ...(split?{split:undefined}:{}), method: 'user_edited', unit_ids: [...new Set(projections.flatMap(p => p.unit_ids))],
    parts: { question: spans(projections.flatMap(p => p.parts.question)), answer: spans(projections.flatMap(p => p.parts.answer)), explanation: spans(projections.flatMap(p => p.parts.explanation)), context: spans(projections.flatMap(p => p.parts.context)), unassigned: spans(projections.flatMap(p => p.parts.unassigned)) },
    dependencies: [...new Map(projections.flatMap(p => p.dependencies).map(d => [d.id, d])).values()],
    excluded_figure_ids: [...new Set(projections.flatMap(p => p.excluded_figure_ids || []))] };
}
