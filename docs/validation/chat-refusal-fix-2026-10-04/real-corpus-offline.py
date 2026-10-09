import json,pathlib,sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from unittest.mock import patch
from ingestion.lexical_index import search_rows,expand_neighbors_rows
from ingestion.vector_store import RetrievalOutcome
from graph.retrieval_node import retrieve_node
from graph.safe_retrieval import SafeKG
from graph.evidence_pack import build_evidence_pack
from graph.generator import prepare_answer_generation
from backend.services.session_context import build_resolution_trace
base=pathlib.Path.home()/'Library/Application Support/kaoyan-assistant-desktop/data'
rows=json.loads((base/'vector_db/_lexical_versions/传感器原理及应用/c8b6947edb7858f2.json').read_text())
class Store:
 def search_all(self,*a,**k):return RetrievalOutcome(items={})
 def search_chapter(self,*a,**k):return RetrievalOutcome(items=[])
queries=[('types','电阻式传感器可以分成哪两种类型',['第4章 力敏传感器','第1章 绪论']),('examples','根据传感器的分类，比如说根据结构分类是物性型和结构型，还有复合型，那把这对应分类具体是哪几种传感器，比如说电容式、电阻式是什么结构型的传感器，这样给我举例一下',['第1章 绪论']),('materials','电阻式传感器，它有两种材料，这两种材料构成的不同种类的传感器各有什么特点？适用于哪种场景',['第4章 力敏传感器'])]
out={'corpus_version':'c8b6947edb7858f2','validation':'Production retrieve_node with full existing lexical snapshot, empty vector backend, disabled KG/history. No model calls or live user data writes. Planner chapters frozen to diagnosed scopes; not an online answer evaluation.','cases':[]}
for name,q,chapters in queries:
 state=dict(user_input=q,book_name='传感器原理及应用',subject='专业课',intent='factual_recall',target_chapters=chapters,answer_mode='textbook_grounded',use_textbook_context=True)
 with patch('graph.retrieval_node.get_safe_kg',return_value=(SafeKG(),'')),patch('graph.retrieval_node._load_history',return_value=[]):
  r=retrieve_node(state,vector_store=Store(),lexical_search=lambda b,q,**kw:search_rows(rows,q,**kw),neighbor_expander=lambda b,ids,**kw:expand_neighbors_rows(rows,ids,**kw),index_stats_override={'传感器原理及应用':{'healthy':True}},retrieval_resources_override=[dict(book_name='传感器原理及应用',is_primary=True,is_selected=True,role='core',priority=1)])
 pack=build_evidence_pack(r['evidence_items'],intent='factual_recall')
 case={'name':name,'query':q,'resolution':build_resolution_trace(q,[])['resolution_action'],'support':r['evidence_support'],'retrieval_error':r['retrieval_error'],'pack_items':[{k:i.get(k) for k in ['chunk_id','section_title','page_start','chars']} for i in pack['items']],'has_metal':'金属应变片' in pack['text'],'has_semiconductor':'半导体应变片' in pack['text'],'has_classification':all(w in pack['text'] for w in ['结构型','物性型','复合型'])}
 assert case['resolution']=='continue'
 assert case['support']['status'] in {'supported','partial'}
 if name in {'types','materials'}:assert case['has_metal'] and case['has_semiconductor']
 if name=='examples':assert case['has_classification']
 out['cases'].append(case)
 print(json.dumps(case,ensure_ascii=False,indent=2))
 if name=='materials':
  print('MATERIAL EVIDENCE')
  for i in r['evidence_items']:
   if i['chunk_id'] in {x['chunk_id'] for x in pack['items']}:print(i['section_title'],i['text'][:900])
state=dict(user_input=queries[1][1],book_name='传感器原理及应用',subject='专业课',intent='factual_recall',answer_mode='subject_general',use_textbook_context=False,evidence_items=[])
m=prepare_answer_generation(state)
assert '允许使用模型知识' in m[0].content and '不用模型记忆补齐' not in m[0].content
out['general_prompt']={'assembly_mode':state['context_budget']['assembly_mode'],'allows_model_knowledge':True,'evidence_included_count':state['context_budget']['evidence_included_count']}
path=pathlib.Path('docs/validation/chat-refusal-fix-2026-10-04');path.mkdir(parents=True,exist_ok=True);(path/'real-corpus-offline.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
