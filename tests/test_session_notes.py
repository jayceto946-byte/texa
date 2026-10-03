"""Offline Notes contract, concurrency and fault-injection regressions."""
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import conversation_memory as cm
from backend.job_manager import JobManager
from backend.services.session_notes.service import SessionNoteService
from backend.services.session_notes.generation import generate, plan_batches
from backend.services.session_notes.jobs import start_generation, reconcile
from memory.session_notes import SessionNoteStore, NoteError, fingerprint


class Chapters:
    def resolve(self, evidence):
        return {"chapter_ref_id": "chapterref_" + fingerprint({"book": evidence.get("book_id"), "hash": evidence.get("canonical_hash"), "path": evidence.get("section_path")}), "book_id": evidence.get("book_id"), "title_snapshot": "连续与可导", "resolution": "legacy", "canonical_hash": evidence.get("canonical_hash")}
    def availability(self, ref):
        return "unavailable"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    jobs = JobManager(tmp_path / "jobs.sqlite3")
    svc = SessionNoteService(SessionNoteStore(tmp_path / "session_notes.db"), chapters=Chapters(), jobs_provider=lambda:jobs)
    monkeypatch.setattr(svc, "audit", lambda *a,**k:None)
    for turn in range(3):
        cm.append_message("session", "user", f"连续能推出可导吗？{turn}", turn_id=f"t{turn}")
        cm.append_message("session", "assistant", "可导推出连续，连续未必可导。$|x|$ 在零点连续但不可导。", turn_id=f"t{turn}", sources=[{"id":"E1","book_id":"book", "book_name":"数学", "chunk_id":f"chunk{turn}","canonical_hash":"v1","text":"可导则连续"}])
    return svc


def fake_call(payload, **kwargs):
    if "messages" in payload:
        sources = payload["messages"]
    else:
        entries = [e for result in payload["extractions"] for e in result["coverage"]]
        sources = [{"source_ref_id":e["source_ref_id"],"content":"可导推出连续", "role":"assistant"} for e in entries]
    blocks = [{"block_id":f"b{n}","type":"paragraph","role":"concept","data":{"markdown":s["content"]},"source_ref_ids":[s["source_ref_id"]],"evidence_ref_ids":[]} for n,s in enumerate(sources)]
    return json.dumps({"document":{"title":"连续与可导","blocks":blocks}, "coverage":[{"source_ref_id":s["source_ref_id"],"block_ids":[f"b{n}"],"disposition":"included"} for n,s in enumerate(sources)]},ensure_ascii=False)


def request(service, op="generation"):
    preflight,_ = service.preflight({"conversation_id":"session"})
    req={"operation_id":op,"selection":preflight["selection"],"preflight_fingerprint":preflight["fingerprint"]}
    receipt=service.request_generation(req)
    return receipt,req


def ready(service, op="generation"):
    receipt,req=request(service,op)
    start_generation(service,receipt,generator=lambda snapshot,**kw:generate(snapshot,call=fake_call,**kw),threaded=False)
    draft=service.draft(receipt["draft_id"])
    assert draft["status"]=="editable", draft
    return draft,receipt,req


def save(service,draft,op="save"):
    req={"operation_id":op,"expected_draft_revision":draft["draft_revision"],"base_note_revision":draft.get("base_note_revision"),"acknowledgement":{"draft_revision":draft["draft_revision"],"warning_hash":draft["content"]["quality"]["warning_hash"]}}
    return service.save(draft["id"],req),req


def test_versioned_manual_edit_and_independent_save(service):
    draft,receipt,req=ready(service)
    assert service.store.list()["items"]==[]
    saved,save_req=save(service,draft)
    assert service.save(draft["id"],save_req)==saved
    assert service.request_generation(req)==receipt
    note=service.detail(saved["note_id"])
    old=copy.deepcopy(note["blocks"])
    edit=service.create_draft(kind="edit",note_id=note["id"],base_revision=1)
    content={k:v for k,v in edit["content"].items() if k!="quality"}
    content["blocks"][0]["data"]["markdown"]="用户订正后的内容"
    content["blocks"][0]["authorship"]="generated"
    content["blocks"].append({"block_id":"new-user-block","type":"equation","data":{"latex":"x^2"},"authorship":"generated"})
    edit=service.patch_draft(edit["id"],1,content)
    assert edit["content"]["blocks"][0]["source_alignment"]=="needs_review"
    assert edit["content"]["blocks"][-1]["source_alignment"]=="user_added"
    assert edit["content"]["blocks"][-1]["authorship"]=="user"
    second,_=save(service,edit,"save2")
    assert second["revision"]==2
    assert service.detail(note["id"],1)["blocks"]==old
    # A second independent note from the same session.
    another,_,_=ready(service,"generation2")
    saved2,_=save(service,another,"save3")
    assert saved2["note_id"]!=note["id"]
    assert len(service.store.list(conversation_id="session")["items"])==2


def test_concurrent_operations_and_cas(service):
    receipt,req=request(service)
    req2={**req,"operation_id":"other-op"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(service.request_generation,[req,req2]))
    assert results==[receipt,receipt]
    draft,_,_=ready(service)
    saved,save_req=save(service,draft)
    with pytest.raises(NoteError,match="同一操作"):
        service.save(draft["id"],{**save_req,"expected_draft_revision":999})
    edit=service.create_draft(kind="edit",note_id=saved["note_id"],base_revision=1)
    content={k:v for k,v in edit["content"].items() if k!="quality"}
    edit2=service.patch_draft(edit["id"],1,content)
    with pytest.raises(NoteError) as err:
        service.patch_draft(edit["id"],1,content)
    assert err.value.code=="revision_conflict"
    archived=service.status(saved["note_id"],{"operation_id":"archive","expected_revision":1,"status":"archived"})
    assert archived["revision"]==2
    with pytest.raises(NoteError):
        save(service,edit2,"conflicting-save")
    assert service.detail(saved["note_id"])["status"]=="archived"
    service.status(saved["note_id"],{"operation_id":"restore","expected_revision":2,"status":"active"})
    assert service.detail(saved["note_id"],2)["status"]=="archived"


def test_frozen_source_namespaces_change_move_missing(service):
    draft,_,_=ready(service)
    snap=service.store.get("note_source_snapshots",draft["source_snapshot_ids"][0])
    assert len({e["evidence_ref_id"] for e in snap["evidence"]})==3
    assert {e["original_e_id"] for e in snap["evidence"]}=={"E1"}
    source=snap["sources"][0]
    assert service.source(draft["id"],source["source_ref_id"],draft=True)["status"]=="current"
    cm.update_message_evidence_support("session",source["id"],"unverified")
    assert service.source(draft["id"],source["source_ref_id"],draft=True)["status"]=="changed"
    _,target=cm.split_turn_to_conversation("session",source["turn_id"],"数学")
    detail=service.source(draft["id"],source["source_ref_id"],draft=True)
    assert detail["status"]=="moved"
    assert detail["live_locator"]["conversation_id"]==target["id"]
    with cm._connect_events() as conn:
        conn.execute("DELETE FROM conversation_messages")
    detail=service.source(draft["id"],source["source_ref_id"],draft=True)
    assert detail["status"]=="unavailable" and detail["source"]["content"]


@pytest.mark.parametrize("turns",[20,40,80,2600])
def test_history_exceeds_recent_and_full_window(service,turns):
    with cm._connect_events() as conn:
        for n in range(turns):
            for offset,role in enumerate(("user","assistant")):
                item={"id":f"large{n}_{role}","turn_id":f"l{n}","role":role,"content":"知识", "created_at":"2026-10-02"}
                cm._insert_projection_message(conn,"large",item,seq=n*2+offset+1)
        conn.execute("INSERT INTO conversation_imports VALUES('large','today')")
    captured=cm.capture_note_selection("large")
    assert len(captured["messages"])==turns*2
    assert len(cm.load_full_history("large"))==min(5000,turns*2)
    with pytest.raises(NoteError) as err:
        cm.capture_note_selection("large",max_bytes=10)
    assert err.value.code=="needs_range_selection"


def test_preflight_fingerprint_does_not_include_later_turns(service):
    pre,_=service.preflight({"conversation_id":"session"})
    cm.append_message("session","user","新内容",turn_id="later")
    cm.append_message("session","assistant","新回答",turn_id="later")
    receipt=service.request_generation({"operation_id":"fixed","selection":pre["selection"],"preflight_fingerprint":pre["fingerprint"]})
    snap=service.store.get("note_source_snapshots",receipt["snapshot_id"])
    assert len(snap["sources"])==6
    cm.reclassify_conversation("session","数学")
    with pytest.raises(NoteError) as err:
        service.request_generation({"operation_id":"changed","selection":pre["selection"],"preflight_fingerprint":pre["fingerprint"]})
    assert err.value.code=="source_changed"


def test_preflight_roundtrip_preserves_scope_exclusions(service):
    cm.reclassify_conversation("session", "数学")
    cm.append_message("session", "user", "旧范围问题", turn_id="outside")
    cm.append_message("session", "assistant", "旧范围回答", turn_id="outside")
    pre, snapshot = service.preflight({"conversation_id": "session"})
    assert pre["turn_count"] == 3
    assert len(snapshot["excluded"]) == 2
    repeated, repeated_snapshot = service.preflight(pre["selection"])
    assert repeated["fingerprint"] == pre["fingerprint"]
    assert repeated_snapshot["excluded"] == snapshot["excluded"]
    receipt = service.request_generation({"operation_id": "scoped-roundtrip", "selection": pre["selection"], "preflight_fingerprint": pre["fingerprint"]})
    stored = service.store.get("note_source_snapshots", receipt["snapshot_id"])
    assert len(stored["sources"]) == 6
    assert stored["excluded"] == snapshot["excluded"]


def test_bad_model_refs_and_coverage_rejected(service):
    _,snapshot=service.preflight({"conversation_id":"session"})
    def bad(payload,**kwargs):
        result=json.loads(fake_call(payload))
        result["document"]["blocks"][0]["source_ref_ids"]=["another-session"]
        return json.dumps(result)
    with pytest.raises(NoteError):
        generate(snapshot,call=bad)
    def missing(payload,**kwargs):
        result=json.loads(fake_call(payload))
        result["coverage"].pop()
        return json.dumps(result)
    assert len(generate(snapshot,call=missing)["quality"]["coverage"]) == len(snapshot["sources"])
    def forged_coverage(payload,**kwargs):
        result=json.loads(fake_call(payload))
        result["coverage"][0]["source_ref_id"]="another-session"
        return json.dumps(result)
    with pytest.raises(NoteError):
        generate(snapshot,call=forged_coverage)
    with pytest.raises(NoteError):
        plan_batches([{"turn_id":"huge","content":"x"*100000}])


@pytest.mark.parametrize("link_conversation", [True, False])
def test_article_supplement_without_coverage_can_be_saved(service, link_conversation):
    receipt, _ = request(service, "article-supplement")
    frozen = copy.deepcopy(service.store.get("note_source_snapshots", receipt["snapshot_id"]))

    def article(payload, **kwargs):
        # A thematic paragraph combines the discussion; a new example explains it.
        refs = [m["source_ref_id"] for m in payload["messages"] if m["role"] == "assistant"] if link_conversation else []
        return json.dumps({"document": {"title": "连续与可导", "blocks": [
            {"block_id": "discussion", "type": "paragraph", "data": {"markdown": "可导必然连续，连续未必可导。"}, "source_ref_ids": refs},
            {"block_id": "supplement", "type": "equation", "data": {"latex": "f(x)=x^2", "annotation": "作为直观例子，平方函数处处连续且可导。"}}
        ]}}, ensure_ascii=False)

    start_generation(service, receipt, generator=lambda snapshot, **kw: generate(snapshot, call=article, **kw), threaded=False)
    draft = service.draft(receipt["draft_id"])
    assert draft["status"] == "editable", draft
    example = draft["content"]["blocks"][1]
    assert example["source_ref_ids"] == example["evidence_ref_ids"] == []
    assert example["authorship"] == "generated"
    assert example["source_alignment"] == "supplemented"
    assert example["verification"]["status"] == "not_checked"
    coverage = draft["content"]["quality"]["coverage"]
    assert len(coverage) == (3 if link_conversation else 0)
    assert all(entry["block_ids"] == [draft["content"]["blocks"][0]["block_id"]] for entry in coverage)
    saved = service.save(draft["id"], {"operation_id": "save-article", "expected_draft_revision": draft["draft_revision"], "base_note_revision": None})
    note = service.detail(saved["note_id"])
    assert note["blocks"][1] == example
    assert note["quality"]["semantic_review"] == "not_checked"
    assert note["generation"]["prompt_version"] == "session-note-article-v4"
    assert service.store.get("note_source_snapshots", receipt["snapshot_id"]) == frozen


def test_supplement_cannot_claim_unprovided_textbook_evidence(service):
    _, snapshot = service.preflight({"conversation_id": "session"})

    def forged(payload, **kwargs):
        return json.dumps({"document": {"title": "连续", "blocks": [{"block_id": "extra", "type": "paragraph", "data": {"markdown": "补充说明"}, "evidence_ref_ids": ["T1"]}]}})

    with pytest.raises(NoteError) as error:
        generate(snapshot, call=forged)
    assert error.value.code == "invalid_source_ref"


def test_cancellation_and_complete_publication_crashes(service,monkeypatch):
    receipt,_=request(service)
    def cancelled(snapshot,**kw):
        service.jobs().request_cancel(receipt["job_id"])
        return generate(snapshot,call=fake_call)
    start_generation(service,receipt,generator=cancelled,threaded=False)
    assert service.jobs().get_job(receipt["job_id"])["status"]=="cancelled"
    assert service.draft(receipt["draft_id"])["status"]=="preparing"
    # Manual fallback and retry retain the exact frozen snapshot.
    manual=service.create_draft(kind="manual",snapshot_id=receipt["snapshot_id"])
    assert manual["status"]=="editable"
    retry=service.request_generation({"operation_id":"retry","retry_of_draft_id":receipt["draft_id"]})
    assert retry["snapshot_id"]==receipt["snapshot_id"] and retry["draft_id"]!=receipt["draft_id"]
    publish=service.store.publish_candidate
    monkeypatch.setattr(service.store,"publish_candidate",lambda *a:(_ for _ in ()).throw(OSError("disk failed")))
    start_generation(service,retry,generator=lambda snap,**kw:generate(snap,call=fake_call,**kw),threaded=False)
    assert service.jobs().get_job(retry["job_id"])["status"]=="completed"
    monkeypatch.setattr(service.store,"publish_candidate",publish)
    assert reconcile(service)==1
    assert service.draft(retry["draft_id"])["status"]=="editable"
    assert reconcile(service)==0


def test_application_restart_unstarted_receipt(service):
    receipt,_=request(service)
    reconcile(service)
    assert service.jobs().get_job(receipt["job_id"])["status"]=="interrupted"
    # Replayed operation must never restart it.
    start_generation(service,receipt,generator=lambda *a,**kw:pytest.fail("paid restart"),threaded=False)


def test_api_error_contract_and_offline_read(service):
    from backend.api.notes import router,get_notes_service
    app=FastAPI()
    app.include_router(router,prefix="/api")
    app.dependency_overrides[get_notes_service]=lambda:service
    client=TestClient(app)
    invalid=client.post("/api/notes/preflight",json={"selection":{"conversation_id":"../bad"}})
    assert invalid.status_code==400 and invalid.json()["code"]=="invalid_selection"
    invalid=client.post("/api/notes/preflight",json={"bad":True})
    assert invalid.status_code==422 and invalid.json()["code"]=="invalid_document"
    assert client.get("/api/notes/missing").status_code==404
    draft,_,_=ready(service)
    saved,_=save(service,draft)
    assert client.get(f"/api/notes/{saved['note_id']}").status_code==200
    assert "blocks" not in client.get("/api/notes").json()["data"]["items"][0]


def test_schema_future_rejected_and_sqlite_backup(service,tmp_path):
    draft,_,_=ready(service)
    saved,_=save(service,draft)
    from backend.data_backup import _copy_consistent_file
    # SQLite backup API preserves snapshots, drafts, immutable revisions.
    _copy_consistent_file(service.store.path,tmp_path/"copy.db")
    restored=SessionNoteStore(tmp_path/"copy.db")
    assert restored.get("session_notes",saved["note_id"])["blocks"]
    assert restored.get("note_source_snapshots",draft["source_snapshot_ids"][0])["sources"]
    with sqlite3.connect(service.store.path) as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(NoteError):
        SessionNoteStore(service.store.path)


def test_candidate_before_complete_crash_and_late_callback(service):
    receipt,_=request(service)
    manager=service.jobs()
    manager.create_job('session_note_generate',job_id=receipt['job_id'],input_data=receipt)
    assert manager.claim_queued_job(receipt['job_id'])
    snap=service.store.get('note_source_snapshots',receipt['snapshot_id'])
    content=generate(snap,call=fake_call)
    service.store.candidate(receipt['draft_id'],content)
    manager.mark_running_interrupted()
    reconcile(service)
    assert service.draft(receipt['draft_id'])['status']=='preparing'
    with pytest.raises(RuntimeError):
        manager.complete_job(receipt['job_id'])
    # Cancellation cannot be overwritten by start/failure or a late completion.
    other=manager.create_job('session_note_generate')
    manager.request_cancel(other['id'])
    assert not manager.claim_queued_job(other['id'])
    assert manager.fail_or_cancel_job(other['id'],error='transport',message='failed')['status']=='cancelled'


def test_save_transaction_crash_does_not_commit_asset(service,monkeypatch):
    draft,_,_=ready(service)
    record=service.store.record
    def disk_failure(*args):
        raise OSError('disk error after revision insert')
    monkeypatch.setattr(service.store,'record',disk_failure)
    with pytest.raises(OSError):
        save(service,draft)
    assert service.store.list()['items']==[]
    assert service.draft(draft['id'])['status']=='editable'
    monkeypatch.setattr(service.store,'record',record)
    saved,_=save(service,draft)
    assert saved['revision']==1


def test_strict_thinking_credentials_invalid_evidence_and_limits(service):
    _,snapshot=service.preflight({'conversation_id':'session'})
    def thinking(payload,**kw):
        return '<think>private reasoning</think>'+fake_call(payload)
    result=generate(snapshot,call=thinking)
    assert 'private reasoning' not in json.dumps(result)
    def forged(payload,**kw):
        value=json.loads(fake_call(payload));value['document']['blocks'][0]['evidence_ref_ids']=['T1']
        return json.dumps(value)
    with pytest.raises(NoteError):
        generate(snapshot,call=forged)
    cm.append_message('secrets','user','API_KEY=sk-test-123456789012345 /Users/test/hidden.png',turn_id='s')
    cm.append_message('secrets','assistant','请不要分享凭证',turn_id='s')
    _,scrubbed=service.preflight({'conversation_id':'secrets'})
    assert 'sk-test' not in json.dumps(scrubbed) and '/Users/test/' not in json.dumps(scrubbed)
    draft,_,_=ready(service)
    content={k:v for k,v in draft['content'].items() if k!='quality'}
    content['title']='a'*201
    with pytest.raises(NoteError):
        service.patch_draft(draft['id'],draft['draft_revision'],content)


def test_large_range_picker_and_message_context(service):
    turns=cm.list_note_turns('session',limit=2)
    assert len(turns['items'])==2 and turns['next_cursor']
    rest=cm.list_note_turns('session',before_seq=turns['next_cursor'],limit=2)
    assert len(rest['items'])==1
    target=cm.capture_note_selection('session')['messages'][0]
    context=cm.resolve_message_context('session',target['id'],radius=1)
    assert context['target']['id']==target['id'] and len(context['messages'])==2
    assert len(cm.load_message_page_after('session',context['page']['next_after_seq'])['messages'])==4
    with pytest.raises(NoteError):
        cm.capture_note_selection('session',through_seq=1)


def test_multi_batch_fixed_plan_and_failure_no_repair(service):
    for n in range(12):
        cm.append_message('long','user',f'讨论概念 {n}',turn_id=f'x{n}')
        cm.append_message('long','assistant','保持公式条件与原结论。'*70,turn_id=f'x{n}')
    _,snapshot=service.preflight({'conversation_id':'long'})
    calls=[]
    def call(payload,**kw):
        calls.append(payload['phase'])
        if payload['phase']=='extract':
            payload=copy.deepcopy(payload)
            for message in payload['messages']:
                message['content']='保持公式条件与原结论。'
        result=json.loads(fake_call(payload,**kw))
        result.pop('coverage')
        return json.dumps(result)
    document=generate(snapshot,call=call)
    assert 2<=len(calls)<=9 and calls[-1]=='organize_extracted'
    assert len(document['quality']['coverage'])==24
    calls.clear()
    def bad(payload,**kw):
        calls.append(payload)
        return 'not JSON'
    with pytest.raises(NoteError):
        generate(snapshot,call=bad)
    assert len(calls)==1


def test_restore_readonly_integrity_and_missing_old_component(service,tmp_path):
    from memory.session_notes import validate_notes_database
    draft,_,_=ready(service);save(service,draft)
    validate_notes_database(service.store.path)
    validate_notes_database(tmp_path/'old-archive-without-notes.db')
    with sqlite3.connect(service.store.path) as conn:
        conn.execute('DELETE FROM note_source_snapshots')
    with pytest.raises(ValueError):
        validate_notes_database(service.store.path)


def test_chapter_identity_rename_reorder_version_and_missing(tmp_path):
    from backend.services.chapter_references import ChapterReferenceResolver
    from utils.book_registry import BookRegistry
    from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint
    registry=BookRegistry(tmp_path)
    record=registry.ensure('math',display_name='数学')
    book=CanonicalBook('math','fixture',[DocumentBlock('h1','heading','连续',['连续']),DocumentBlock('p1','paragraph','连续未必可导',['连续'])],'fixture')
    resolver=ChapterReferenceResolver(registry,lambda name:book)
    evidence={'book_id':record['book_id'],'book_name':'数学','canonical_hash':canonical_book_fingerprint(book),'source_block_ids':['p1']}
    first=resolver.resolve(evidence)
    assert first['resolution']=='exact'
    registry.rename_display(record['book_id'],'高等数学')
    assert resolver.resolve(evidence)['chapter_ref_id']==first['chapter_ref_id']
    assert resolver.options()['items'][0]['chapter_ref_id']==first['chapter_ref_id']
    book.blocks.insert(0,DocumentBlock('h0','heading','新章',['新章']))
    assert resolver.availability(first)=='historical'
    assert resolver.resolve(evidence)['resolution']=='legacy'
    current=resolver.options()['items'][1]
    assert current['chapter_ref_id']!=first['chapter_ref_id']
    assert resolver.validate_classification([current])==[current]
    with pytest.raises(NoteError):
        resolver.validate_classification([{**current,'chapter_ref_id':'fake'}])
    registry.set_status(record['book_id'],'purged')
    assert resolver.availability(first)=='unavailable'


def test_partial_completion_fingerprint_and_immutable_snapshot(service):
    cm.append_message('partial','user','计算极限',turn_id='p')
    answer=cm.append_message('partial','assistant','步骤未完成',turn_id='p',delivery_status='partial')
    pre,snapshot=service.preflight({'conversation_id':'partial'})
    receipt=service.request_generation({'operation_id':'partial-old','selection':pre['selection'],'preflight_fingerprint':pre['fingerprint']})
    cm.append_message('partial','assistant','完整结论',turn_id='p',delivery_status='complete')
    assert cm.get_message('partial',answer['id'])['content']=='完整结论'
    with pytest.raises(NoteError) as err:
        service.request_generation({'operation_id':'partial-new','selection':pre['selection'],'preflight_fingerprint':pre['fingerprint']})
    assert err.value.code=='source_changed'
    frozen=service.store.get('note_source_snapshots',receipt['snapshot_id'])
    assert frozen['sources'][-1]['content']=='步骤未完成'
    assert frozen['warnings']


def test_explicit_save_preserves_internal_quality_without_acknowledgement(service):
    cm.append_message('image','user','📎 photo.png\n\n请解答',turn_id='img')
    cm.append_message('image','assistant','缺少附表，只能说明方法',turn_id='img',learning_task={'status':'waiting_for_input','required_inputs':[{'id':'table','kind':'table','status':'missing'}],'verification':{'status':'unverified'}})
    pre,snap=service.preflight({'conversation_id':'image'})
    assert any('missing_required_input' in warning['reasons'] for warning in snap['warnings'])
    receipt=service.request_generation({'operation_id':'image','selection':pre['selection'],'preflight_fingerprint':pre['fingerprint']})
    start_generation(service,receipt,generator=lambda s,**kw:generate(s,call=fake_call,**kw),threaded=False)
    draft=service.draft(receipt['draft_id'])
    request={'operation_id':'explicit-save','expected_draft_revision':draft['draft_revision']}
    saved=service.save(draft['id'],request)
    assert service.save(draft['id'],request)==saved
    note=service.detail(saved['note_id'])
    assert note['quality']==draft['content']['quality']
    assert note['quality']['warnings']
    assert note['quality']['semantic_review']=='not_checked'


def test_backup_archive_restores_notes_without_conversation(service,tmp_path,monkeypatch):
    from backend import data_backup
    draft,_,_=ready(service);saved,_=save(service,draft)
    data_root=tmp_path/'restore-data';progress=data_root/'progress';progress.mkdir(parents=True)
    data_backup._copy_consistent_file(service.store.path,progress/'session_notes.db')
    backups=tmp_path/'backups'
    for name,value in {'DATA_ROOT':data_root,'BACKUP_ROOT':backups,'MINERU_ROOT':tmp_path/'mineru','PENDING_RESTORE_PATH':backups/'pending_restore.json','RESTORE_RESULT_PATH':backups/'last_restore.json'}.items():
        monkeypatch.setattr(data_backup,name,value)
    archive=data_backup.create_backup()
    data_backup.schedule_restore(archive['name'])
    result=data_backup.apply_pending_restore()
    assert result['status']=='completed'
    restored=SessionNoteStore(progress/'session_notes.db')
    restored_service=SessionNoteService(restored,chapters=Chapters(),live_resolver=lambda *a:{'status':'unavailable','target':None,'conversation_id':'session'})
    assert restored_service.detail(saved['note_id'])['blocks']
    ref=restored.get('note_source_snapshots',draft['source_snapshot_ids'][0])['sources'][0]['source_ref_id']
    detail=restored_service.source(saved['note_id'],ref)
    assert detail['status']=='unavailable' and detail['source']['content']


@pytest.mark.parametrize('bad_field', ['chapter', 'book', 'tone', 'header_thinking'])
def test_malformed_editor_fields_fail_without_losing_draft(service, bad_field):
    draft, _, _ = ready(service)
    before = copy.deepcopy(draft['content'])
    content = {k: copy.deepcopy(v) for k, v in before.items() if k != 'quality'}
    if bad_field == 'chapter':
        content['chapter_refs'] = [{'chapter_ref_id': []}]
    elif bad_field == 'book':
        content['chapter_refs'] = [{'chapter_ref_id': 'new', 'book_id': []}]
    elif bad_field == 'tone':
        content['blocks'][0].update(type='callout', data={'markdown': 'text', 'tone': []})
    else:
        content['title'] = '<thinking>private analysis</thinking>笔记'
    with pytest.raises(NoteError) as error:
        service.patch_draft(draft['id'], draft['draft_revision'], content)
    assert error.value.code == 'invalid_document'
    assert service.draft(draft['id'])['content'] == before


def test_filters_span_pages_and_pagination_limits_are_bounded(service):
    draft, _, _ = ready(service)
    saved, _ = save(service, draft)
    page = service.store.list(limit=1)
    assert len(page['items']) == 1
    options = service.store.filter_options()
    assert options['books'][0]['book_id'] == 'book'
    edit = service.create_draft(kind='edit', note_id=saved['note_id'], base_revision=1)
    content = {k: copy.deepcopy(v) for k, v in edit['content'].items() if k != 'quality'}
    content['chapter_refs'] = edit['chapter_options']
    edit = service.patch_draft(edit['id'], edit['draft_revision'], content)
    save(service, edit, 'classify-save')
    options = service.store.filter_options()
    assert options['chapter_refs'][0]['chapter_ref_id'] == edit['chapter_options'][0]['chapter_ref_id']
    assert len(service.store.revisions(saved['note_id'], limit=-1)['items']) == 1
    assert len(cm.load_message_page_after('session', 0, limit=-1)['messages']) == 1


def test_runtime_audit_failure_cannot_fail_committed_save(service, monkeypatch):
    draft, _, _ = ready(service)
    from backend.services import runtime_events
    monkeypatch.setattr(runtime_events, 'emit_best_effort', lambda *a, **k: (_ for _ in ()).throw(OSError('audit offline')))
    monkeypatch.setattr(service, 'audit', SessionNoteService.audit.__get__(service))
    result, req = save(service, draft)
    assert service.detail(result['note_id'])['revision'] == 1
    assert service.save(draft['id'], req) == result


def _representative_cases():
    from pathlib import Path
    return json.loads((Path(__file__).parent / 'fixtures/session_notes/representative-v1.json').read_text())['cases']


@pytest.mark.parametrize('case', _representative_cases(), ids=lambda c: c['id'])
def test_representative_fixtures_snapshot_and_traceability_only(service, case):
    # These synthetic fixtures do not assert the model's semantic organization quality.
    for message in case['messages']:
        fields = {k: v for k, v in message.items() if k not in {'role', 'content'}}
        cm.append_message(case['id'], message['role'], message['content'], **fields)
    preflight, snapshot = service.preflight({'conversation_id': case['id']}, case['structure_hint'])
    assert preflight['message_count'] == len(case['messages'])
    assert [s['content'] for s in snapshot['sources']] == [m['content'] for m in case['messages']]
    result = generate(snapshot, call=fake_call, structure_hint=case['structure_hint'])
    assert len(result['quality']['coverage']) == len(case['messages'])
    refs = {s['source_ref_id'] for s in snapshot['sources']}
    assert all(set(block['source_ref_ids']) <= refs for block in result['blocks'])
    reasons = {r for warning in result['quality']['warnings'] for r in warning['reasons']}
    if case['id'] == 'problem-missing-figure':
        assert {'missing_required_input', 'source_unverified', 'image_input_not_owned'} <= reasons
    if case['id'] == 'review-historical':
        assert 'historical_evidence_text_unknown' in reasons
