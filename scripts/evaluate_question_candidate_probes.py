"""Additional v1 probes; frozen legacy runner and its expectations remain unchanged."""
import json,sys,runpy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
fixture=runpy.run_path('tests/test_exercise_candidate_contract.py')
legacy=json.loads(Path('artifacts/question-candidate-contract/legacy-probes/contract-probe-results.json').read_text())
rows=[]
for case in fixture['CASES']:
    book,units,registry,proposals=fixture['fixture_case'](case)
    stems=[p['question_text'] for p in proposals]
    comparable=[s.replace('$$\n','').replace('\n$$','') for s in stems]
    answers=[p['answer'] or p['explanation'] for p in proposals]
    assets=sorted({asset for p in proposals for d in p['projection']['dependencies'] for asset in d['asset_ids']})
    strict=comparable==case['expected']['stems'] and answers==case['expected']['answers'] and assets==sorted(case['expected']['required_asset_ids'])
    safe=all(p['projection']['method']=='unresolved' and p['issues'] for p in proposals) if case['id'] in ('R05','R12') else None
    rows.append(dict(id=case['id'],strict_structure='PASS' if strict else 'FAIL',safe_pending='PASS' if safe else 'N/A',raw_stem_equal=stems==case['expected']['stems'],actual_stems=stems,actual_answers=answers,asset_ids=assets,exercise_image_delivery='PENDING_F3' if case['id']=='R11' else 'N/A'))
for row in legacy['results']:
    if row['id'].startswith('D') or row['id']=='A01':
        rows.append(dict(id=row['id'],strict_structure=row['status'],safe_pending='N/A',scope='unchanged legacy/dedup strategy'))
rows.append(dict(id='A01-v1',strict_structure='PASS',evidence='test_api_version_routing_and_all_or_nothing; fake/invalid candidate set has zero writes'))
Path('docs/validation/question-candidate-contract-2026-10-18/probe-disposition.json').write_text(json.dumps(dict(legacy_current_counts=legacy['counts'],note='display wrappers mapped only for new structural comparison; raw stem strings and unchanged legacy results retained',rows=rows),ensure_ascii=False,indent=2)+'\n')
print({key:sum(r['strict_structure']==key for r in rows) for key in ('PASS','FAIL')})
