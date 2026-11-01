"""Source-backed review, bounded paid-call dispatch and delivered exercise images."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.document_structure import apply_structure_review
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_workflows import canonical_outline
from backend.services.document_structure_review import run_review
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
from backend.services.exercise_assets import attachment_file
from llm.types import Capability, ModelRole, ProviderSpec, ResolvedModelRole
from memory.exercise_bank import ExerciseRecord
from memory.exercise_candidate_projection import content_hash, project_units
from memory.exercise_file_importer import ExtractedExerciseText


def source_book():
    def block(bid, text, page, kind='paragraph', **attrs):
        return DocumentBlock(bid, kind, text, ['第一章 基础', '习题'], page_start=page, page_end=page, source_kind='mineru', attributes=attrs)
    return CanonicalBook('教材', 'mineru', [block('q1', '1.1 根据图1-1说明测量方法。', 1),
        block('q2', '1.2 根据图1-2说明另一测量方法。', 2),
        block('f1', '图1-1 测量装置', 2, 'figure'), block('f2', '图1-2 另一装置', 2, 'figure')], 'test', source_page_count=2)


def model():
    provider = ProviderSpec('openai_compatible', 'test', 'openai_compatible', frozenset({Capability.VISION}),
                            'https://never-called.invalid', {}, requires_api_key=False)
    return ResolvedModelRole(ModelRole.VISION, provider, 'fixture-vision', '', provider.default_endpoint)


def test_native_toc_roles_do_not_require_missing_body_chapters():
    payload = dict(metadata=dict(producer=dict(name='MinerU', version='4.0.12')), pages=[
        dict(page_idx=0, blocks=[dict(type='paragraph_title', content='目录 CONTENTS'),
            dict(type='paragraph_title', content='第一章 基础'),
            dict(type='index', content='- 第一节 定义 …… (1)\n- 第二章 未提供 …… (80)')]),
        dict(page_idx=3, blocks=[dict(type='paragraph_title', content='第一章 基础'),
            dict(type='text', content='教材正文保留。')])])
    book = MinerUAdapter.from_structured_content(payload, book_name='部分教材')
    outline = canonical_outline(book)
    assert [(c['title'], c['page_number']) for c in outline] == [('第一章 基础', 4)]
    assert book.blocks[1].attributes['outline_toc']
    assert any('第二章 未提供' in b.text for b in book.blocks)


def test_review_owns_figures_across_ocr_order_without_rewriting_sources():
    book = source_book(); before = deepcopy(book)
    result = apply_structure_review(book, [dict(block_id='f1', role='exercise', unit_id='q1', unit_role='explanation')])
    assert book == before
    assert [(b.block_id, b.text, b.page_start, b.bbox) for b in result.blocks] == [(b.block_id, b.text, b.page_start, b.bbox) for b in before.blocks]
    from backend.services.exercise_file_analysis import file_book
    from memory.exercise_structure import exercise_units
    projected = file_book(ExtractedExerciseText('', 'zip', canonical_book=result), name='教材')
    units = exercise_units(projected, unrestricted=True)
    first = next(u for u in units if u['text'].startswith('1.1'))
    second = next(u for u in units if u['text'].startswith('1.2'))
    assert '图1-1 测量装置' in first['text'] and '图1-1 测量装置' not in second['text']


def test_unknown_sources_and_incomplete_spans_are_rejected():
    with pytest.raises(ValueError, match='未知'):
        apply_structure_review(source_book(), [dict(block_id='invented', role='exercise')])
    with pytest.raises(ValueError, match='遗漏'):
        apply_structure_review(source_book(), [dict(block_id='q1', segments=[dict(start=0, end=2, role='exercise')])])


def test_review_is_bounded_cached_and_never_retries_failed_paid_calls(tmp_path):
    book = source_book(); calls = []
    def complete(resolved, **kwargs):
        calls.append(kwargs)
        text = json.loads(kwargs['messages'][1]['content'][0]['text'])
        assert text['review_pages'] == [1]
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"blocks":[],"unresolved":[]}'))],
                               usage=SimpleNamespace(model_dump=lambda: dict(prompt_tokens=300, completion_tokens=20)))
    reviewed, report = run_review(book, directory=tmp_path / 'done', mode='all', max_pages=1, resolved=model(), complete=complete)
    assert report['plan']['coverage'] == 'selected_pages' and report['plan']['omitted_pages'] == [2]
    run_review(book, directory=tmp_path / 'done', mode='all', max_pages=1, resolved=model(), complete=complete)
    assert len(calls) == 1
    def failed(*args, **kwargs):
        calls.append(kwargs); raise RuntimeError('must not persist secret-provider-error')
    _, report = run_review(book, directory=tmp_path / 'failed', mode='all', max_pages=1, resolved=model(), complete=failed)
    run_review(book, directory=tmp_path / 'failed', mode='all', max_pages=1, resolved=model(), complete=failed)
    assert len(calls) == 2 and report['status'] == 'partial'
    assert 'secret-provider-error' not in (tmp_path / 'failed' / 'structure_review.json').read_text()
    _, report = run_review(book, directory=tmp_path / 'budget', mode='all', max_pages=1, resolved=model(), complete=complete,
        budget=dict(input_price=10, output_price=20, max_cost_cny=0.00001))
    assert len(calls) == 2 and report['budget_blocked_pages'] == [1]


def test_ready_source_image_survives_admission_and_original_source_removal(tmp_path):
    book = source_book()
    book.blocks = [b for b in book.blocks if b.block_id != 'f1']
    root = tmp_path / 'source'; root.mkdir()
    Image.new('RGB', (80, 80), 'white').save(root / 'diagram.png')
    for b in book.blocks:
        if b.block_type == 'figure':
            b.attributes.update(source_asset_relpath='diagram.png')
    store = ExerciseFileAnalysisStore(tmp_path / 'progress')
    extracted, sid, _ = store.create(ExtractedExerciseText('source', 'zip', canonical_book=book, asset_root=root), book_name='教材')
    scope = dict(chapter='', page_start=None, page_end=None, source_mode='file')
    proposals = project_units(extracted.units, extracted.source_blocks, extracted.canonical_hash, scope,
                              profile_version=extracted.profile_version, source_id=sid)
    proposal = next(p for p in proposals if p['question_text'].startswith('1.2'))
    item = dict(origin_id='candidate', question_text=proposal['question_text'], answer=proposal['answer'], explanation=proposal['explanation'])
    item['candidate_context'] = dict(projection=proposal['projection'], review=dict(content_hash=content_hash({**item, 'projection': proposal['projection']}),
        resolutions=[dict(issue_key=i['key'], decision='source_checked') for i in proposal['issues'] if i['category'] == 'content']))
    receipt = ExerciseCandidateReviewService(progress_root=tmp_path / 'progress', file_provider=lambda s, n: store.load(s, n)).prepare('教材', [item])[0]
    assert receipt['attachments']
    record = ExerciseRecord(question_text=item['question_text'], extra_fields=dict(source_attachments=receipt['attachments']))
    asset = receipt['attachments'][0]['asset_id']
    (root / 'diagram.png').unlink()
    for path in (store.root / 'assets').iterdir(): path.unlink()
    path, mime = attachment_file(record, asset, progress_root=tmp_path / 'progress')
    assert path.is_file() and mime == 'image/png'
    with pytest.raises(FileNotFoundError):
        attachment_file(ExerciseRecord(question_text='other record'), asset, progress_root=tmp_path / 'progress')


def test_exercise_images_survive_standard_backup_restore(monkeypatch, tmp_path):
    import backend.data_backup as backup
    from memory.exercise_bank import ExerciseBank
    data = tmp_path / 'data'; progress = data / 'progress'
    assets = progress / 'exercise_assets'; assets.mkdir(parents=True)
    aid = 'a' * 64
    Image.new('RGB', (40, 40), 'white').save(assets / (aid + '.png'))
    record = ExerciseRecord(question_text='根据图1-1作答', extra_fields=dict(source_attachments=[dict(asset_id=aid, format='.png', role='question', label='图1-1')]))
    bank = ExerciseBank(progress / 'exercises.db'); bank.add(record)
    monkeypatch.setattr(backup, 'DATA_ROOT', data)
    monkeypatch.setattr(backup, 'MINERU_ROOT', tmp_path / 'mineru')
    monkeypatch.setattr(backup, 'BACKUP_ROOT', tmp_path / 'backups')
    monkeypatch.setattr(backup, 'PENDING_RESTORE_PATH', tmp_path / 'backups' / 'pending.json')
    monkeypatch.setattr(backup, 'RESTORE_RESULT_PATH', tmp_path / 'backups' / 'result.json')
    saved = backup.create_backup()
    (assets / (aid + '.png')).unlink()
    backup.schedule_restore(saved['name'])
    assert backup.apply_pending_restore()['status'] == 'completed'
    restored = ExerciseBank(progress / 'exercises.db').get(record.id)
    assert attachment_file(restored, aid, progress_root=progress)[0].is_file()


def test_associating_original_pdf_invalidates_crop_only_review_cache(tmp_path):
    import fitz
    calls = []
    def complete(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"blocks":[],"unresolved":[]}'))], usage={})
    options = dict(directory=tmp_path / 'review', max_pages=1, resolved=model(), complete=complete)
    run_review(source_book(), **options)
    pdf = tmp_path / 'source.pdf'
    with fitz.open() as document:
        document.new_page(); document.new_page(); document.save(pdf)
    _, report = run_review(source_book(), pdf_path=pdf, **options)
    assert len(calls) == 2
    assert report['batches'][0]['coverage']['full_page_images'] == [1]


def test_structure_job_persists_candidate_without_activating_book(monkeypatch, tmp_path):
    from backend.job_manager import JobManager
    from backend.services import structure_review_jobs as service
    jobs = JobManager(tmp_path / 'jobs.sqlite3')
    book = source_book()
    target = dict(kind='book', reference='教材', book_name='教材')
    monkeypatch.setattr(service, 'resolve_source', lambda *a, **kw: (book, None, None))
    monkeypatch.setattr('llm.factory.create_vision_completion', lambda *a, **kw:
        SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"blocks":[],"unresolved":[]}'))], usage={}))
    job = jobs.create_job('document_structure_review', dict(target=target, book_name='教材', mode='all', max_pages=1,
        budget=dict(input_price=1, output_price=1, max_cost_cny=1)), status='running')
    directory = service.review_directory(tmp_path, 'book', '教材')
    service._run(job=job, book=book, assets=None, pdf=None, directory=directory,
                 progress_root=tmp_path, books_root=tmp_path, jobs=jobs, resolved=model())
    assert jobs.get_job(job['id'])['status'] == 'completed'
    assert service.load_reviewed_candidate(book, directory).source_metadata['structure_review']['model'] == 'fixture-vision'
    assert not (tmp_path / '教材' / 'canonical_document.jsonl').exists()


def test_file_review_retains_separately_imported_answers(monkeypatch, tmp_path):
    from backend.job_manager import JobManager
    from backend.services import structure_review_jobs as service
    book = CanonicalBook('教材', 'fixture', [DocumentBlock('q1', 'paragraph', '1. 求测量误差。', ['教材'],
        page_start=1, page_end=1, source_kind='mineru')], 'fixture', source_page_count=1)
    store = ExerciseFileAnalysisStore(tmp_path)
    extracted, sid, paired = store.create(ExtractedExerciseText(book.blocks[0].text, 'zip', canonical_book=book), book_name='教材',
        answer=ExtractedExerciseText('1. 解：误差为2。', 'docx'))
    assert paired == 1
    jobs = JobManager(tmp_path / 'jobs.sqlite3')
    target = dict(kind='file', reference=sid, book_name='教材')
    monkeypatch.setattr('llm.factory.create_vision_completion', lambda *a, **kw:
        SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"blocks":[],"unresolved":[]}'))], usage={}))
    job = jobs.create_job('document_structure_review', dict(target=target, book_name='教材', mode='all', max_pages=1,
        budget=dict(input_price=1, output_price=1, max_cost_cny=1)), status='running')
    service._run(job=job, book=book, assets=None, pdf=None, directory=tmp_path / 'review',
                 progress_root=tmp_path, books_root=tmp_path, jobs=jobs, resolved=model())
    finished = jobs.get_job(job['id'])
    assert finished['status'] == 'completed'
    new_source = store.load(finished['result']['source_id'], '教材')
    assert any('误差为2' in b['text'] for b in new_source.source_blocks)
    assert new_source.units[0]['answer_block_ids']


def test_deepseek_flash_vision_request_disables_thinking_locally():
    from llm.configuration import resolve_model_role
    from llm.factory import create_vision_completion, vision_without_thinking, vision_image_token_reservation
    calls = []
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw))))
    for name in ('deepseek-flash', 'deepseek-v4-flash'):
        original = resolve_model_role('vision', dict(LLM_VISION_PROVIDER='deepseek', LLM_VISION_MODEL=name, LLM_VISION_API_KEY='fixture'))
        options = deepcopy(original.options)
        resolved = vision_without_thinking(original)
        create_vision_completion(resolved, messages=[dict(role='user', content=[dict(type='image_url', image_url=dict(url='data:image/png;base64,AAAA'))])],
                                 max_tokens=32, timeout=1, client=client)
        assert calls[-1]['extra_body']['thinking'] == dict(type='disabled')
        assert calls[-1]['messages'][0]['content'][0]['type'] == 'image_url'
        assert original.options == options
        assert vision_image_token_reservation(resolved) == 1024


def test_answer_uses_managed_figure_and_preserves_visual_uncertainty(monkeypatch, tmp_path):
    from backend.services import exercise_answers as answers
    aid = 'b' * 64
    image = tmp_path / 'exercise_assets' / (aid + '.png'); image.parent.mkdir()
    Image.new('RGB', (40, 40), 'white').save(image)
    record = ExerciseRecord(question_text='根据图1-1求标准差。', extra_fields=dict(source_attachments=[
        dict(asset_id=aid, format='.png', role='question', label='图1-1')]))
    calls = []
    monkeypatch.setattr('config.PROGRESS_PATH', tmp_path)
    monkeypatch.setattr('config.get_model_role_config', lambda _: model())
    monkeypatch.setattr(answers, 'retrieve_node', lambda _: {})
    monkeypatch.setattr(answers, 'has_textbook_evidence', lambda _: True)
    monkeypatch.setattr(answers, 'prepare_answer_generation', lambda _: [])
    def vision(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(
            dict(problem_text='图中概率密度', visual_summary='对称密度图', uncertainties=['纵轴标注模糊']))))])
    monkeypatch.setattr('llm.factory.create_vision_completion', vision)
    messages = []
    monkeypatch.setattr('config.get_llm', lambda **_: SimpleNamespace(invoke=lambda content:
        (messages.extend(content) or SimpleNamespace(content='答案草稿'))))
    monkeypatch.setattr('backend.services.exercise_knowledge.prepare_analysis', lambda *a, **kw: {})
    monkeypatch.setattr('backend.services.exercise_knowledge.analysis_instruction', lambda _: '知识分析')
    monkeypatch.setattr('backend.services.exercise_knowledge.parse_analysis', lambda draft, _: (draft, {}, None, 'unverified'))
    def finalized(state, text):
        state['answer_verification'] = dict(status='passed')
        return text
    monkeypatch.setattr(answers, 'finalize_generated_answer', finalized)
    state = dict(book_name='教材', required_outputs=[])
    result = answers._generate_draft(record, state)
    assert result['delivery_status'] == 'unverified'
    assert any(item['type'] == 'image_url' for item in calls[0]['messages'][0]['content'])
    assert any('对称密度图' in message.content for message in messages)
    image.unlink()
    assert answers._generate_draft(record, state)['delivery_status'] == 'waiting_for_input'
    assert len(calls) == 1
