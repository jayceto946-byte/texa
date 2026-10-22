/** Audit-only parity probe: existing preprocessing + remark-math AST + installed KaTeX.
 * This checks representation, not mathematical truth or Electron visual layout. */
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
const work=resolve(process.argv[2]);
const rows=JSON.parse(readFileSync(resolve(work,'candidates.private.json')));
const compact=text=>text.replace(/\s/g,'');
const output=rows.map(row=>{
 const processor=unified().use(remarkParse).use(remarkMath);
 const tree=processor.parse(prepareMathMarkdown(readingMathMarkdown(row.candidate.question_text)));
 const math=[];
 const walk=node=>{if(['math','inlineMath'].includes(node.type))math.push(node);for(const child of node.children||[])walk(child)};walk(tree);
 const errors=[];
 for(const node of math){try{katex.renderToString(node.value,{displayMode:node.type==='math',throwOnError:true})}catch(error){errors.push({kind:node.type,message:error.message,tex:node.value})}}
 const unrecognized=row.source_blocks.filter(x=>x.canonical.block_type==='formula'&&!math.some(node=>compact(node.value)===compact(x.canonical.text))).map(x=>x.canonical.block_id);
 return {audit_id:row.audit_id,math_nodes:math.length,katex_errors:errors,formula_blocks_not_exact_math_nodes:unrecognized};
});
writeFileSync(resolve(work,'math-probe.private.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify(output.filter(x=>x.katex_errors.length||x.formula_blocks_not_exact_math_nodes.length).map(x=>({audit_id:x.audit_id,errors:x.katex_errors.length,unrecognized_formula_blocks:x.formula_blocks_not_exact_math_nodes.length})),null,2));
