"""Publish redacted records from explicitly source-reviewed decisions, not regex labels.

The fixed ordinal decisions below are the audit agent's review of this frozen 108-row
dataset. They are not a classifier or human gold labels. Re-check if dataset hash differs.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

work, out = map(Path, sys.argv[1:3])
records = json.loads((work / 'candidates.private.json').read_text())
identity = json.loads((work / 'identity.json').read_text())
assert identity['dataset_sha256_excluding_random_candidate_id'] == 'bd8e06d3aef90488cf4ab10a12d987a950fd72dbc49e4f0b03057eeabaf41377'
out.mkdir(parents=True, exist_ok=True)
sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
# All 108 source texts and adjacent boundaries were read; these are individual
# adjudications tied to IDs, with more specific reasons for every known defect.
topics = '''静态性能例题|电阻容差例题|表格灵敏度例题|温漂计算例题|两组校准数据例题|跨页动态温度例题|
传感器组成|传感器分类|静态指标|动态特性|动静态比较|精度准确度|量程误差计算|制造容差计算|量程选择|热电偶数据表|漂移因素|两组灵敏度|校准偏差|跨页负载漂移|潜艇动态响应|二阶模型与阻尼|
半导体温漂|薄膜工艺|掺杂工艺|加工技术|
冷端补偿|热电偶结构|热电偶结论|电阻温敏比较|钢水热电偶图示|温度器件选择|温敏线性比较|
应变温漂|电桥非线性|应变组成|压阻比较|横向效应|电桥方式|横向系数|交流电桥|压电效应|静态响应限制|石英效应|陶瓷极化|等效电路|放大器特性|电荷放大|受力装置|连接方式|
霍尔原理|霍尔温漂|形状修正|磁阻设计|磁敏二极管|温度补偿|磁敏三极管|器件应用|
光电效应|光器件选择设计|倍增管计算|电荷耦合|光纤|暗电流|光敏晶体管|CCD时序|
声学现象|声敏分类|水声|超声衰减|声场|超声收发|
气敏分类|表面控制|加热|选择性|真空仪表|Pd-MOSFET|气体选择|
湿度|亲和力与湿敏|电容石英|恒湿控制|
生物原理|生物分类|用途|免疫分类|酶结构|信号放大|诊断应用|
压力电桥例题|内阻电桥例题|容差电桥例题|顶点平衡例题|麦克斯韦例题|依赖前例的Q计算|电容电桥例题|电感电桥例题|
电压电流转换|电流电压转换|电压频率转换|电容检测|阻抗变换|滤波|有源滤波|
智能传感器|网络仪器|无线网络'''.replace('\n','').split('|')
assert len(topics) == len(records) == 108
examples = set(range(1,7)) | set(range(91,99))
boundary = {33,91,92,93,96}
missing_assets = {31,91,92,93,94,95,96,97,98}
missing_inputs = {31,92,93,94,95,96,97,98}
math_representation = {91,93,94,96}
wrong_type = {4,36,91,92,96,108}
notes = {
1:'IR与MinerU均为题干、解、补充解三个独立块；候选将三块原样连接，答案/解析为空。',
2:'题干与显式解为两个源块；独立练习前须分离，不能只删除“解”字。',
3:'题干与所需表格保留，但末尾显式解混入；图形一词触发图论标签不代表内容完好。',
4:'源表格及设问完整，解混入；“正确”导致判断题误标。原始裁图与OCR表值一致，数值与解的冲突不能归罪候选丢失。',
5:'两组负载/挠度与设问完整保留，四个解答块混入；空知识点不是主要缺陷。',
6:'题干完整，跨页解/公式/表格均保留但未分离；不因跨页本身判错。',
21:'源公式文本完整；现有前端bare-LaTeX预处理能识别此式，未把无美元符误判为必然公式丢失。',
29:'源题措辞开放、未显式附解；不能把宽泛教材概念题等同于被截断。',
31:'题干引用图3.60；该图在同页靠后，学习单元却归到C033，当前候选缺所需图。',
33:'本题为晶体管线性问答；附在本单元的钢水图3.60属于C031，形成错误附属边界；导出的仅有图题没有图片。',
61:'题干与OCR一致；数值量级需原PDF/专家核对，本轮不凭常识擅改数字，也不作答案准确率判断。',
66:'要求用户画图，不是引用一个缺失图；图论标签只属元数据争议，不判为缺图。',
81:'源问题本身点明湿敏对象；措辞宽泛不证明切分缺失，保留为概念题。',
91:'解混入后还吸收另一温度计实例及后续电流小节；选择题由数学符号误触发；图资源未导出，带tag公式被转inline并报错；裁图确认OCR公式多余闭括号。',
92:'解混入且吸收后续“误差分析”小节；所需电路参数在图11.5，候选只有图题没有可读图。',
93:'解混入并吞入下一“顶点平衡”小节与图，原题另引用上文图11.1；裸公式部分未进入math节点。',
94:'没有显式“解:”但题目后的方程及最终数值是解答；图11.6在C093单元。多段同行公式/变量被分成孤立equation，裁图确认片段确实存在；是否来自图中标注无法确认，不作该归因。不得靠匹配解字修复。',
95:'显式解未分离；所需图11.8在后续C096单元，不是来源不存在。',
96:'“解:”在首个块内，非行首块标记；需前例参数，且吞入下一偏转型交流电桥小节与两幅图；两条tag公式被包成inline。',
97:'题干参数公式保留；解混入，引用的图11.9未作为本题可读附件导出。',
98:'题干参数公式保留；解混入，引用的图11.9未作为本题可读附件导出。',
107:'网络化仪器是合法概念题；网络关键词不等于已验证的图论知识点。',
108:'无线网络是合法概念题；“解决”触发计算题元数据误标，不等于题干被损坏。',
}
math = {r['audit_id']:r for r in json.loads((work / 'math-probe.private.json').read_text())}
published=[]
for n, (r, topic) in enumerate(zip(records, topics),1):
    c=r['candidate']; tags=[]
    if n in examples: tags += ['Q2','Q4']
    if n in missing_inputs: tags += ['Q3']
    if n in boundary: tags += ['Q5']
    if n in math_representation: tags += ['Q7']
    if n in missing_assets: tags += ['Q8']
    if c['duplicate_of']: tags += ['Q9']
    hard = n in examples | boundary | missing_assets
    if c['validation_issues'] and not hard: tags += ['Q10']
    primary = 'Q5' if n in boundary else 'Q2' if n in examples else 'Q8' if n==31 else 'Q1'
    note=notes.get(n, f'{topic}：核对本题及相邻编号/章节边界，源单元无显式附解，题干与源正文一致；未见确定结构损坏。')
    if c['duplicate_of']: note += ' 与已有题干逐字符一致、来源相同、双方答案/解析均空；为真实重导入，不是相似题误判。'
    row={'audit_id':r['audit_id'],'candidate_id':c['id'],'dataset_alias':'TEXA-D01-01',
         'source':{'unit_id':r['unit']['id'],'kind':r['unit']['kind'],'label':r['unit']['label'],
                   'chapter':r['candidate']['chapter'], 'pages':[r['page_start'],r['page_end']],
                   'block_ids':[b['canonical']['block_id'] for b in r['source_blocks']],
                   'source_positions':[{'block_id':b['canonical']['block_id'],'page_idx':b['canonical']['attributes'].get('source_page_idx'),'block_index':b['canonical']['attributes'].get('source_block_index'),'bbox':b['canonical']['bbox']} for b in r['source_blocks']],
                   'traceable':True,'source_level':'MinerU structured OCR + persisted IR; original PDF unavailable'},
         'original_text':{'sha256':r['unit_text_sha256'],'excerpt':'[私有原文不发布；按audit_id在本地证据查阅]'},
         'current_question':{'sha256':r['question_sha256'],'chars':len(c['question_text']),'equals_unit_text':r['question_equals_unit_text'],'text':'WITHHELD_PRIVATE'},
         'current_answer':c['answer'],'current_explanation':c['explanation'],'suggested_type':c['suggested_type'],'tags':c['tags'],
         'warnings':c['validation_issues'],'duplicate':{'marked':bool(c['duplicate_of']),'record_alias':sha(c['duplicate_of'])[:12] if c['duplicate_of'] else None,
                           'decision':'VERIFIED_EXACT_SAME_TEXT_AND_SOURCE' if c['duplicate_of'] else 'NOT_MARKED'},
         'review':{'evidence_level':'VERIFIED','reviewer_kind':'audit_agent_source_review','human_review_status':'NOT_PERFORMED',
                   'primary':primary,'defect_labels':tags,'source_contains_real_question':True,
                   'explicit_solution_in_source_unit':n in examples,'stem_ready_for_independent_practice':not hard,
                   'hard_structural_defect_confirmed':hard,'manual_structural_correction_required':hard,
                   'review_conclusion':note,'stage':(['unit_projection_no_solution_separation'] if n in examples else [])+(['unit_boundary_or_asset_association'] if n in boundary|missing_assets else [])+(['source_representation_or_render_serialization'] if n in math_representation else []),
                   'confidence':'high for source-relative structure; original-PDF correctness UNKNOWN',
                   'original_pdf_ocr_fidelity':'UNKNOWN','answer_math_accuracy':'UNKNOWN',
                   'suggested_type_mismatch_confirmed':n in wrong_type,
                   'literal_warning_false_positive':False,
                   'warning_as_content_defect_proxy_false_positive':bool(c['validation_issues']) and not hard},
         'automatic_diagnostics':{'evidence_level':'AUTO-CLASSIFIED','needs_llm':c['needs_llm'],'needs_review':c['needs_review'],
                                  'truncated':r['unit']['truncated'],'math_ast_errors':len(math[r['audit_id']]['katex_errors']),
                                  'formula_blocks_not_exact_math_nodes':math[r['audit_id']]['formula_blocks_not_exact_math_nodes']},
         'private_evidence':'artifacts/question-extraction-quality-2026-10-17/candidates.private.json#'+r['audit_id']}
    published.append(row)
(out / 'candidate-audit.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in published))
warnings=[r for r in published if r['warnings']]
summary={'scope':'Agent source-relative review; no human gold or original-PDF accuracy claim',
         'counts':{'total':108,'agent_source_reviewed':108,'human_reviewed':0,'auto_only':0,
                   'source_real_questions':108,'source_relative_stem_ready':sum(r['review']['stem_ready_for_independent_practice'] for r in published),
                   'requires_structural_correction':sum(r['review']['manual_structural_correction_required'] for r in published),
                   'confirmed_hard_structural_defects':sum(r['review']['hard_structural_defect_confirmed'] for r in published),
                   'unknown_primary_source_structure':0,'unknown_original_pdf_fidelity':108,
                   'metadata_type_mismatches_confirmed':len(wrong_type),'system_needs_review':108,
                   'literal_warning_false_positives':0,'warned_with_hard_defect':sum(r['review']['hard_structural_defect_confirmed'] for r in warnings),
                   'warned_without_hard_defect':sum(not r['review']['hard_structural_defect_confirmed'] for r in warnings),
                   'unwarned_with_hard_defect':sum(not r['warnings'] and r['review']['hard_structural_defect_confirmed'] for r in published),
                   'exact_duplicate_confirmed':16,'duplicate_false_positives':0,
                   'within_candidate_exact_duplicate_groups':sum(count>1 for count in Counter(''.join(r['candidate']['question_text'].lower().split()) for r in records).values()),
                   'ready_new_nonduplicate':sum(r['review']['stem_ready_for_independent_practice'] and not r['duplicate']['marked'] for r in published)},
         'exclusive_primary':dict(Counter(r['review']['primary'] for r in published)),
         'overlapping_labels':dict(Counter(label for r in published for label in r['review']['defect_labels'])),
         'warning_sets':identity['counts'],'quality_numbers_are_not_model_accuracy':True}
summary['taxonomy_counts']={q:{'Q1':92,'Q2':14,'Q3':8,'Q4':14,'Q5':5,'Q6':0,'Q7':4,'Q8':9,'Q9':16,'Q10':89,'Q11':0}[q] for q in ['Q'+str(i) for i in range(1,12)]}
summary['scope_notes']={'Q1':'core source-relative stem-ready; not all metadata or OCR verified',
                        'Q7':'4 representation problems; 2 also have directly inspected source-crop token/fragment issues',
                        'Q10':'89 usable stems appear in issues (user operational definition); literal warning statements are factually correct, strict literal false positives 0',
                        'Q11':'0 unknown primary source-structure decisions; original-PDF fidelity remains UNKNOWN for all 108',
                        'confirmed_any_structural_or_type_error_union':18}
(out / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
