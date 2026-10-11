"""Read-only verification after restarting the isolated qa-live-server."""
import json,sqlite3,urllib.request
from pathlib import Path
root=Path('/tmp/texa-full-qa-live');out=[]
results=json.loads(Path('docs/qa/evidence/live-e2e/results.json').read_text())
for item in results['checks']:
    if item['case']=='draft→saved mistake': endpoint='/api/mistakes/'+item['id']+'?book_name=default';expected=item['id']
    elif 'complete' in item['case']: expected=item['url'].split('/review/')[1].split('?')[0];endpoint='/api/review/sessions/'+expected+'?book_name=default'
    elif item['case']=='manual exercise validation→save→refresh':expected=item['id'];endpoint='/api/exercises/'+expected+'?book_name=default'
    else:continue
    try:
        response=json.load(urllib.request.urlopen('http://127.0.0.1:18041'+endpoint));data=response['data']
        assert response['success'] and data['id']==expected
        if 'complete' in item['case']:assert data['index']==len(data['items']) and data['results']
        db_path=root/'progress'/('exercise_bank_default.db' if item['case'].startswith('manual exercise') else 'mistake_book_default.db')
        table='exercises' if item['case'].startswith('manual exercise') else 'mistake_review_sessions' if 'complete' in item['case'] else 'mistakes'
        db=sqlite3.connect(f'file:{db_path}?mode=ro',uri=True)
        rows=db.execute(f'SELECT data FROM {table} WHERE id=?',(expected,)).fetchall();db.close()
        assert len(rows)==1
        persisted=json.loads(rows[0][0]);assert persisted.get('id',expected)==expected
        if 'complete' in item['case']:assert persisted['results']==data['results'] and persisted['index']==len(persisted['items'])
        if item['case']=='draft→saved mistake':assert persisted['question_text']==data['question_text'] and len(persisted['review_history'])==1
        if item['case'].startswith('manual exercise'):assert persisted['question_text']==data['question_text']
        out.append({'case':item['case'],'id':expected,'status':'PASS','sqlite_rows':1,'api_matches_authority':True})
    except Exception as error:out.append({'case':item['case'],'id':expected,'status':'FAIL','error':str(error)})
for path in root.rglob('*.db'):
    db=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    integrity=db.execute('PRAGMA integrity_check').fetchall();foreign=db.execute('PRAGMA foreign_key_check').fetchall()
    out.append({'database':str(path.relative_to(root)),'status':'PASS' if integrity==[('ok',)] and not foreign else 'FAIL','integrity':integrity,'foreign_keys':foreign})
    db.close()
Path('docs/qa/evidence/restart-persistence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False));raise SystemExit(any(x['status']=='FAIL' for x in out))
