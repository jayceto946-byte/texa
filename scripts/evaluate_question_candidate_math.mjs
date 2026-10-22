/** All three candidate body slots and source context. No source tokens leave local artifacts. */
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const req=createRequire(resolve('frontend/package.json'));
const {unified}=await import(pathToFileURL(req.resolve('unified')));
const {default:remarkParse}=await import(pathToFileURL(req.resolve('remark-parse')));
const {default:remarkMath}=await import(pathToFileURL(req.resolve('remark-math')));
const katex=req('katex');
const {prepareMathMarkdown}=await import(pathToFileURL(resolve('frontend/src/utils/mathText.ts')));
const {readingMathMarkdown}=await import(pathToFileURL(resolve('frontend/src/features/reading/readingMath.ts')));
const rows=JSON.parse(readFileSync('artifacts/question-candidate-contract/candidates.private.json'));
const old=JSON.parse(readFileSync('artifacts/question-extraction-quality-2026-10-17/math-probe.private.json'));
const blocks=new Map(rows.extract.source_blocks.map(b=>[b.block_id,b]));
const compact=s=>s.replace(/\s/g,'');
const output=rows.data.map((c,i)=>{
 const slots={};
 for(const key of ['question_text','answer','explanation']){
  const tree=unified().use(remarkParse).use(remarkMath).parse(prepareMathMarkdown(readingMathMarkdown(c[key])));
  const nodes=[];const walk=n=>{if(['math','inlineMath'].includes(n.type))nodes.push(n);for(const child of n.children||[])walk(child)};walk(tree);
  const errors=[];for(const node of nodes){try{katex.renderToString(node.value,{displayMode:node.type==='math',throwOnError:true})}catch(e){errors.push(String(e))}}
  slots[key]={nodes,errors};
 }
 const formulas=[];
 for(const [role,spans]of Object.entries(c.projection.parts))for(const span of spans){
  const b=blocks.get(span.block_id);if(b.block_type!=='formula')continue;
  const key=role==='answer'?'answer':role==='explanation'?'explanation':'question_text';
  const matched=slots[key].nodes.find(n=>compact(n.value)===compact(b.text));
  formulas.push({block_id:b.block_id,role,source_tokens_preserved:c[key].includes(b.text),exact_math_node:!!matched,display:matched?.type==='math',source_truth:'UNKNOWN'});
 }
 return {audit_id:`C${String(i+1).padStart(3,'0')}`,before_errors:old[i].katex_errors.length,after_errors:Object.values(slots).reduce((n,v)=>n+v.errors.length,0),before_unrecognized:old[i].formula_blocks_not_exact_math_nodes,formulas};
});
const summary={scope:'representation only; no OCR/math truth claim',formula_occurrences:output.reduce((n,r)=>n+r.formulas.length,0),source_tokens_preserved:output.every(r=>r.formulas.every(f=>f.source_tokens_preserved)),before_errors:output.reduce((n,r)=>n+r.before_errors,0),after_errors:output.reduce((n,r)=>n+r.after_errors,0),before_unrecognized:output.reduce((n,r)=>n+r.before_unrecognized.length,0),after_unrecognized:output.reduce((n,r)=>n+r.formulas.filter(f=>!f.exact_math_node).length,0),rows:output.filter(r=>r.formulas.length||r.before_errors)};
writeFileSync('docs/validation/question-candidate-contract-2026-10-18/math-representation.json',JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify(Object.fromEntries(Object.entries(summary).filter(([k])=>k!=='rows'))));
