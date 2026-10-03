import copy
from pathlib import Path
import pytest
from PIL import Image
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_assets import materialize_document_assets
from ingestion.document_ir import validate_canonical_book, canonical_book_fingerprint, persist_canonical_book, load_canonical_book


def book_with_crop(path='images/crop.png'):
    return MinerUAdapter.from_structured_content(dict(metadata=dict(producer=dict(name='mineru', version='4.0.8')), pages=[
        dict(page_idx=0, blocks=[dict(type='paragraph_title', content='第1章'),
            dict(type='equation', content='y=x+1', image_source=path, bbox=[.1,.2,.4,.5])])]), book_name='demo')


@pytest.mark.parametrize('case', ['missing', 'bad', 'traversal', 'symlink'])
def test_crop_failure_retains_formula_with_warning(tmp_path, case):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'images').mkdir()
    crop = source / 'images/crop.png'
    if case == 'bad': crop.write_text('not an image')
    if case == 'symlink':
        outside = tmp_path / 'outside.png'
        Image.new('RGB', (3,3)).save(outside)
        crop.symlink_to(outside)
    book = book_with_crop('../outside.png' if case == 'traversal' else 'images/crop.png')
    materialize_document_assets(book, source_root=source, progress_root=tmp_path / 'progress')
    formula = book.blocks[-1]
    asset = formula.attributes['original_visual_asset']
    assert asset['status'] == ('invalid' if case == 'bad' else 'missing')
    assert formula.text == 'y=x+1' and formula.equations == ['y=x+1']
    report = validate_canonical_book(book)
    # Direct API untrusted relative paths are rejected by adapter normalization.
    assert report.valid
    assert any(issue.code.startswith('original_visual_asset_') for issue in report.issues)


def test_target_symlink_cannot_write_outside_progress(tmp_path):
    source = tmp_path / 'source'
    (source / 'images').mkdir(parents=True)
    Image.new('RGB', (3,3)).save(source / 'images/crop.png')
    progress = tmp_path / 'progress'
    (progress / 'demo').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (progress / 'demo/original_visuals').symlink_to(outside, target_is_directory=True)
    book = book_with_crop()
    materialize_document_assets(book, source_root=source, progress_root=progress)
    assert book.blocks[-1].attributes['original_visual_asset']['status'] == 'invalid'
    assert not list(outside.iterdir())


def test_ready_contract_requires_path_hash_dimensions_and_matching_provenance():
    book = book_with_crop()
    asset = book.blocks[-1].attributes['original_visual_asset']
    asset.update(status='ready', block_id='wrong')
    codes = {issue.code for issue in validate_canonical_book(book).issues if issue.severity == 'error'}
    assert codes >= {'missing_original_visual_asset_relpath', 'invalid_original_visual_sha256',
                     'invalid_original_visual_dimensions', 'original_visual_provenance_mismatch'}


def test_changed_crop_does_not_overwrite_or_delete_old_asset(tmp_path):
    source = tmp_path / 'source'
    (source / 'images').mkdir(parents=True)
    crop = source / 'images/crop.png'
    Image.new('RGB', (3,3), 'white').save(crop)
    progress = tmp_path / 'progress'
    first = book_with_crop()
    materialize_document_assets(first, source_root=source, progress_root=progress)
    old_path = progress / 'demo' / first.blocks[-1].attributes['original_visual_asset']['asset_relpath']
    old_bytes = old_path.read_bytes()
    Image.new('RGB', (5,4), 'black').save(crop)
    second = book_with_crop()
    materialize_document_assets(second, source_root=source, progress_root=progress)
    assert first.blocks[-1].block_id == second.blocks[-1].block_id
    assert first.blocks[-1].attributes['original_visual_asset']['asset_relpath'] != second.blocks[-1].attributes['original_visual_asset']['asset_relpath']
    assert old_path.read_bytes() == old_bytes


def test_original_crops_survive_existing_progress_backup_and_restore(monkeypatch, tmp_path):
    import backend.data_backup as backup
    data = tmp_path / 'data'
    mineru = tmp_path / 'source'
    (mineru / 'images').mkdir(parents=True)
    Image.new('RGB', (3,3), 'white').save(mineru / 'images/crop.png')
    progress = data / 'progress'
    book = book_with_crop()
    materialize_document_assets(book, source_root=mineru, progress_root=progress)
    persist_canonical_book(book, progress_root=progress)
    monkeypatch.setattr(backup, 'DATA_ROOT', data)
    monkeypatch.setattr(backup, 'MINERU_ROOT', tmp_path / 'mineru')
    monkeypatch.setattr(backup, 'BACKUP_ROOT', tmp_path / 'backups')
    monkeypatch.setattr(backup, 'PENDING_RESTORE_PATH', tmp_path / 'backups/pending_restore.json')
    monkeypatch.setattr(backup, 'RESTORE_RESULT_PATH', tmp_path / 'backups/last_restore.json')
    saved = backup.create_backup()
    asset = progress / 'demo' / book.blocks[-1].attributes['original_visual_asset']['asset_relpath']
    expected = asset.read_bytes()
    asset.write_bytes(b'damaged')
    backup.schedule_restore(saved['name'])
    assert backup.apply_pending_restore()['status'] == 'completed'
    assert asset.read_bytes() == expected
    assert canonical_book_fingerprint(load_canonical_book('demo', progress_root=progress)) == canonical_book_fingerprint(book)
