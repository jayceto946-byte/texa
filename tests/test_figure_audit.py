import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingestion.document_ir import CanonicalBook, DocumentBlock, persist_canonical_book, canonical_book_fingerprint
from ingestion.figure_audit import audit_figures, compare_audits, verify_figure_repair
from ingestion.figure_layout import FigureLayout, caption_nodes, project_figure_layout


def figure(bid, box, text='', page=1, nodes=None):
    return DocumentBlock(bid, 'figure', text, ['第一章'], page, page,
                         bbox=box, source_kind='ocr', attributes={
                             'bbox_space': 'page', 'bbox_units': 'normalized',
                             'visual_captions': nodes or []})


def book(figures, name='任意教材', kind='ocr'):
    return CanonicalBook(book_name=name, source_kind=kind, parser_version='adapter-test-v1', blocks=[
        DocumentBlock('body', 'paragraph', '教材正文', ['第一章'], 1, 1, source_kind=kind), *figures])


def test_wrong_parent_is_evidence_not_automatically_accepted():
    a = figure('a', [.1, .1, .4, .2], '(a)')
    b = figure('b', [.6, .1, .9, .2], '(b)\n图1.1组合图', nodes=[
        {'text': '(a)', 'bbox': [.2, .205, .25, .22]},
        {'text': '(b)', 'bbox': [.7, .205, .75, .22]},
        {'text': '图1.1组合图', 'bbox': [.35, .23, .65, .25]}])
    result = audit_figures(book([a, b]))
    findings = [f for f in result['findings'] if f['rule'] == 'caption_parent_geometry_mismatch']
    assert findings[0]['evidence']['declared_parent'] == 'b'
    assert findings[0]['evidence']['nearer_crop'] == 'a'
    assert findings[0]['category'] == 'suspect'
    assert result['repair_proposals'][0]['review_status'] == 'pending'
    assert result['status'] == 'needs_review'
    assert result['coverage']['crop_completeness'] == 'unverified'


def test_prose_must_not_become_group_anchor():
    prose = '图1.2所示为电路，需要比较两个电压后才能求出灵敏度。'
    source = book([figure('a', [.1, .1, .4, .2], prose, nodes=[{'text': prose, 'bbox': [.1, .22, .8, .25]}])])
    report = audit_figures(source)
    assert any(f['rule'] == 'prose_in_caption' for f in report['findings'])
    assert not project_figure_layout(source).details


def test_one_crop_with_internal_labels_not_missing_images():
    # External OCR mentions c/d; a/b can already be inside the single crop.
    source = book([figure('one', [.1, .1, .8, .5], '(c)(d)图2.2', nodes=[
        {'text': '(c)', 'bbox': [.15, .51, .2, .53]},
        {'text': '(d)', 'bbox': [.6, .51, .65, .53]},
        {'text': '图2.2', 'bbox': [.3, .55, .6, .58]}])])
    report = audit_figures(source)
    assert not any(f['rule'] == 'subcaption_sequence_gap' for f in report['findings'])
    assert report['coverage']['original_page_pixels'] == 'not_checked'


def test_assets_are_hash_checked_without_image_modification(tmp_path):
    data = b'immutable crop'
    (tmp_path / 'crop.png').write_bytes(data)
    source = book([figure('one', [.1, .1, .4, .3])])
    source.blocks[-1].attributes.update(asset_relpath='crop.png', content_hash=hashlib.sha256(data).hexdigest())
    result = audit_figures(source, asset_root=tmp_path)
    assert result['summary']['assets_checked'] == 1
    assert not result['summary']['errors']
    assert (tmp_path / 'crop.png').read_bytes() == data
    (tmp_path / 'crop.png').write_bytes(b'changed')
    assert any(f['rule'] == 'asset_hash_mismatch' for f in audit_figures(source, asset_root=tmp_path)['findings'])
    source.blocks[-1].attributes['asset_relpath'] = '../outside.png'
    assert any(f['rule'] == 'asset_path_outside_book' for f in audit_figures(source, asset_root=tmp_path)['findings'])


def test_invalid_provenance_and_bbox_are_contract_errors():
    source = book([figure('one', [.8, .1, .4, .3])])
    result = audit_figures(source, nodes=[{'source_block_id': 'unknown', 'page': 1, 'text': '(a)', 'bbox': [.1, .1, .2, .2]}])
    assert result['status'] == 'blocked'
    assert {f['rule'] for f in result['findings']} >= {'invalid_caption_provenance', 'invalid_normalized_bbox'}


@pytest.mark.parametrize('source_kind', ['mineru', 'ocr', 'pdf', 'word'])
def test_every_source_automatically_persists_audit(tmp_path, source_kind):
    source = book([figure('one', None)], name=source_kind+'教材', kind=source_kind)
    source.blocks[-1].attributes = {}
    assert persist_canonical_book(source, progress_root=tmp_path).valid
    directory = tmp_path / source.book_name
    audit = json.loads((directory / 'figure_audit.json').read_text())
    report = json.loads((directory / 'ingestion_report.json').read_text())
    assert audit['canonical_hash'] == canonical_book_fingerprint(source)
    assert report['valid']  # Diagnostics do not discard usable textbook body.
    assert audit['summary']['unverifiable'] >= 1
    assert audit['coverage']['coordinates'] == 'partial'


def test_stable_findings_and_version_fenced_diff():
    source = book([figure('one', None)])
    first, second = audit_figures(source), audit_figures(source)
    assert first == second
    result = compare_audits(first, second)
    assert not result['new_finding_ids']
    assert len(result['unchanged_finding_ids']) == len(first['findings'])
    with pytest.raises(ValueError, match='Canonical'):
        compare_audits(first, dict(second, canonical_hash='stale'))


def test_repair_verification_rejects_lost_duplicate_cross_page_members():
    a, b = figure('a', [.1, .1, .4, .2]), figure('b', [.6, .1, .9, .2], page=2)
    source = book([a, b])
    unsafe = FigureLayout(groups={'a': [a, b], 'b': [a, b]})
    result = verify_figure_repair(source, FigureLayout(), unsafe, audit_figures(source))
    assert result['structural_status'] == 'failed'
    assert any(f['rule'] == 'group_crosses_source_boundary' for f in result['failures'])
    unsafe = FigureLayout(groups={'a': [a, a], 'b': [a, a]})
    result = verify_figure_repair(source, FigureLayout(), unsafe, audit_figures(source))
    assert any(f['rule'] == 'catalog_lost_or_duplicated_crop' for f in result['failures'])


def test_math_disagreement_is_not_silently_normalized():
    source = book([figure('one', [.1, .1, .4, .2], '图1.1 x+1')])
    node = {'source_block_id': 'one', 'page': 1, 'text': '图1.1 x-1', 'bbox': [.1, .22, .4, .24]}
    result = audit_figures(source, nodes=[node])
    assert any(f['rule'] == 'caption_text_not_supported_by_ir' for f in result['findings'])
    node['text'] = '图 1.1 x + 1'
    assert not any(f['rule'] == 'caption_text_not_supported_by_ir' for f in audit_figures(source, nodes=[node])['findings'])


def test_api_audit_pagination_and_stale_error(monkeypatch, tmp_path):
    from backend.main import app
    import backend.api.books as api
    import backend.services.figure_audit as service
    source = book([figure('one', None)])
    result = audit_figures(source)
    monkeypatch.setattr(api, '_resolve_book_reference', lambda *args, **kwargs: source.book_name)
    monkeypatch.setattr(service, 'textbook_figure_audit', lambda *args, **kwargs: result.copy())
    client = TestClient(app)
    response = client.get('/api/books/任意教材/figure-audit?limit=1')
    assert response.status_code == 200
    assert len(response.json()['data']['findings']) == 1
    assert client.get('/api/books/任意教材/figure-audit?limit=501').status_code == 422
    def stale(*args, **kwargs):
        raise ValueError('审核来源版本不一致')
    monkeypatch.setattr(service, 'textbook_figure_audit', stale)
    assert client.get('/api/books/任意教材/figure-audit').status_code == 409


def test_body_reference_is_suspect_even_when_ocr_label_not_visible():
    source = book([figure('one', [.1, .1, .6, .4], '图1.1', nodes=[
        {'text': '图1.1', 'bbox': [.2, .42, .5, .45]}])])
    source.blocks[0].text = '图1.1(b)说明了连接关系。'
    report = audit_figures(source)
    finding = next(f for f in report['findings'] if f['rule'] == 'referenced_subcaption_not_observed')
    assert finding['category'] == 'suspect'
    assert finding['evidence']['referenced_labels'] == ['b']


def test_derived_audit_publishes_and_restores_with_candidate(tmp_path):
    from ingestion.document_publication import CanonicalPublication
    active, candidate = tmp_path / 'active', tmp_path / 'candidate'
    old = book([figure('one', None)])
    persist_canonical_book(old, progress_root=active)
    old_bytes = (active / old.book_name / 'figure_audit.json').read_bytes()
    new = book([figure('two', [.1, .1, .4, .3])])
    persist_canonical_book(new, progress_root=candidate)
    publication = CanonicalPublication(new.book_name, candidate_root=candidate, progress_root=active)
    publication.publish()
    assert json.loads((active / new.book_name / 'figure_audit.json').read_text())['canonical_hash'] == canonical_book_fingerprint(new)
    publication.restore()
    assert (active / old.book_name / 'figure_audit.json').read_bytes() == old_bytes


def test_batch_cli_keeps_healthy_book_report_when_another_book_is_broken(tmp_path, monkeypatch):
    import scripts.audit_textbook_figures as cli
    progress, vector, output = tmp_path / 'progress', tmp_path / 'vector', tmp_path / 'reports'
    source = book([figure('one', [.1, .1, .4, .3])], name='正常教材')
    persist_canonical_book(source, progress_root=progress)
    canonical = progress / source.book_name / 'canonical_document.jsonl'
    before = canonical.read_bytes()
    bad = progress / '损坏教材'
    bad.mkdir()
    (bad / 'canonical_document.jsonl').write_text('broken json')
    monkeypatch.setattr('sys.argv', ['audit', '--all', '--progress-root', str(progress), '--vector-root', str(vector), '--output-dir', str(output)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    rows = json.loads((output / 'summary.json').read_text())
    assert {row['status'] for row in rows} == {'needs_review', 'failed'}
    assert (output / '正常教材.figure-audit.json').exists()
    assert canonical.read_bytes() == before
