"""Read-only verification after restarting the isolated qa-live-server."""
import json,sqlite3,urllib.request,os
from pathlib import Path
root=Path(os.environ.get('TEXA_QA_DATA','/tmp/texa-full-qa-live'));out=[]
results=json.loads(Path(os.environ.get('TEXA_QA_RESULTS','docs/qa/evidence/live-e2e/results.json')).read_text())
for item in results['checks']:
    if item['case']=='draft→saved mistake': endpoint='/api/mistakes/'+item['id']+'?book_name=default';expected=item['id']
    elif item['case']=='review reveal→self grade→complete→refresh': expected=item['url'].split('/review/')[1].split('?')[0];endpoint='/api/review/sessions/'+expected+'?book_name=default'
    elif item['case']=='manual exercise validation→save→refresh':expected=item['id'];endpoint='/api/exercises/'+expected+'?book_name=default'
    else:continue
    try:
        response=json.load(urllib.request.urlopen('http://127.0.0.1:18041'+endpoint));data=response['data']
        assert response['success'] and data['id']==expected
        if item['case']=='review reveal→self grade→complete→refresh':assert data['index']==len(data['items']) and data['results']
        db_path=root/'progress'/('exercise_bank_default.db' if item['case'].startswith('manual exercise') else 'mistake_book_default.db')
        table='exercises' if item['case'].startswith('manual exercise') else 'mistake_review_sessions' if item['case']=='review reveal→self grade→complete→refresh' else 'mistakes'
        db=sqlite3.connect(f'file:{db_path}?mode=ro',uri=True)
        rows=db.execute(f'SELECT data FROM {table} WHERE id=?',(expected,)).fetchall();db.close()
        assert len(rows)==1
        persisted=json.loads(rows[0][0]);assert persisted.get('id',expected)==expected
        if item['case']=='review reveal→self grade→complete→refresh':assert persisted['results']==data['results'] and persisted['index']==len(persisted['items'])
        if item['case']=='draft→saved mistake':assert persisted['question_text']==data['question_text'] and len(persisted['review_history'])==1
        if item['case'].startswith('manual exercise'):assert persisted['question_text']==data['question_text']
        out.append({'case':item['case'],'id':expected,'status':'PASS','sqlite_rows':1,'api_matches_authority':True})
    except Exception as error:out.append({'case':item['case'],'id':expected,'status':'FAIL','error':str(error)})
for item in results['checks']:
    case=item['case']
    try:
        if case.startswith('direct attempt lost'):
            response=json.load(urllib.request.urlopen(f"http://127.0.0.1:18041/api/exercises/practice/{item['id']}/operations/{item['operation_id']}?book_name=default"))
            assert response['success'] and response['completion_status']=='complete' and response['data']['practice_count']==1
        elif case.startswith('note frozen'):
            response=json.load(urllib.request.urlopen(f"http://127.0.0.1:18041/api/notes/{item['id']}"))
            assert response['success'] and response['data']['revision']==1 and response['data']['origins']
        elif case.startswith('goal proposal'):
            response=json.load(urllib.request.urlopen(f"http://127.0.0.1:18041/api/goals/{item['id']}/runtime"))
            assert response['goal']['status']=='paused' and response['data']['status']!='running'
        elif case.startswith('chat stream'):
            response=json.load(urllib.request.urlopen(f"http://127.0.0.1:18041/api/chat/tasks/{item['id']}"))
            assert response['learning_task']['status'] in {'completed','degraded','unverified'}
        else: continue
        out.append({'case':case,'id':item['id'],'status':'PASS','restart_authority':True})
    except Exception as error:out.append({'case':case,'id':item['id'],'status':'FAIL','error':str(error)})
for path in root.rglob('*.db'):
    db=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    integrity=db.execute('PRAGMA integrity_check').fetchall();foreign=db.execute('PRAGMA foreign_key_check').fetchall()
    out.append({'database':str(path.relative_to(root)),'status':'PASS' if integrity==[('ok',)] and not foreign else 'FAIL','integrity':integrity,'foreign_keys':foreign})
    db.close()
Path(os.environ.get('TEXA_QA_PERSISTENCE_OUT','docs/qa/evidence/restart-persistence.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False));raise SystemExit(any(x['status']=='FAIL' for x in out))
