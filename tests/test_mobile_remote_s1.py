"""Offline photo -> authoritative Session -> reviewed assets, with real image bytes."""
import copy
import io
import json
from pathlib import Path

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from backend import conversation_memory as cm
from backend.api import mistakes, mistake_lifecycle as api
from backend.main import app
from backend.services.learning_task import LearningTaskStore
from backend.services.mistake_images import MistakeImageStore
from backend.services.multimodal_bridge import VisualProblemIR
from backend.services.session_notes.sources import materialize
from backend.services.visual_session_assets import visual_session_text
from memory.mistake_book import MistakeBook
from memory.mistake_lifecycle import MistakeLifecycleStore


def photo(exif=False):
    buf = io.BytesIO()
    meta = Image.Exif()
    if exif:
        meta[274] = 6
    Image.new('RGB', (80, 40), 'white').save(buf, format='JPEG', exif=meta)
    return buf.getvalue()


@pytest.fixture
def chain(tmp_path, monkeypatch):
    images = MistakeImageStore(tmp_path / 'images', frozenset({'.jpg', '.jpeg', '.png', '.webp', '.bmp'}), 20*1024*1024, 1600, 86, 3600)
    tasks = LearningTaskStore(tmp_path / 'progress')
    book = MistakeBook(tmp_path / 'mistakes.db')
    monkeypatch.setattr(cm, 'CONV_DIR', tmp_path / 'conversations')
    monkeypatch.setattr(mistakes, '_image_store', images)
    monkeypatch.setattr(api, '_image_store', images)
    monkeypatch.setattr(mistakes, 'get_learning_task_store', lambda: tasks)
    from backend.services import learning_task
    monkeypatch.setattr(learning_task, 'get_learning_task_store', lambda: tasks)
    monkeypatch.setattr(api, '_store', lambda _: MistakeLifecycleStore(book.store))
    monkeypatch.setattr(api, '_mb', lambda _: book)
    ir = VisualProblemIR(problem_text=r'求 $\lim_{x\to0}\frac{x-\sin x}{x^3}$。', formulas=[r'\sin x=x-\frac{x^3}{6}+o(x^3)'], options=['A. 0', 'B. 1/6'], visual_summary='完整例题', relations=[{'description': '坐标轴与函数图像'}])
    answer = '保留三阶项，结果为 $1/6$。\n\n' + '推导说明。' * 1100
    monkeypatch.setattr(mistakes, '_ocr_image_with_kimi', lambda *a, **k: copy.deepcopy(ir))
    monkeypatch.setattr(mistakes, '_iter_visual_solution_chunks', lambda *a, **k: iter([answer]))
    monkeypatch.setattr(mistakes, '_link_mistake_concepts', lambda *a, **k: [])
    monkeypatch.setattr(mistakes, '_verify_visual_answer', lambda text, **k: (text, {'passed': True, 'status': 'passed'}))
    return TestClient(app), images, tasks, book, ir, answer


def test_photo_session_mistake_and_note_freeze_preserve_complete_assets(chain):
    client, images, tasks, book, ir, answer = chain
    original = photo(exif=True)
    result = client.post('/api/mistakes/solve-image-stream',
        files={'file': ('crop.jpg', photo(), 'image/jpeg'), 'original_file': ('camera.jpg', original, 'image/jpeg')},
        data={'conversation_id': 's1-photo', 'turn_id': 's1-turn', 'question': '请完整讲解这道题', 'user_answer': '不会做'})
    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    task_id = events[-1]['execution_event']['task_id']
    assert events[-1]['execution_event']['type'] == 'final'
    task = tasks.get(task_id)
    assert Path(task.artifacts['original_image_path']).read_bytes() == original
    assert client.get(f'/api/mistakes/tasks/{task_id}/image').content == original
    preview = client.get(f'/api/mistakes/tasks/{task_id}/image?preview=true')
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/jpeg'
    with Image.open(io.BytesIO(preview.content)) as decoded:
        assert decoded.size == (40, 80)  # full frame, EXIF orientation applied
    assert client.get(f'/api/mistakes/tasks/{task_id}/image?preview=true').content == preview.content
    assert Path(task.artifacts['original_image_path']).read_bytes() == original
    history = cm.load_full_history('s1-photo')
    assert len(history) == 2
    user, assistant = history
    assert user['learning_task']['id'] == assistant['learning_task']['id'] == task_id
    assert user['content'] == visual_session_text(task.artifacts)
    assert ir.problem_text in user['content'] and ir.options[1] in user['content']
    assert assistant['content'] == answer and len(answer) > 4000
    request = {'conversation_id': 's1-photo', 'message_id': user['id'], 'turn_id': 's1-turn', 'data': {'question_text': '客户端占位文本'}}
    capture = client.post('/api/mistakes/chat-sources/capture', json=request).json()['data']
    assert client.post('/api/mistakes/chat-sources/capture', json=request).json()['data'] == capture
    draft_id = capture['draft_id']
    draft = client.get(f'/api/mistakes/drafts/{draft_id}').json()['data']
    assert draft['question_text'] == user['content'] and draft['correct_answer'] == draft['explanation'] == answer
    assert draft['visual_ir'] == ir.to_dict() and draft['user_answer'] == '不会做'
    assert draft['source_ref']['task_id'] == task_id
    attachment = draft['attachments'][0]
    assert client.get(f'/api/mistakes/drafts/{draft_id}/attachments/{attachment["id"]}').content == original
    assert not draft['content_complete']
    assert book.list_all() == []
    assert client.post(f'/api/mistakes/drafts/{draft_id}/save', json={'expected_revision': 1, 'operation_id': 'review-missing'}).json()['data']['status'] == 'draft'
    updated = client.patch(f'/api/mistakes/drafts/{draft_id}', json={'expected_revision': 1, 'data': {'content_complete': True}}).json()['data']
    save = {'expected_revision': updated['revision'], 'operation_id': 's1-save'}
    receipt = client.post(f'/api/mistakes/drafts/{draft_id}/save', json=save).json()['data']
    assert client.post(f'/api/mistakes/drafts/{draft_id}/save', json=save).json()['data'] == receipt
    assert client.post(f'/api/mistakes/drafts/{draft_id}/save', json={**save, 'operation_id': 'other-click'}).json()['data'] == receipt
    stale_edit = client.patch(f'/api/mistakes/drafts/{draft_id}', json={'expected_revision': updated['revision'], 'data': {'question_text': '旧标签页修改'}})
    assert stale_edit.status_code == 422 and '正式错题' in stale_edit.text
    record = book.get(receipt['mistake_id'])
    assert record.explanation == record.correct_answer == answer
    assert record.source_ref['task_id'] == task_id and record.visual_ir == ir.to_dict()
    assert Path(record.attachments[0]['original_path']).read_bytes() == original
    assert len(book.list_all()) == 1
    assert client.post('/api/mistakes/chat-sources/capture', json=request).json()['data']['mistake_id'] == record.id
    # Same SQLite selection used by Notes: freeze full text, never task's 4000-char preview.
    snapshot = materialize(cm.capture_note_selection('s1-photo'), None)
    assert snapshot['sources'][0]['content'] == user['content']
    assert snapshot['sources'][1]['content'] == answer
    assert snapshot['sources'][0]['learning_task']['id'] == task_id
    assert str(images.image_root) not in json.dumps(snapshot)


def test_exif_work_image_is_upright_original_bytes_unchanged(chain):
    _, images, *_ = chain
    original = photo(exif=True)
    raw, work = images.save_visual_upload(UploadFile(filename='camera.jpg', file=io.BytesIO(original)))
    assert raw.read_bytes() == original
    with Image.open(work) as image:
        assert image.size == (40, 80)
        assert image.getexif().get(274) is None


@pytest.mark.parametrize('name,data', [('broken.jpg', b'bad-image'), ('empty.jpg', b''), ('photo.heic', b'heic')])
def test_invalid_upload_does_not_create_task_or_session(chain, name, data):
    client, images, tasks, *_ = chain
    response = client.post('/api/mistakes/solve-image-stream', files={'file': (name, data, 'image/jpeg')}, data={'conversation_id': 'invalid-photo', 'turn_id': 'turn'})
    assert '"type": "error"' in response.text
    assert cm.load_full_history('invalid-photo') == []
    assert list(tasks.root.glob('*.json')) == []
    assert not list((images.image_root / 'drafts').rglob('*.*'))


def test_chat_capture_rejects_forged_message_or_turn(chain):
    client, *_ = chain
    user = cm.append_message('scope', 'user', '完整问题', turn_id='real-turn')
    for mid, tid in [('absent', 'real-turn'), (user['id'], 'wrong-turn')]:
        response = client.post('/api/mistakes/chat-sources/capture', json={'conversation_id': 'scope', 'message_id': mid, 'turn_id': tid, 'data': {}})
        assert response.status_code in {404, 422}


def test_visual_session_prose_keeps_problem_conditions_without_raw_arrays():
    assets = {'question': '请解题', 'visual_ir': {'problem_text': '求 $x^2=1$ 的解。',
        'entities': [{'id': 'x', 'type': 'variable'}],
        'relations': [{'description': '图中两直线互相垂直'}],
        'formulas': ['$x^2=1$'], 'options': ['A. 1', 'B. ±1'],
        'user_marks': ['圈选 B'], 'required_inputs': [{'name': '附表', 'reason': '需要附表中的数值'}]}}
    prose = visual_session_text(assets)
    assert '求 $x^2=1$ 的解。' in prose and 'B. ±1' in prose
    assert '图中两直线互相垂直' in prose and '需要附表中的数值' in prose
    assert '圈选 B' in prose and 'variable' not in prose and '["' not in prose
    assert assets['visual_ir']['entities'][0]['id'] == 'x'
