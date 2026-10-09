"""Read-only structural triage of split textbook figures; never an OCR verdict.

Uses existing Canonical blocks/assets only. Does not call models, modify IR,
merge images, rebuild indexes, or change the production grouping rules.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.document_ir import canonical_book_fingerprint
from ingestion.document_workflows import figure_groups, load_workflow_book

NUMBER = re.compile(r'图\s*(\d+(?:[.．-]\d+)+)')
LABEL = re.compile(r'(?:^|\n|(?<=[）)]))\s*[（(]([a-h])[）)]', re.I)
REFERENCE = re.compile(r'图\s*(\d+(?:[.．-]\d+)+)\s*[（(]([a-h])[）)]', re.I)


def numbers(text):
    return list(dict.fromkeys(m.replace('．', '.').replace('-', '.') for m in NUMBER.findall(text)))


def labels(text):
    return LABEL.findall(text.lower())


def valid_box(block):
    box = block.bbox
    return (box is not None and len(box) == 4 and all(0 <= v <= 1 for v in box)
            and box[0] < box[2] and box[1] < box[3])


def neighbors(left, right):
    """Loose layout candidates. Adjacent independent figures can match too."""
    if not valid_box(left) or not valid_box(right):
        return False
    a, b = left.bbox, right.bbox
    x_overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    y_overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    x_gap = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    y_gap = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return ((y_overlap / min(a[3]-a[1], b[3]-b[1]) >= .5 and x_gap <= .18)
            or (x_overlap / min(a[2]-a[0], b[2]-b[0]) >= .3 and y_gap <= .045))


def audit(book, book_root):
    figures = [b for b in book.blocks if b.block_type == 'figure']
    covered = figure_groups(book)
    references = defaultdict(set)
    for block in book.blocks:
        if block.block_type != 'figure':
            for number, label in REFERENCE.findall(block.text):
                references[number.replace('．', '.').replace('-', '.')].add(label.lower())
    pages = defaultdict(list)
    for b in figures:
        pages[b.page_start].append(b)
    candidates = []
    included = set()
    for page, page_figures in pages.items():
        remaining = {b.block_id: b for b in page_figures}
        while remaining:
            seed = remaining.pop(next(iter(remaining)))
            members, queue = [seed], [seed]
            while queue:
                current = queue.pop()
                for bid, other in list(remaining.items()):
                    if current.section_path == other.section_path and neighbors(current, other):
                        remaining.pop(bid)
                        members.append(other)
                        queue.append(other)
            members.sort(key=lambda b: book.blocks.index(b))
            found_numbers = list(dict.fromkeys(n for b in members for n in numbers(b.text)))
            found_labels = sorted(set(l for b in members for l in labels(b.text)))
            uncovered = [b.block_id for b in members if b.block_id not in covered and labels(b.text)]
            expected = sorted(set().union(*(references[n] for n in found_numbers))) if found_numbers else []
            absent = sorted(set(expected) - set(found_labels))
            reasons = []
            if len(members) > 1 and uncovered and len(found_labels) >= 2:
                reasons.append('labeled_layout_cluster_not_fully_grouped')
            if len(found_numbers) == 1 and absent:
                reasons.append('body_references_labels_not_observed_in_cluster')
            if (len(members) == 1 and found_numbers and found_labels
                    and found_labels[0] != 'a' and members[0].block_id not in covered):
                reasons.append('caption_labels_start_after_a')
            if not reasons:
                continue
            complete = bool(found_labels) and found_labels == list('abcdefgh'[:len(found_labels)])
            priority = ('high' if len(found_numbers) == 1 and len(members) > 1
                        and complete and uncovered
                        and 'labeled_layout_cluster_not_fully_grouped' in reasons else 'review')
            row = dict(physical_page=page, figure_numbers=found_numbers, priority=priority,
                       reasons=reasons, observed_labels=found_labels, referenced_labels=expected,
                       unobserved_reference_labels=absent, members=[dict(
                           block_id=b.block_id, caption=b.text, bbox=b.bbox,
                           asset_relpath=b.attributes.get('asset_relpath', ''),
                           current_group=[m.block_id for m in covered.get(b.block_id, [])]) for b in members])
            candidates.append(row)
            included.update(b.block_id for b in members)
    uncovered = [b for b in figures if re.match(r'^\s*[（(][a-h][）)]', b.text, re.I)
                 and b.block_id not in covered]
    unassigned = [dict(block_id=b.block_id, physical_page=b.page_start, caption=b.text,
                       bbox=b.bbox, in_layout_candidate=b.block_id in included) for b in uncovered]
    asset_issues = []
    for b in figures:
        rel = Path(str(b.attributes.get('asset_relpath') or ''))
        if (not str(b.attributes.get('asset_relpath') or '') or rel.is_absolute()
                or '..' in rel.parts or not (book_root / rel).is_file()):
            asset_issues.append(dict(block_id=b.block_id, physical_page=b.page_start,
                                     reason='missing_or_invalid_asset_path'))
    return dict(book_name=book.book_name, canonical_hash=canonical_book_fingerprint(book),
                policy='triage_only_no_correctness_or_recall_claim',
                thresholds=dict(horizontal_gap=.18, vertical_gap=.045,
                                vertical_overlap_ratio=.5, horizontal_overlap_ratio=.3),
                limitations=['No original full-page comparison; absent OCR labels may exist inside pixels.',
                             'Spatial clusters can combine adjacent independent figures.',
                             'Uncovered label blocks can already contain a complete composite image.',
                             'Cross-page figures and unlabeled splits are not exhaustively detected.'],
                summary=dict(figure_blocks=len(figures),
                             existing_groups=len({tuple(m.block_id for m in v) for v in covered.values()}),
                             existing_group_members=len(covered),
                             uncovered_leading_label_blocks=len(uncovered),
                             layout_candidates=len(candidates),
                             priority_counts=dict(Counter(c['priority'] for c in candidates)),
                             asset_path_issues=len(asset_issues)),
                candidates=sorted(candidates, key=lambda c: (c['physical_page'] or 0)),
                uncovered_label_blocks=unassigned, asset_path_issues=asset_issues)


def caption_assignment_audit(book, middle_path):
    """Check the export's parent assignment against original caption coordinates.

    A subcaption below another crop but above its assigned crop is a strong
    structural inconsistency. It is still triage, not a semantic verdict.
    """
    source = json.loads(middle_path.read_text(encoding='utf-8'))
    # middle_json indices include caption blocks; structured_content indices
    # enumerate collapsed parents. Match page + exact source bbox, not indices.
    canonical_ids = defaultdict(list)
    for block in book.blocks:
        if block.block_type == 'figure' and block.bbox:
            canonical_ids[(block.page_start, tuple(block.bbox))].append(block.block_id)
    def identity(page_idx, image):
        matches = canonical_ids.get((page_idx+1, tuple(image.get('bbox') or [])), [])
        return matches[0] if len(matches) == 1 else None
    results = []
    for page in source.get('pages', []):
        page_idx = page.get('page_idx')
        images = [b for b in page.get('blocks', []) if b.get('type') in {'image', 'chart'}]
        for image in images:
            for caption in image.get('content') or []:
                if caption.get('type') != 'image_caption':
                    continue
                text = ''.join(c.get('content', '') for c in caption.get('content') or []
                               if c.get('type') == 'text')
                if not re.match(r'^\s*[（(][a-h][）)]', text, re.I) or len(labels(text)) != 1:
                    continue
                box = caption.get('bbox')
                if not isinstance(box, list) or len(box) != 4:
                    continue
                center = (box[0] + box[2]) / 2
                alternatives = []
                for candidate in images:
                    body = candidate.get('bbox')
                    if not isinstance(body, list) or len(body) != 4:
                        continue
                    gap = box[1] - body[3]
                    if -.005 <= gap <= .06 and body[0]-.015 <= center <= body[2]+.015:
                        alternatives.append((max(0, gap), candidate))
                # Keep only contradictions: assigned parent is not a plausible
                # image immediately above this subcaption, while another is.
                if not alternatives or any(c is image for _, c in alternatives):
                    continue
                nearest_gap, nearest = min(alternatives, key=lambda item: item[0])
                results.append(dict(physical_page=page_idx+1, caption=text, caption_bbox=box,
                                    assigned_block_id=identity(page_idx, image),
                                    assigned_source_index=image.get('index'), assigned_bbox=image.get('bbox'),
                                    proposed_block_id=identity(page_idx, nearest),
                                    proposed_source_index=nearest.get('index'), proposed_bbox=nearest.get('bbox'),
                                    gap_below_proposed_crop=nearest_gap, identity_match='page_and_exact_bbox',
                                    reason='subcaption_geometry_conflicts_with_exported_parent'))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', required=True)
    parser.add_argument('--progress-root', type=Path, required=True)
    parser.add_argument('--vector-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--middle-json', type=Path, help='Optional existing export; no new OCR/model call')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.progress_root.resolve()) or output.is_relative_to(args.vector_root.resolve()):
        parser.error('Audit output must be outside textbook/index data directories')
    book = load_workflow_book(args.book, progress_root=args.progress_root, vector_root=args.vector_root)
    if book is None:
        parser.error('Canonical textbook not found')
    from ingestion.document_ir import canonical_paths
    source, _ = canonical_paths(args.book, progress_root=args.progress_root)
    report = audit(book, source.parent)
    if args.middle_json:
        report['caption_assignment_candidates'] = caption_assignment_audit(book, args.middle_json)
        report['summary']['caption_assignment_candidates'] = len(report['caption_assignment_candidates'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
