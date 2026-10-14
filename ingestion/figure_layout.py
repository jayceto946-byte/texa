"""Source-neutral, read-only caption geometry and whole-figure projections.

Raw crops and Canonical records remain immutable. A projection only restores
their relationships; it makes no claim about OCR or missing source pixels.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint

LAYOUT_SCHEMA = 'texa.figure-layout/v1'
LAYOUT_VERSION = 'caption-geometry-v1'
LAYOUT_FILENAME = 'figure_layout.json'
MAX_LAYOUT_BYTES = 4 * 1024 * 1024
NUMBER = re.compile(r'^\s*图\s*(\d+(?:[.．-]\d+)+)')
SUBCAPTION = re.compile(r'^\s*[（(]([a-h])[）)]', re.I)


def is_caption_anchor(text: str) -> bool:
    """A leading figure reference in prose is not a trustworthy caption."""
    return bool(NUMBER.match(text) and len(text) <= 120
                and not re.search(r'所示|如图|可见|可以', text))


def normalized_box(box):
    return (isinstance(box, (list, tuple)) and len(box) == 4
            and all(type(v) in (int, float) and 0 <= v <= 1 for v in box)
            and box[0] < box[2] and box[1] < box[3])


def caption_nodes(book: CanonicalBook) -> list[dict]:
    nodes = []
    for block in book.blocks:
        if block.block_type == 'figure':
            for caption in block.attributes.get('visual_captions') or []:
                if isinstance(caption, dict) and normalized_box(caption.get('bbox')):
                    nodes.append(dict(source_block_id=block.block_id, page=block.page_start,
                                      text=str(caption.get('text') or ''), bbox=list(caption['bbox'])))
        elif normalized_box(block.bbox) and is_caption_anchor(block.text):
            # A short standalone caption can be exported as a paragraph.
            nodes.append(dict(source_block_id=block.block_id, page=block.page_start,
                              text=block.text, bbox=list(block.bbox)))
    return nodes


def load_caption_projection(book: CanonicalBook, path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > MAX_LAYOUT_BYTES:
        raise ValueError('教材图片关联文件不安全或过大')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('schema') != LAYOUT_SCHEMA or data.get('book_name') != book.book_name
            or data.get('canonical_hash') != canonical_book_fingerprint(book)):
        raise ValueError('教材图片关联与当前 Canonical 版本不一致，请重新生成关联')
    blocks = {b.block_id: b for b in book.blocks}
    nodes = data.get('caption_nodes')
    if not isinstance(nodes, list) or len(nodes) > 20000:
        raise ValueError('教材图片关联缺少合法图题节点')
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError('教材图题节点损坏')
        block = blocks.get(node.get('source_block_id'))
        if (block is None or node.get('page') != block.page_start
                or not normalized_box(node.get('bbox')) or not isinstance(node.get('text'), str)
                or len(node['text']) > 2000):
            raise ValueError('教材图题来源或坐标不合法')
    return nodes


@dataclass
class FigureLayout:
    groups: dict[str, list[DocumentBlock]] = field(default_factory=dict)
    details: dict[str, dict] = field(default_factory=dict)
    caption_nodes: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


def _barrier(book_blocks, figure, caption):
    """Do not reach past intervening prose/heading into another diagram."""
    a, c = figure.bbox, caption['bbox']
    for block in book_blocks:
        if (block.page_start != figure.page_start or block.block_type not in {'paragraph', 'heading'}
                or not normalized_box(block.bbox)
                or is_caption_anchor(block.text)):
            continue
        b = block.bbox
        overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
        if (b[0] <= a[2] and b[2] >= a[0] and b[1] >= a[3]-.005
                and b[3] <= c[1]+.005 and b[3]-b[1] >= .02
                and overlap / (a[2]-a[0]) >= .25):
            return True
    return False


def project_figure_layout(book: CanonicalBook, nodes: list[dict] | None = None) -> FigureLayout:
    from ingestion.document_workflows import figure_groups
    result = FigureLayout(groups=figure_groups(book))
    source_nodes = caption_nodes(book) if nodes is None else nodes
    unique = {}
    for node in source_nodes:
        if normalized_box(node.get('bbox')) and node.get('text'):
            unique[(node['page'], tuple(node['bbox']), node['text'])] = dict(node)
    result.caption_nodes = list(unique.values())
    by_page = defaultdict(list)
    for node in result.caption_nodes:
        match = NUMBER.match(node['text'])
        if match and is_caption_anchor(node['text']):
            node['number'] = match.group(1).replace('．', '.').replace('-', '.')
            by_page[node['page']].append(node)
    assigned = defaultdict(list)
    page_blocks = defaultdict(list)
    for block in book.blocks:
        page_blocks[block.page_start].append(block)
    figures = [b for b in book.blocks if b.block_type == 'figure']
    for figure in figures:
        if (not normalized_box(figure.bbox) or type(figure.page_start) is not int or figure.page_start < 1
                or figure.attributes.get('bbox_space') != 'page'
                or figure.attributes.get('bbox_units') != 'normalized'):
            continue
        a = figure.bbox
        center = (a[0]+a[2])/2
        choices = {}
        for caption in by_page[figure.page_start]:
            c = caption['bbox']
            gap = c[1]-a[3]
            horizontal = max(0, c[0]-center, center-c[2])
            if not -.025 <= gap <= .45 or horizontal > .35 or _barrier(page_blocks[figure.page_start], figure, caption):
                continue
            score = 2*max(0, gap) + .6*horizontal
            number = caption['number']
            if number not in choices or score < choices[number][0]:
                choices[number] = (score, caption)
        ranked = sorted(choices.values(), key=lambda item: item[0])
        if not ranked:
            continue
        if len(ranked) > 1 and ranked[1][0]-ranked[0][0] < .012:
            result.issues.append(dict(block_id=figure.block_id, page=figure.page_start,
                                      reason='ambiguous_figure_caption'))
            result.details[figure.block_id] = dict(status='ambiguous', member_ids=[figure.block_id])
            continue
        anchor = ranked[0][1]
        # Physical page and exact section are hard boundaries, not soft priors.
        key = figure.page_start, tuple(figure.section_path), anchor['number']
        assigned[key].append((figure, anchor))
    for (page, _scope, number), items in assigned.items():
        members = [b for b, _ in items]
        bounds = [min(b.bbox[0] for b in members), min(b.bbox[1] for b in members),
                  max(b.bbox[2] for b in members), max(b.bbox[3] for b in members)]
        if len(members) > 16 or (len(members) > 1 and bounds[3]-bounds[1] > .55):
            for member in members:
                result.issues.append(dict(block_id=member.block_id, page=page, reason='unbounded_figure_layout'))
                result.details[member.block_id] = dict(status='ambiguous', member_ids=[member.block_id])
            continue
        anchor = min((c for _, c in items), key=lambda c: c['bbox'][1])
        selected_nodes = [anchor]
        for node in result.caption_nodes:
            if node['page'] != page or NUMBER.match(node['text']):
                continue
            c = node['bbox']
            center = (c[0]+c[2])/2
            # Labels can sit between two crops in one logical subfigure. Keep
            # their page coordinates rather than inventing per-crop a/b labels.
            if (SUBCAPTION.match(node['text']) and bounds[0]-.03 <= center <= bounds[2]+.03 and bounds[1] <= c[1] <= anchor['bbox'][1]+.012
                    and any(-.025 <= c[1]-b.bbox[3] <= .08 for b in members)):
                selected_nodes.append(node)
            elif (not SUBCAPTION.match(node['text']) and len(node['text']) <= 100
                  and node['source_block_id'] in {b.block_id for b in members}
                  and bounds[0]-.1 <= center <= bounds[2]+.1
                  and bounds[1]-.03 <= c[1] <= anchor['bbox'][1]+.012):
                # Source annotations can lie outside the crop (e.g. a mask
                # name). Preserve known text; never infer missing pixels.
                selected_nodes.append(node)
        selected_nodes = list({(n['page'], tuple(n['bbox']), n['text']): n for n in selected_nodes}.values())
        # Reading order is based on rows, not arbitrary OCR block order or
        # rounding boundaries that can swap near-aligned a/b captions.
        child_nodes = sorted([n for n in selected_nodes if n is not anchor], key=lambda n: (n['bbox'][1], n['bbox'][0]))
        ordered, row = [], []
        for node in child_nodes:
            if row and node['bbox'][1]-row[0]['bbox'][1] > .018:
                ordered.extend(sorted(row, key=lambda n: n['bbox'][0]))
                row = []
            row.append(node)
        ordered.extend(sorted(row, key=lambda n: n['bbox'][0]))
        child_nodes = ordered
        member_captions = {b.block_id: [] for b in members}
        for node in child_nodes:
            if not SUBCAPTION.match(node['text']):
                continue
            c = node['bbox']
            center = (c[0]+c[2])/2
            nearby = sorted([(max(0, c[1]-b.bbox[3]), b) for b in members
                             if -.025 <= c[1]-b.bbox[3] <= .08
                             and b.bbox[0] <= center <= b.bbox[2]], key=lambda item: item[0])
            if nearby and (len(nearby) == 1 or nearby[1][0]-nearby[0][0] > .012):
                member_captions[nearby[0][1].block_id].append(node['text'])
        detail = dict(status='assembled' if len(members) > 1 else 'single', figure_number=number,
                      caption='\n'.join([anchor['text'], *[n['text'] for n in child_nodes]]),
                      member_ids=[b.block_id for b in members], bounds=bounds,
                      caption_sources=selected_nodes, version=LAYOUT_VERSION,
                      member_captions={bid: '\n'.join(texts) for bid, texts in member_captions.items()})
        for member in members:
            result.details[member.block_id] = detail
            if len(members) > 1:
                result.groups[member.block_id] = members
            else:
                result.groups.pop(member.block_id, None)
    # A failed geometry resolution must not inherit a legacy group silently.
    for issue in result.issues:
        removed = result.groups.pop(issue['block_id'], [])
        for member in removed:
            result.groups.pop(member.block_id, None)
    # Remove overlapping fallback groups when a caption projection reassigned
    # only some of their members to distinct numbered diagrams.
    for bid, group in list(result.groups.items()):
        if any(tuple(m.block_id for m in result.groups.get(b.block_id, []))
               != tuple(m.block_id for m in group) for b in group):
            result.groups.pop(bid, None)
    return result
