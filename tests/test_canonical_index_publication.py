import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from ingestion import mineru_importer, index_pipeline, lexical_index
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_ir import load_canonical_book, canonical_book_fingerprint, canonical_paths
from ingestion.index_snapshot import index_read_snapshot
from test_index_pipeline import FakeStore


def setup(monkeypatch, tmp_path):
    vector = tmp_path / 'vector'
    progress = tmp_path / 'progress'
    source = tmp_path / 'source'
    (source / 'images').mkdir(parents=True)
    Image.new('RGB', (24,12), 'white').save(source / 'images/f.png')
    monkeypatch.setattr(index_pipeline, 'VECTOR_DB_PATH', vector)
    monkeypatch.setattr(lexical_index, 'VECTOR_DB_PATH', vector)
    monkeypatch.setattr(mineru_importer, 'load_kg_chunk_roles', lambda _: {})
    store = FakeStore(vector)
    monkeypatch.setattr(mineru_importer, 'get_vector_store', lambda: store)
    # These tests target publication failure injection, not retrieval scores.
    monkeypatch.setattr(index_pipeline, '_validate_staged_production_retrieval', lambda *_args, **_kwargs: dict(passed=True))
    return store, source, progress


def book(text):
    return MinerUAdapter.from_structured_content(dict(metadata=dict(producer=dict(name='mineru', version='4.0.8')),
        pages=[dict(page_idx=0, blocks=[dict(type='paragraph_title', content='第1章'),
            dict(type='text', content=text), dict(type='equation', content='y=x+1', image_source='images/f.png')])]), book_name='demo')


def publish(source, progress, text, before=None):
    canonical = book(text)
    mineru_importer.build_index_from_chapters('demo', [], source, canonical_book=canonical,
        canonical_progress_root=progress, before_publish=before)
    return canonical


def snapshot(store, progress):
    with index_read_snapshot():
        loaded = load_canonical_book('demo', progress_root=progress)
        manifest = index_pipeline.load_index_manifest('demo')
        rows = json.loads(lexical_index.index_path('demo').read_text())
        assert manifest['canonical_hash'] == canonical_book_fingerprint(loaded)
        assert {r['canonical_hash'] for r in rows} == {manifest['canonical_hash']}
        assert {r['index_version'] for r in rows} == {manifest['index_version']}
        blocks = {b.block_id for b in loaded.blocks}
        assert all(set(r['source_block_ids']) <= blocks for r in rows)
        for b in loaded.blocks:
            asset = b.attributes.get('original_visual_asset')
            if asset and asset['status'] == 'ready':
                assert (progress / 'demo' / asset['asset_relpath']).is_file()
        return manifest['index_version'], canonical_book_fingerprint(loaded)


@pytest.mark.parametrize('mode', ['gate', 'cancel', 'write', 'interrupt'])
def test_failed_update_restores_ir_assets_lexical_map_and_manifest(monkeypatch, tmp_path, mode):
    store, source, progress = setup(monkeypatch, tmp_path)
    publish(source, progress, '旧版定义：旧教材正文保留用于稳定检索。')
    old_snapshot = snapshot(store, progress)
    files = {p: p.read_bytes() for p in (progress / 'demo').rglob('*') if p.is_file()}
    old_map = dict(store._map)
    old_lexical = lexical_index.index_path('demo').read_bytes()
    if mode == 'gate':
        def gate(*_args, **_kwargs):
            assert snapshot(store, progress) == old_snapshot
            raise RuntimeError('gate failed')
        monkeypatch.setattr(index_pipeline, '_validate_staged_production_retrieval', gate)
    if mode in {'write','interrupt'}:
        original = index_pipeline.atomic_write_json
        def write(path, data):
            if Path(path) == index_pipeline.manifest_path('demo') and data.get('canonical_hash') != old_snapshot[1]:
                raise (KeyboardInterrupt('interrupt') if mode == 'interrupt' else RuntimeError('write failed'))
            return original(path, data)
        monkeypatch.setattr(index_pipeline, 'atomic_write_json', write)
    def cancel(): raise RuntimeError('cancelled')
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        publish(source, progress, '新版定义：候选不同正文，不得污染旧版本。', cancel if mode == 'cancel' else None)
    assert snapshot(store, progress) == old_snapshot
    assert store._map == old_map
    assert lexical_index.index_path('demo').read_bytes() == old_lexical
    assert all(p.read_bytes() == data for p, data in files.items())


def test_candidate_gate_reads_old_version_and_retry_is_idempotent(monkeypatch, tmp_path):
    store, source, progress = setup(monkeypatch, tmp_path)
    publish(source, progress, '旧版定义：旧教材正文。')
    old = snapshot(store, progress)
    observations = []
    def gate(*_args, **_kwargs):
        observations.append(snapshot(store, progress))
        return dict(passed=True)
    monkeypatch.setattr(index_pipeline, '_validate_staged_production_retrieval', gate)
    publish(source, progress, '新版定义：候选教材正文。')
    new = snapshot(store, progress)
    assert old != new and observations == [old]
    publish(source, progress, '新版定义：候选教材正文。')
    assert snapshot(store, progress) == new
    assert len(list((progress / 'demo/original_visuals').iterdir())) == 1
    rollback = index_pipeline.activate_retained_index_version(store, 'demo', old[0])
    assert rollback['canonical_hash'] == old[1]
    assert snapshot(store, progress) == old


def test_reader_waits_for_complete_publication_and_never_mixes_versions(monkeypatch, tmp_path):
    import ingestion.document_publication as publication
    store, source, progress = setup(monkeypatch, tmp_path)
    publish(source, progress, '旧版定义：旧教材正文。')
    entered, release, reader_started = threading.Event(), threading.Event(), threading.Event()
    original = publication._atomic_copy
    def copy(src, target):
        result = original(src, target)
        if target == progress / 'demo/canonical_document.jsonl':
            entered.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(publication, '_atomic_copy', copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(publish, source, progress, '新版定义：候选教材正文。')
        assert entered.wait(3)
        def read():
            reader_started.set()
            return snapshot(store, progress)
        reader = executor.submit(read)
        assert reader_started.wait(3)
        assert not reader.done()
        release.set()
        writer.result(timeout=3)
        assert reader.result(timeout=3) == snapshot(store, progress)


def test_non_authoritative_chunk_projection_write_failure_is_not_failed_import(monkeypatch, tmp_path):
    import utils.json_io as json_io
    store, source, progress = setup(monkeypatch, tmp_path)
    original = json_io.atomic_write_json
    def write(path, data):
        if str(path).endswith('_middle_chunks.json'):
            raise OSError('diagnostic disk full')
        return original(path, data)
    monkeypatch.setattr(json_io, 'atomic_write_json', write)
    publish(source, progress, '定义：诊断文件失败不撤销成功发布的教材正文。')
    snapshot(store, progress)


def test_mismatched_old_ir_is_never_bound_to_retained_index(monkeypatch, tmp_path):
    from ingestion.document_ir import persist_canonical_book
    store, source, progress = setup(monkeypatch, tmp_path)
    publish(source, progress, '旧版定义：索引对应的正文。')
    old_version = snapshot(store, progress)[0]
    # Simulate the pre-fix same-name failed import, which replaced only the IR.
    persist_canonical_book(book('孤立正文：不对应旧索引。'), progress_root=progress)
    publish(source, progress, '新版定义：新索引对应的正文。')
    with pytest.raises(RuntimeError, match='no Canonical snapshot'):
        index_pipeline.activate_retained_index_version(store, 'demo', old_version)
    snapshot(store, progress)
