"""Reusable local figure audit. Findings are evidence, never OCR gold labels.

No model calls and no image editing. Same rules run on every Canonical source.
A clean metadata check cannot prove that a crop contains all original pixels.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from ingestion.document_ir import CanonicalBook, canonical_book_fingerprint
from ingestion.figure_layout import (
    NUMBER, SUBCAPTION, FigureLayout, caption_nodes, is_caption_anchor,
    normalized_box, project_figure_layout,
)

AUDIT_FILENAME = 'figure_audit.json'
AUDIT_SCHEMA = 'texa.figure-audit/v1'
AUDIT_POLICY = 'figure-audit-v1'


def _text_key(text):
    # Whitespace alone is harmless. Keep digits, operators, braces and escapes:
    # math-format differences remain reviewable rather than silently rewritten.
    return re.sub(r'\s+', '', str(text or ''))


def _number(text):
    match = NUMBER.match(text)
    return match.group(1).replace('．', '.').replace('-', '.') if match else ''


def audit_figures(book: CanonicalBook, *, nodes: list[dict] | None = None,
                  asset_root: Path | None = None) -> dict:
    """Audit declared coordinates/captions and optionally verify immutable assets.

    ``error`` means a deterministic contract failure; ``suspect`` means geometry
    or OCR text suggests a problem; ``unverifiable`` means required evidence is
    absent. Page/crop visual completeness remains unverified for all figures.
    """
    blocks = {b.block_id: b for b in book.blocks}
    figures = [b for b in book.blocks if b.block_type == 'figure']
    raw_nodes = caption_nodes(book) if nodes is None else nodes
    findings = {}

    def add(rule, category, members=(), *, evidence=None, action='review_source_page'):
        ids = sorted(set(members))
        payload = dict(rule=rule, category=category, block_ids=ids,
                       pages=sorted({blocks[i].page_start for i in ids if i in blocks
                                     and isinstance(blocks[i].page_start, int)}),
                       evidence=evidence or {}, suggested_action=action)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        findings[digest] = dict(finding_id=digest, **payload)

    duplicate_ids = [bid for bid, count in Counter(b.block_id for b in book.blocks).items() if count > 1]
    for bid in duplicate_ids:
        add('duplicate_block_identity', 'error', [bid], action='repair_source_contract')
    if figures:
        add('source_page_pixels_not_compared', 'unverifiable', [b.block_id for b in figures],
            evidence={'scope': 'whole_book', 'crop_completeness': 'unverified', 'ocr_semantics': 'unverified'},
            action='provide_original_pages_for_visual_comparison')
    usable_nodes = []
    supported = 0
    for node in raw_nodes:
        if not isinstance(node, dict):
            add('invalid_caption_node', 'error', evidence={'node_type': type(node).__name__}, action='repair_source_contract')
            continue
        source = blocks.get(node.get('source_block_id'))
        if (source is None or node.get('page') != source.page_start
                or not normalized_box(node.get('bbox')) or not isinstance(node.get('text'), str)):
            add('invalid_caption_provenance', 'error', [source.block_id] if source else [],
                evidence={'source_block_id': node.get('source_block_id'), 'page': node.get('page'), 'bbox': node.get('bbox')},
                action='repair_source_contract')
            continue
        usable_nodes.append(node)
        key = _text_key(node['text'])
        # Older adapters merged captions into text, newer ones retain separate
        # coordinate nodes. Both are immutable evidence, not inferred text.
        source_texts = [source.text, *[n.get('text', '') for n in source.attributes.get('visual_captions') or [] if isinstance(n, dict)]]
        if key and any(key in _text_key(text) for text in source_texts):
            supported += 1
        else:
            add('caption_text_not_supported_by_ir', 'suspect', [source.block_id],
                evidence={'caption': node['text'], 'bbox': node['bbox'], 'source_text': source.text},
                action='compare_raw_export_and_ir')
        if NUMBER.match(node['text']) and not is_caption_anchor(node['text']):
            add('prose_in_caption', 'suspect', [source.block_id],
                evidence={'caption': node['text'], 'bbox': node['bbox']}, action='separate_caption_from_body')

    page_figures = defaultdict(list)
    geometry_count = assets_checked = 0
    for figure in figures:
        attrs = figure.attributes
        if attrs.get('bbox_units') == 'normalized' and attrs.get('bbox_space') == 'page':
            if not normalized_box(figure.bbox):
                add('invalid_normalized_bbox', 'error', [figure.block_id], evidence={'bbox': figure.bbox}, action='repair_source_contract')
            elif type(figure.page_start) is not int or figure.page_start < 1:
                add('invalid_physical_page', 'error', [figure.block_id], action='repair_source_contract')
            else:
                geometry_count += 1
                page_figures[figure.page_start].append(figure)
        else:
            add('geometry_unavailable', 'unverifiable', [figure.block_id],
                evidence={'bbox_units': attrs.get('bbox_units'), 'bbox_space': attrs.get('bbox_space')}, action='provide_page_coordinates')
        if asset_root is None:
            continue
        rel = attrs.get('asset_relpath')
        if not rel:
            add('asset_unavailable', 'unverifiable', [figure.block_id], action='provide_original_crop')
            continue
        root = asset_root.resolve()
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            add('asset_path_outside_book', 'error', [figure.block_id], action='repair_source_contract')
            continue
        if not path.is_file():
            add('asset_missing', 'error', [figure.block_id], action='restore_original_crop')
            continue
        assets_checked += 1
        expected = attrs.get('content_hash')
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            add('asset_hash_mismatch', 'error', [figure.block_id], action='restore_original_crop')
        elif not expected:
            add('asset_hash_unavailable', 'unverifiable', [figure.block_id], action='record_source_asset_hash')

    # Parent assignment checks are independent of the grouping algorithm.
    # Only a clear better same-page crop is a suspect; proximity is not proof.
    for node in usable_nodes:
        parent = blocks[node['source_block_id']]
        if parent.block_type != 'figure' or not normalized_box(parent.bbox):
            continue
        c = node['bbox']
        center = (c[0] + c[2]) / 2
        nearby = []
        for figure in page_figures[node['page']]:
            box = figure.bbox
            gap = c[1] - box[3]
            if box[0] - .015 <= center <= box[2] + .015 and -.025 <= gap <= .1:
                nearby.append((abs(gap), figure.block_id))
        nearby.sort()
        if nearby and nearby[0][1] != parent.block_id:
            parent_score = next((s for s, bid in nearby if bid == parent.block_id), 1)
            if parent_score - nearby[0][0] > .02 and (len(nearby) == 1 or nearby[1][0] - nearby[0][0] > .012):
                add('caption_parent_geometry_mismatch', 'suspect', [parent.block_id, nearby[0][1]],
                    evidence={'caption': node['text'], 'caption_bbox': c,
                              'declared_parent': parent.block_id, 'nearer_crop': nearby[0][1],
                              'declared_parent_bbox': parent.bbox, 'nearer_crop_bbox': blocks[nearby[0][1]].bbox},
                    action='review_caption_assignment')

    layout = project_figure_layout(book, usable_nodes)
    for issue in layout.issues:
        add(issue['reason'], 'suspect', [issue['block_id']], action='review_group_membership')
    proposals = []
    groups = {tuple(m.block_id for m in group) for group in layout.groups.values()}
    referenced_labels = defaultdict(set)
    for block in book.blocks:
        if block.block_type == 'figure':
            continue
        for number, label in re.findall(r'图\s*(\d+(?:[.．-]\d+)+)\s*[（(]([a-h])[）)]', block.text, re.I):
            referenced_labels[number.replace('．', '.').replace('-', '.')].add(label.lower())
    numbered_details = {tuple(detail['member_ids']): detail for detail in layout.details.values()
                        if detail.get('figure_number')}
    for ids, detail in numbered_details.items():
        observed = {m.group(1).lower() for node in detail['caption_sources']
                    if (m := SUBCAPTION.match(node['text']))}
        referenced = referenced_labels[detail['figure_number']]
        if referenced - observed:
            add('referenced_subcaption_not_observed', 'suspect', ids,
                evidence={'figure_number': detail['figure_number'], 'referenced_labels': sorted(referenced),
                          'observed_ocr_labels': sorted(observed),
                          'note': 'A label may be inside crop pixels; absence from OCR does not prove missing imagery.'})
    for ids in sorted(groups):
        detail = layout.details.get(ids[-1], {})
        members = [blocks[bid] for bid in ids]
        proposals.append(dict(member_ids=list(ids), page=members[0].page_start,
                              figure_number=detail.get('figure_number', ''),
                              review_status='pending', evidence_basis='caption_coordinates' if detail else 'caption_sequence'))
        if detail:
            child_labels = [SUBCAPTION.match(n['text']).group(1).lower()
                            for n in detail['caption_sources'] if SUBCAPTION.match(n['text'])]
            missing = sorted(set(chr(n) for n in range(ord('a'), ord(max(child_labels))+1)) - set(child_labels)) if child_labels else []
            if missing:
                add('subcaption_sequence_gap', 'suspect', ids,
                    evidence={'observed_labels': child_labels, 'missing_ocr_labels': missing,
                              'note': 'Labels may already be inside crop pixels; this is not a missing-image verdict.'})
            for member in members:
                original_number = _number(member.attributes.get('caption') or member.text)
                if original_number and original_number != detail['figure_number']:
                    add('group_number_conflict', 'suspect', ids,
                        evidence={'member_id': member.block_id, 'original_number': original_number,
                                  'proposed_number': detail['figure_number']}, action='review_group_membership')
        if len({b.page_start for b in members}) > 1 or len({tuple(b.section_path) for b in members}) > 1:
            add('group_crosses_source_boundary', 'error', ids, action='split_unsafe_group')

    # Find neighboring crop clusters independently, including anonymous crops
    # and isolated b/c labels that a numbered-caption projection can miss.
    for page, members in page_figures.items():
        edges = defaultdict(set)
        for i, a in enumerate(members):
            for b in members[i+1:]:
                if a.section_path != b.section_path:
                    continue
                xgap = max(0, a.bbox[0]-b.bbox[2], b.bbox[0]-a.bbox[2])
                ygap = max(0, a.bbox[1]-b.bbox[3], b.bbox[1]-a.bbox[3])
                xoverlap = min(a.bbox[2], b.bbox[2])-max(a.bbox[0], b.bbox[0])
                yoverlap = min(a.bbox[3], b.bbox[3])-max(a.bbox[1], b.bbox[1])
                if (xgap <= .18 and yoverlap > .01) or (ygap <= .045 and xoverlap > .03):
                    edges[a.block_id].add(b.block_id)
                    edges[b.block_id].add(a.block_id)
        remaining = set(edges)
        while remaining:
            seed = min(remaining)
            component, pending = set(), [seed]
            while pending:
                bid = pending.pop()
                if bid in component:
                    continue
                component.add(bid)
                pending.extend(edges[bid] - component)
            remaining -= component
            # Distinct explicit numbered figures are a routine adjacent layout.
            explicit = {_number(blocks[bid].text) for bid in component} - {''}
            if len(component) > 1 and len(explicit) <= 1 and not any(component <= set(ids) for ids in groups):
                add('neighboring_crops_without_group', 'suspect', component,
                    evidence={'bboxes': {bid: blocks[bid].bbox for bid in sorted(component)}}, action='review_group_membership')

    counts = Counter(item['category'] for item in findings.values())
    return dict(schema=AUDIT_SCHEMA, policy_version=AUDIT_POLICY, book_name=book.book_name,
                canonical_hash=canonical_book_fingerprint(book),
                caption_nodes_hash=hashlib.sha256(json.dumps(usable_nodes, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                status='blocked' if counts['error'] else 'needs_review' if figures else 'not_applicable',
                summary=dict(figure_blocks=len(figures), geometry_checked=geometry_count,
                             caption_nodes=len(usable_nodes), ir_supported_caption_nodes=supported,
                             assets_checked=assets_checked, proposed_groups=len(proposals),
                             errors=counts['error'], suspects=counts['suspect'], unverifiable=counts['unverifiable']),
                coverage=dict(coordinates='complete' if geometry_count == len(figures) else 'partial',
                              assets='checked' if asset_root is not None else 'not_checked',
                              original_page_pixels='not_checked', crop_completeness='unverified',
                              ocr_semantics='unverified',
                              note='Metadata checks cannot prove crop completeness or OCR correctness; proposed groups require source-page review.'),
                findings=sorted(findings.values(), key=lambda f: (f['category'], f['pages'], f['rule'], f['finding_id'])),
                repair_proposals=proposals)


def verify_figure_repair(book: CanonicalBook, before: FigureLayout, after: FigureLayout,
                         audit: dict) -> dict:
    """Verify relationships without rendering or claiming semantic correctness."""
    failures = []
    blocks = {b.block_id: b for b in book.blocks if b.block_type == 'figure'}
    unique = {tuple(m.block_id for m in g) for g in after.groups.values()}
    for ids in unique:
        if len(set(ids)) != len(ids) or any(bid not in blocks for bid in ids):
            failures.append(dict(rule='invalid_group_members', member_ids=list(ids)))
            continue
        members = [blocks[bid] for bid in ids]
        if len({b.page_start for b in members}) != 1 or len({tuple(b.section_path) for b in members}) != 1:
            failures.append(dict(rule='group_crosses_source_boundary', member_ids=list(ids)))
        if any(tuple(m.block_id for m in after.groups.get(bid, [])) != ids for bid in ids):
            failures.append(dict(rule='inconsistent_group_projection', member_ids=list(ids)))
    for bid, detail in after.details.items():
        if bid not in blocks or any(mid not in blocks for mid in detail['member_ids']):
            failures.append(dict(rule='unknown_figure_identity', member_ids=detail['member_ids']))
    # Catalog covers every crop exactly once; a display merge must not hide it.
    catalog = [set(ids) for ids in unique] + [{bid} for bid in blocks if bid not in after.groups]
    flattened = [bid for item in catalog for bid in item]
    if Counter(flattened) != Counter(blocks.keys()):
        failures.append(dict(rule='catalog_lost_or_duplicated_crop'))
    expected_hash = canonical_book_fingerprint(book)
    if audit.get('canonical_hash') != expected_hash or audit.get('policy_version') != AUDIT_POLICY:
        failures.append(dict(rule='stale_audit'))
    failures.extend(dict(rule=f['rule'], finding_id=f['finding_id']) for f in audit['findings'] if f['category'] == 'error')
    prior = {tuple(m.block_id for m in g) for g in before.groups.values()}
    return dict(schema='texa.figure-repair-verification/v1', canonical_hash=expected_hash,
                policy_version=AUDIT_POLICY, structural_status='failed' if failures else 'passed',
                quality_status='unverified', source_crop_count=len(blocks),
                catalog_crop_count=len(flattened), added_groups=[list(ids) for ids in sorted(unique-prior)],
                removed_groups=[list(ids) for ids in sorted(prior-unique)], failures=failures,
                open_finding_ids=[f['finding_id'] for f in audit['findings'] if f['category'] != 'error'],
                note='Structural preservation only. No finding is closed by successful image composition.')


def compare_audits(before: dict, after: dict) -> dict:
    """Hash/policy fenced issue diff; disappearance is not reviewer acceptance."""
    if before.get('canonical_hash') != after.get('canonical_hash') or before.get('policy_version') != after.get('policy_version'):
        raise ValueError('审核版本或 Canonical 不一致，不能自动对比；需重新建立基线')
    old, new = {f['finding_id'] for f in before['findings']}, {f['finding_id'] for f in after['findings']}
    return dict(new_finding_ids=sorted(new-old), unchanged_finding_ids=sorted(new & old),
                no_longer_detected_ids=sorted(old-new), quality_status='unverified')
