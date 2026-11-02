import type { CandidateProjection, CandidateSourceRegistry, CandidateSpan, ExerciseCandidate } from '../../../types';
import { editCandidate } from './candidateContract';

type Parts = CandidateProjection['parts'];
export type SplitAssignment = { solution: 'left' | 'right' | 'separate' | ''; blocks: Record<string, 'left' | 'right' | 'both'> };
const empty = (): Parts => ({ question: [], answer: [], explanation: [], context: [], unassigned: [] });
const compact = (value: string) => Array.from(value).filter(c => !/\s/.test(c)).join('');

export function splitSourceCandidate(candidate: ExerciseCandidate, suffix: string, registry: CandidateSourceRegistry, assignment: SplitAssignment): ExerciseCandidate[] {
  const p = candidate.projection!;
  const boundary = candidate.question_text.search(/\n\s*\n/);
  if (boundary < 0) throw Error('请先用空行标出拆分位置');
  if ((candidate.answer || candidate.explanation) && !assignment.solution) throw Error('请先指定原答案与解析属于哪道子题');
  const byId = new Map(registry.source_blocks.map(b => [b.block_id, b]));
  const raw = (s: CandidateSpan) => Array.from(byId.get(s.block_id)!.text).slice(s.start, s.end ?? undefined).join('');
  const display = (s: CandidateSpan) => {
    const b = byId.get(s.block_id)!; const text = raw(s);
    if (s.start===0 && s.end===null && b.display_text!==undefined) return b.display_text;
    return b.block_type === 'formula' && !text.trim().startsWith('$') ? `$$\n${text}\n$$` : text;
  };
  const spans = [...p.parts.question, ...p.parts.unassigned].sort((a,b) => byId.get(a.block_id)!.order - byId.get(b.block_id)!.order || a.start-b.start);
  if (compact(p.parts.answer.map(display).join('\n\n'))!==compact(candidate.answer) || compact(p.parts.explanation.map(display).join('\n\n'))!==compact(candidate.explanation)) throw Error('编辑后的原解尚未对齐来源，请先核对原解再拆分');
  if (compact(spans.map(display).join('\n\n')) !== compact(candidate.question_text)) throw Error('编辑后的题干尚未对齐原文，请保留当前内容，先核对原文再拆分');
  const partition=(source: CandidateSpan[],value: string,cut: number): [CandidateSpan[],CandidateSpan[]]=> {
    let remaining=Array.from(compact(value.slice(0,cut))).length;
    const first: CandidateSpan[]=[],second: CandidateSpan[]=[];
    for (const span of source) {
      const text=display(span),length=Array.from(compact(text)).length;
      if (remaining>=length) {first.push({...span});remaining-=length;}
      else if (remaining===0) second.push({...span});
      else {
        if (compact(text)!==compact(raw(span))) throw Error('拆分位置落在公式或表格内，请把空行放到完整公式或表格之后');
        const chars=Array.from(raw(span));let count=0,offset=0;
        for(;offset<chars.length;offset++){if(!/\s/.test(chars[offset]))count++;if(count===remaining){offset++;break;}}
        first.push({...span,end:span.start+offset});second.push({...span,start:span.start+offset});remaining=0;
      }
    }
    if(!first.length||!second.length)throw Error('拆分位置两侧都需要完整来源');
    return [first,second];
  };
  const left=empty(),right=empty();
  [left.question,right.question]=partition(spans,candidate.question_text,boundary);
  if(assignment.solution==='separate') {
    for(const role of ['answer','explanation'] as const) if(candidate[role]) {
      const cut=candidate[role].search(/\n\s*\n/);
      if(cut<0)throw Error('请先在答案和解析中用空行标出两题的分界，再选择分别分配');
      [left[role],right[role]]=partition(p.parts[role],candidate[role],cut);
    }
  } else {
    const solution=assignment.solution==='left'?left:right;
    solution.answer=[...p.parts.answer];solution.explanation=[...p.parts.explanation];
  }
  // Ordinary source context is retained with the first child; sharing is explicit.
  left.context=[...p.parts.context];
  const shared=new Set(p.split?.shared_block_ids || []);
  for (const [bid,owner] of Object.entries(assignment.blocks)) {
    const current=[left,right].flatMap(parts => Object.values(parts).flat()).find(s => s.block_id===bid);
    if (!current) continue;
    let role: keyof Parts='question';
    for (const parts of [left,right]) for (const key of Object.keys(parts) as Array<keyof Parts>) {
      if (parts[key].some(s=>s.block_id===bid)) role=key;
      parts[key]=parts[key].filter(s=>s.block_id!==bid);
    }
    if (owner==='left' || owner==='both') left[role].push({...current});
    if (owner==='right' || owner==='both') right[role].push({...current});
    if (owner==='both') shared.add(bid); else shared.delete(bid);
  }
  const previous=p.split;const index=previous?.index || 0;
  const plans=previous ? [...previous.siblings.slice(0,index),left,right,...previous.siblings.slice(index+1)] : [left,right];
  for(const bid of [...shared]) if(plans.filter(part=>Object.values(part).flat().some(s=>s.block_id===bid)).length<2) shared.delete(bid);
  for(const bid of previous?.shared_block_ids||[]) if(plans.filter(part=>Object.values(part).flat().some(s=>s.block_id===bid)).length>1) shared.add(bid);
  if (plans.length>20) throw Error('同一来源最多拆为20道子题，请分批校对');
  const serialize=(values: CandidateSpan[])=>[...values].sort((a,b)=>byId.get(a.block_id)!.order-byId.get(b.block_id)!.order||a.start-b.start).map(display).filter(t=>t.trim()).join('\n\n');
  return [left,right].map((parts,i)=> {
    const ids=new Set(Object.values(parts).flat().map(s=>s.block_id));
    const projection: CandidateProjection={...p,parts,dependencies:p.dependencies.filter(d=>!d.block_ids.length||d.block_ids.some(b=>ids.has(b))),
      ...(p.excluded_figure_ids ? {excluded_figure_ids:p.excluded_figure_ids.filter(b=>ids.has(b))} : {}),
      split:{group_id:previous?.group_id || `split-${candidate.id}-${suffix}`,index:index+i,siblings:plans,shared_block_ids:[...shared]}};
    const value=editCandidate(candidate,{question_text:serialize(parts.question).trim(),answer:serialize(parts.answer),explanation:serialize(parts.explanation),projection});
    return {...value,id:`${candidate.id}-${suffix}-${i+1}`,review:null,duplicate_of:'',issues:value.issues?.filter(issue=>!issue.block_ids.length||issue.block_ids.some(b=>ids.has(b)))};
  });
}
