import type { CandidateProjection, CandidateSourceRegistry, CandidateSpan, ExerciseCandidate } from '../../../types';
import { editCandidate } from './candidateContract';

type Role = keyof CandidateProjection['parts'];
export function assignSourceSuffix(candidate: ExerciseCandidate, registry: CandidateSourceRegistry, blockId: string, utf16Offset: number, role: Role): ExerciseCandidate {
  const projection = candidate.projection;
  const block = registry.source_blocks.find(b => b.block_id === blockId);
  if (!projection || !block) return candidate;
  const offset = Array.from(block.text.slice(0, utf16Offset)).length;
  const length = Array.from(block.text).length;
  if (offset >= length) return candidate;
  const parts = Object.fromEntries(Object.entries(projection.parts).map(([key, spans]) => [key, spans.flatMap(span => {
    if (span.block_id !== blockId || (span.end ?? length) <= offset) return [span];
    return span.start < offset ? [{ ...span, end: offset }] : [];
  })])) as CandidateProjection['parts'];
  parts[role].push({ block_id: blockId, start: offset, end: null });
  parts.question.push(...parts.unassigned);
  parts.unassigned = [];
  const order = new Map(registry.source_blocks.map(b => [b.block_id, b.order]));
  const serialize = (spans: CandidateSpan[]) => spans.sort((a, b) => (order.get(a.block_id)! - order.get(b.block_id)!) || a.start - b.start).map(span => {
    const source = registry.source_blocks.find(b => b.block_id === span.block_id)!;
    let text = Array.from(source.text).slice(span.start, span.end ?? undefined).join('');
    if (source.block_type === 'formula' && span.start === 0 && span.end === null && !text.trim().startsWith('$$') && !(text.includes('\\mathrm') && !/\\(?:tag|frac|begin|sum|int|sqrt)\b|\$/.test(text))) text = `$$\n${text}\n$$`;
    return text.trim() ? text : '';
  }).filter(Boolean).join('\n\n');
  return editCandidate(candidate, { projection: { ...projection, parts },
    question_text: serialize(parts.question), answer: serialize(parts.answer), explanation: serialize(parts.explanation), duplicate_of: '' });
}
