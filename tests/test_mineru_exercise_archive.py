"""MinerU ZIP -> exact candidate sources; never OCR, model, or textbook index."""
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from memory.exercise_file_importer import extract_exercise_text
from memory.textbook_exercise_importer import analyze_learning_unit_candidates


def archive_bytes():
    data = dict(metadata=dict(producer=dict(name='mineru', version='4.0.12'), document=dict(page_count=2)), pages=[
        dict(page_idx=0, blocks=[dict(type='paragraph_title', content='第2章 合成习题', level=2),
            dict(type='paragraph_title', content='思考题与习题', level=2),
            dict(type='paragraph_title', content='2-1 已知线性转换关系，求输出量。', level=2),
            dict(type='equation', content='y=kx'), dict(type='text', content='解：将给定输入代入关系式。')]),
        dict(page_idx=1, blocks=[dict(type='text', content='2-2 根据图2.1及表中参数，说明电桥的连接方法。'),
            dict(type='table', content='| 参数 | 数值 |\n|---|---|\n| R | 2 |'),
            dict(type='image', content='', captions=[dict(content='图2.1 合成电桥')], image_source='images/circuit.png',
                 bbox=[.1, .1, .8, .8])])])
    png = io.BytesIO()
    image = Image.new('RGB', (320, 160), 'white')
    drawing = ImageDraw.Draw(image)
    drawing.line([(40, 80), (110, 80), (110, 50), (210, 50), (210, 80), (280, 80)], fill='black', width=3)
    drawing.rectangle((135, 40, 185, 60), fill='white', outline='black', width=2)
    drawing.text((60, 110), 'Synthetic source figure / R', fill='black')
    image.save(png, format='PNG')
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        archive.writestr('parsed/structured_content.json', json.dumps(data, ensure_ascii=False))
        archive.writestr('parsed/images/circuit.png', png.getvalue())
    return result.getvalue()


def test_archive_keeps_sources_assets_pages_and_server_replay(tmp_path, monkeypatch):
    import memory.exercise_file_importer as module
    monkeypatch.setattr(module, 'MINERU_API_URL', 'https://must-not-be-called.invalid')
    path = tmp_path / '资料.zip'
    path.write_bytes(archive_bytes())
    extracted = extract_exercise_text(path)
    store = ExerciseFileAnalysisStore(tmp_path / 'progress')
    result, source_id, paired = store.create(extracted, book_name='目标题库')
    assert extracted.provider == 'mineru-archive' and extracted.page_count == 2
    assert paired == 0 and len(result.units) == 2
    assert 'y=kx' in result.units[0]['text'] and '解：' in result.units[0]['text']
    assert result.units[0]['page_start'] == 1 and result.units[1]['page_start'] == 2
    assert any(b['block_type'] == 'table' for b in result.source_blocks)
    figure = next(b for b in result.source_blocks if b['block_type'] == 'figure')
    assert figure['attributes']['asset_status'] == 'ready'
    asset_id = figure['attributes']['asset_id']
    # Source is independent of the extraction directory after creation/restart.
    import shutil
    shutil.rmtree(extracted.asset_root)
    reloaded = ExerciseFileAnalysisStore(tmp_path / 'progress').load(source_id, '目标题库')
    assert result.canonical_hash == reloaded.canonical_hash and result.source_blocks == reloaded.source_blocks
    image_path, media_type = store.asset(source_id, asset_id, '目标题库')
    assert image_path.is_file() and media_type == 'image/png'
    with pytest.raises(ValueError):
        store.asset(source_id, asset_id, '其他题库')
    scope = dict(chapter='', page_start=None, page_end=None, source_mode='file')
    candidates = analyze_learning_unit_candidates(result.units, book_name='目标题库', subject='专业课', limit=10,
        source_blocks=result.source_blocks, canonical_hash=result.canonical_hash, scope=scope, source_id=source_id)
    assert len(candidates) == 2 and candidates[0].explanation.startswith('解：')
    assert '解：' not in candidates[0].question_text
    assert candidates[0].projection['structure']['original_number'] == '2-1'
    assert any(i['code'] == 'missing_required_input' for i in candidates[1].issues)
    from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
    service = ExerciseCandidateReviewService(file_provider=lambda sid, book: store.load(sid, book))
    first = candidates[0].to_dict()
    item = dict(origin_id='c1', question_text=first['question_text'], answer=first['answer'], explanation=first['explanation'],
                candidate_context=dict(projection=first['projection'], review=None))
    assert service.prepare('目标题库', [item])[0]['review_kind'] == 'system_proposed'


def test_real_upload_api_and_scoped_image_endpoint(tmp_path, monkeypatch):
    from backend.api import exercises
    monkeypatch.setattr(exercises, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(exercises, 'PROGRESS_PATH', tmp_path / 'progress')
    class Bank:
        def list_all(self, **kwargs):
            return []
    monkeypatch.setattr(exercises, '_bank', lambda _: Bank())
    app = FastAPI()
    app.include_router(exercises.router, prefix='/api')
    client = TestClient(app)
    result = client.post('/api/exercises/upload-analyze?book_name=目标题库',
                         data=dict(candidate_contract_version=1),
                         files=dict(file=('资料.zip', archive_bytes(), 'application/zip'))).json()
    assert result['success'] and result['summary']['total'] == 2
    figure = next(b for b in result['extract']['source_blocks'] if b['block_type'] == 'figure')
    uri = f"/api/exercises/file-sources/{result['extract']['source_id']}/assets/{figure['attributes']['asset_id']}"
    image = client.get(uri, params=dict(book_name='目标题库'))
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert client.get(uri, params=dict(book_name='其他题库')).status_code == 404
    assert not list((tmp_path / 'uploads').glob('mineru-exercises-*'))


def test_zip_upload_uses_the_existing_mineru_bundle_limit(tmp_path, monkeypatch):
    from backend.api import exercises
    from backend.security import upload_body_limit
    from utils.resource_limits import MAX_OUTPUT_ZIP_BYTES
    from starlette.datastructures import UploadFile
    monkeypatch.setattr(exercises, 'UPLOAD_DIR', tmp_path)
    captured = []
    monkeypatch.setattr(exercises, 'copy_stream_limited', lambda *args, **kwargs: captured.append(kwargs['max_bytes']))
    exercises._save_upload(UploadFile(filename='source.zip', file=io.BytesIO(b'')))
    assert captured == [MAX_OUTPUT_ZIP_BYTES]
    assert upload_body_limit('/api/exercises/upload-analyze') >= 2 * MAX_OUTPUT_ZIP_BYTES


@pytest.mark.parametrize('names', [['../escape.json'], ['nothing.txt'], ['a/structured_content.json', 'b/structured_content.json']])
def test_invalid_unsafe_and_multiple_documents_do_not_create_source(tmp_path, names):
    path = tmp_path / 'invalid.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for name in names:
            archive.writestr(name, '{}')
    with pytest.raises(ValueError):
        extract_exercise_text(path)
    assert not list(tmp_path.glob('mineru-exercises-*'))
