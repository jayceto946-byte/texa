"""Exercise import must read its UTF-8 state under a Chinese Windows locale."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.import_review_session import ReviewSession
from backend.services.document_structure_review import run_review
from backend.services.structure_review_jobs import resolve_source
from ingestion.document_ir import CanonicalBook, DocumentBlock
from llm.configuration import resolve_model_role


@pytest.fixture(autouse=True)
def gbk_default_for_local_state(tmp_path, monkeypatch):
    original = Path.open

    def windows_open(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding in (None, 'locale') and path.is_relative_to(tmp_path):
            encoding = 'gbk'
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, 'open', windows_open)


def docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def model():
    return resolve_model_role('vision', dict(LLM_VISION_PROVIDER='deepseek',
        LLM_VISION_MODEL='deepseek-flash', LLM_VISION_API_KEY='fixture'))


def test_chinese_upload_with_answer_can_be_reopened_and_reviewed(tmp_path, monkeypatch):
    from backend.api import exercises
    monkeypatch.setattr(exercises, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(exercises, 'PROGRESS_PATH', tmp_path)
    monkeypatch.setattr(exercises, '_bank', lambda _: SimpleNamespace(list_all=lambda **kw: []))
    app = FastAPI()
    app.include_router(exercises.router)
    with TestClient(app) as client:
        result = client.post('/exercises/upload-analyze?book_name=习题讲义',
            data=dict(candidate_contract_version=1), files={
                'file': ('习题.docx', docx('1. 求给定函数的导数。')),
                'answer_file': ('答案.docx', docx('1. 解：导数为二倍自变量。')),
            }).json()
    assert result['success'], result
    assert result['summary']['paired_answers'] == 1
    sid = result['extract']['source_id']
    store = ExerciseFileAnalysisStore(tmp_path)
    loaded = store.load(sid, '习题讲义')
    assert '求给定函数的导数。' in loaded.text
    assert store.answer_source(sid, '习题讲义').text == '1. 解：导数为二倍自变量。'
    assert store.review_reference(sid, '习题讲义') == sid
    book, _, _ = resolve_source(dict(kind='file', reference=sid, book_name='习题讲义'),
        progress_root=tmp_path, books_root=tmp_path, jobs=None)
    assert book.blocks[0].text == '1. 求给定函数的导数。'


def test_semantic_review_reuses_chinese_receipt_without_another_call(tmp_path):
    calls = []
    expected = dict(note='保留原题，待人工核对。')

    def complete(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps(expected, ensure_ascii=False)))], usage={})

    options = dict(resolved=model(), directory=tmp_path, identity=dict(source='习题讲义'), complete=complete)
    assert ReviewSession(**options).call('batch', '校对题目', '原题内容') == expected
    assert ReviewSession(**options).call('batch', '校对题目', '原题内容') == expected
    assert len(calls) == 1


def test_structure_review_reuses_chinese_receipt_without_another_call(tmp_path):
    calls = []

    def complete(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps(dict(blocks=[],
                unresolved=['图像模糊，待人工核对。']), ensure_ascii=False)))], usage={})

    book = CanonicalBook('习题讲义', 'fixture', [DocumentBlock('q', 'paragraph',
        '1. 求给定函数的导数。', ['习题'], page_start=1, page_end=1)], 'fixture', source_page_count=1)
    options = dict(directory=tmp_path, resolved=model(), complete=complete, max_pages=1)
    run_review(book, **options)
    run_review(book, **options)
    assert len(calls) == 1
