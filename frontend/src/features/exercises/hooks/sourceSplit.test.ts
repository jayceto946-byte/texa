import { describe,expect,it } from 'vitest';
import type { CandidateSourceRegistry,ExerciseCandidate,CandidateProjection } from '../../../types';
import { splitSourceCandidate } from './sourceSplit';
import { canSubmitCandidate } from './candidateContract';

function fixture() {
  const text='第一问😀，条件 $x>0$。\n\n第二问，条件 $y<0$。';
  const raw={block_id:'raw',block_type:'paragraph',text,order:0,section_path:[],page_start:1,page_end:1,bbox:null,equations:[],table_title:'',table_header:[],table_rows:[],source_kind:'fixture',review_status:'',attributes:{}};
  const registry: CandidateSourceRegistry={canonical_hash:'a'.repeat(64),source_blocks:[raw,{...raw,block_id:'solution',text:'解：给出原书解答。',order:1}],units:[]};
  const parts: CandidateProjection['parts']={question:[{block_id:'raw',start:0,end:null}],answer:[],explanation:[{block_id:'solution',start:0,end:null}],context:[],unassigned:[]};
  const p: CandidateProjection={version:1,canonical_hash:registry.canonical_hash,unit_ids:['raw'],scope:{chapter:'',page_start:null,page_end:null,source_mode:'file'},method:'block_boundary',parts,dependencies:[],profile_version:'',source_id:'a'.repeat(32)};
  const c: ExerciseCandidate={id:'c',question_text:text,answer:'',explanation:'解：给出原书解答。',projection:p,issues:[],review:null,source:'fixture',subject:'数学',chapter:'',suggested_type:'计算题',difficulty:3,tags:[],confidence:0.5,reasons:[],needs_llm:false,needs_review:true};
  return {c,registry};
}

describe('source partition when splitting',()=> {
  it('uses Unicode source intervals and explicitly assigns original solutions',()=> {
    const {c,registry}=fixture();
    const [a,b]=splitSourceCandidate(c,'test',registry,{solution:'left',blocks:{}});
    expect(a.explanation).toBe(c.explanation);expect(b.explanation).toBe('');
    expect(a.question_text).toContain('😀');expect(b.question_text).toContain('$y<0$');
    expect(a.projection!.parts.question[0].end).toBe(b.projection!.parts.question[0].start);
    expect(a.projection!.parts.question).not.toEqual(b.projection!.parts.question);
    expect(a.projection!.split!.siblings).toEqual(b.projection!.split!.siblings);
    expect([a,b].every(c=>!canSubmitCandidate(c) && c.review===null)).toBe(true);
  });
  it('retains unresolved edits and requires a solution owner',()=> {
    const {c,registry}=fixture();
    expect(()=>splitSourceCandidate(c,'test',registry,{solution:'',blocks:{}})).toThrow('指定原答案');
    expect(()=>splitSourceCandidate({...c,question_text:c.question_text.replace('x>0','x<0')},'test',registry,{solution:'right',blocks:{}})).toThrow('尚未对齐');
    expect(c.question_text).toContain('x>0');
  });
  it('shares figure pixels only by an explicit assignment',()=> {
    const {c,registry}=fixture();const block={...registry.source_blocks[0],block_id:'figure',block_type:'figure',text:'图1.1',order:2};registry.source_blocks.push(block);
    c.question_text+='\n\n图1.1';c.projection!.parts.question.push({block_id:'figure',start:0,end:null});
    const [a,b]=splitSourceCandidate(c,'test',registry,{solution:'right',blocks:{figure:'both'}});
    expect(a.projection!.parts.question.some(s=>s.block_id==='figure')).toBe(true);
    expect(b.projection!.parts.question.some(s=>s.block_id==='figure')).toBe(true);
    expect(a.projection!.split!.shared_block_ids).toEqual(['figure']);
  });
  it('partitions two original solutions without copying either into both children',()=> {
    const {c,registry}=fixture();
    c.explanation='解：第一问的原解。\n\n解：第二问的原解。';registry.source_blocks[1].text=c.explanation;
    const [a,b]=splitSourceCandidate(c,'test',registry,{solution:'separate',blocks:{}});
    expect(a.explanation).toContain('第一问');expect(a.explanation).not.toContain('第二问');
    expect(b.explanation).toContain('第二问');expect(b.explanation).not.toContain('第一问');
    expect(a.projection!.parts.explanation[0].end).toBe(b.projection!.parts.explanation[0].start);
  });
});
