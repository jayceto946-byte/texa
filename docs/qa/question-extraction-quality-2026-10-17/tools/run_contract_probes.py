"""Synthetic, audit-only current-vs-desired contract probes. Does not fix extraction.

FAIL is an observed gap against a proposed future contract, not a failing CI gate.
All stems are newly authored toy inputs, not private textbook excerpts.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
sys.path.insert(0,str(ROOT))
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
scratch=tempfile.TemporaryDirectory(prefix='texa-extraction-contract-')
os.environ.update(ENV_PATH='/dev/null',DATA_DIR=scratch.name,MINERU_OUTPUT_PATH=scratch.name)
from ingestion.document_ir import CanonicalBook,DocumentBlock
from ingestion.document_workflows import learning_units
from memory.textbook_exercise_importer import analyze_learning_unit_candidates
from memory.exercise_bank import question_fingerprint,ExerciseBank
from backend.api import exercises
from backend.schemas import ExerciseBatchAddRequest,ExerciseAddRequest

def block(text,typ='paragraph',page=1,title=False,asset=''):
    return {'text':text,'type':typ,'page':page,'mineru_title':title,'asset':asset}

cases=[]
def add(case_id,name,blocks,stems,answers=None,assets=None):
    cases.append({'id':case_id,'name':name,'input_blocks':blocks,'expected':{'stems':stems,'answers':answers or ['']*len(stems),'required_asset_ids':assets or []}})

add('R01','ordinary exercise with no answer',[block('1. 简述温度测量的两种方法。')],['1. 简述温度测量的两种方法。'])
add('R02','worked example with explicit solution',[block('【例 1.1】求三个数的平均值。'),block('解：先相加再除以三。')],['【例 1.1】求三个数的平均值。'],['解：先相加再除以三。'])
add('R03','解 word inside a genuine stem',[block('1. 求解方程 $x+3=8$，并写出解集。')],['1. 求解方程 $x+3=8$，并写出解集。'])
add('R04','proof is requested, not supplied',[block('1. 证明给定集合的解存在，并说明通解和特解的区别。')],['1. 证明给定集合的解存在，并说明通解和特解的区别。'])
add('R05','adjacent numeric section is not a subquestion',[block('【例 1.2】求 $2+3$。'),block('解：结果为5。'),block('(3) 下一节理论',title=True),block('此段不属于例题。')],['【例 1.2】求 $2+3$。'],['解：结果为5。'])
add('R06','two consecutive questions and a subquestion',[block('1. 求 $x^2$ 的导数。'),block('（1）说明所用规则。'),block('2. 求 $x^3$ 的导数。')],['1. 求 $x^2$ 的导数。\n\n（1）说明所用规则。','2. 求 $x^3$ 的导数。'])
add('R07','single question across two physical pages',[block('1. 已知测量值如下。'),block('第二页补充：三次读数为2、4、6，求均值。',page=2)],['1. 已知测量值如下。\n\n第二页补充：三次读数为2、4、6，求均值。'])
long_formula=r'\frac{\sum_{i=1}^{n}(x_i-\bar{x})^2}{n-1}'
add('R08','long formula preserves complete expression',[block('1. 解释下式的含义。'),block(long_formula,'formula')],['1. 解释下式的含义。\n\n'+long_formula])
matrix=r'\begin{pmatrix}1&2\\3&4\end{pmatrix}'
add('R09','matrix stays inside one question',[block('1. 求下列矩阵行列式。'),block(matrix,'formula')],['1. 求下列矩阵行列式。\n\n'+matrix])
piecewise=r'f(x)=\begin{cases}x&x\ge0\\-x&x<0\end{cases}'
add('R10','piecewise expression stays whole',[block('1. 讨论下列函数。'),block(piecewise,'formula')],['1. 讨论下列函数。\n\n'+piecewise])
add('R11','required figure association survives projection',[block('1. 根据图A计算电路的输出。'),block('图A 电路','figure',asset='toy-figure-A')],['1. 根据图A计算电路的输出。\n\n图A 电路'],assets=['toy-figure-A'])
add('R12','solution inline in the first block',[block('【例 1.3】求 $5+6$。\n解：结果为11。')],['【例 1.3】求 $5+6$。'],['解：结果为11。'])
for i,label in enumerate(['解答：','证明：','答案：','证：'],13):
    add(f'R{i:02}',f'solution layout {label}',[block('【例 1.4】讨论 $a=a$。'),block(label+'由自反性得到。',title=True)],['【例 1.4】讨论 $a=a$。'],[label+'由自反性得到。'])
add('R17','valid numeric subquestion title survives',[block('1. 比较两种测量结果。'),block('(2) 再分析误差。',title=True)],['1. 比较两种测量结果。\n\n(2) 再分析误差。'])
add('R18','OCR missing structure cannot become an invented question',[block('…条件缺失…识别残片…')],[])
add('R19','a decimal in a formula is not a new question',[block('1. 解释此关系。'),block('1.0 + x = y','formula')],['1. 解释此关系。\n\n1.0 + x = y'])
results=[]
for case in cases:
    blocks=[DocumentBlock(block_id=f"{case['id']}-{i}",block_type=b['type'],text=b['text'],section_path=['第1章 审计样例','习题'],page_start=b['page'],page_end=b['page'],attributes={**({'mineru_type':'paragraph_title'} if b['mineru_title'] else {}),**({'asset_id':b['asset']} if b['asset'] else {})}) for i,b in enumerate(case['input_blocks'])]
    book=CanonicalBook('审计合成样例','synthetic',blocks,'audit-only')
    units=learning_units(book)
    payload=[{'unit_id':u.unit_id,'kind':u.kind,'text':u.text,'chapter':u.section_path[0],'page_start':u.blocks[0].page_start,'page_end':u.blocks[-1].page_end,'source_block_ids':[b.block_id for b in u.blocks],'truncated':u.truncated} for u in units]
    actual=analyze_learning_unit_candidates(payload,book_name=book.book_name,subject='数学',limit=200)
    stems=[c.question_text for c in actual];answers=[c.answer or c.explanation for c in actual]
    assets=[a for c in actual for a in getattr(c,'asset_ids',[])]
    ok=stems==case['expected']['stems'] and answers==case['expected']['answers'] and set(case['expected']['required_asset_ids']).issubset(assets)
    results.append({'id':case['id'],'name':case['name'],'status':'PASS' if ok else 'FAIL','actual_stems':stems,'actual_answers':answers,'actual_assets':assets})
dedup=[('D01','identical prompt from different source','1. 求 $x+2$。','1. 求 $x+2$。',True),
       ('D02','similar but different numbers','1. 求 $x+2$。','1. 求 $x+3$。',False),
       ('D03','case-sensitive Greek macros',r'1. 解释 $\Gamma(x)$。',r'1. 解释 $\gamma(x)$。',False),
       ('D04','same prompt different numbering','1. 求 $x+2$。','2. 求 $x+2$。',True)]
for cid,name,left,right,expected in dedup:
    actual=question_fingerprint(left)==question_fingerprint(right)
    results.append({'id':cid,'name':name,'status':'PASS' if actual==expected else 'FAIL','input':[left,right],'expected_equal':expected,'actual_equal':actual})
# Demonstrate the existing admission boundary on a fresh throwaway bank. Logs
# are suppressed only here; no production database or real question is involved.
bank=ExerciseBank(Path(scratch.name)/'admission.db')
exercises._bank=lambda _book='default':bank
exercises._log_learning_event=lambda *_args,**_kwargs:None
added=exercises.batch_add_exercises(ExerciseBatchAddRequest(exercises=[ExerciseAddRequest(question_text='【例 1.1】求 $2+3$。\n解：结果为5。',status='needs_review')]))
session=bank.create_practice_session(limit=1)
results.append({'id':'A01','name':'unseparated example must not be treated as a structurally verified practice item','status':'FAIL' if added['count']==1 and session.exercise_ids else 'PASS','actual_admitted':added['count'],'actual_practice_items':len(session.exercise_ids),'note':'Current API cannot inspect candidate warnings; synthetic demonstration of missing structural contract, not an unauthorized production action.'})
(out/'regression-cases.json').write_text(json.dumps({'inputs':'new synthetic toy cases; no private textbook text','cases':cases,'duplicate_cases':dedup},ensure_ascii=False,indent=2)+'\n')
summary={'runner_status':'COMPLETE','scope':'current behavior versus proposed future acceptance; known gaps intentionally remain FAIL','counts':{'PASS':sum(r['status']=='PASS' for r in results),'FAIL':sum(r['status']=='FAIL' for r in results)},'results':results}
(out/'contract-probe-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary['counts']))
scratch.cleanup()
