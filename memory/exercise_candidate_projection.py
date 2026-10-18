"""Read-only, bounded projections of Canonical learning units into exercises.

Source spans refer to raw Unicode code points, before display serialization.
No OCR, model, storage or global LearningUnit mutations belong here.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import html
import json
import re

ROLES = ('question', 'answer', 'explanation', 'context', 'unassigned')
SOLUTION = re.compile(r'^\s*(解答|答案|证明|解|证)\s*[：:]')
INLINE_SOLUTION = re.compile(r'(?:[。；;\n]|\s)(?:解答|答案|证明|解|证)\s*[：:]')
PRIOR_CONTEXT = re.compile(r'前例|上例|例\s*\d+(?:[.．]\d+)+\s*中|上述(?:参数|条件)')
FIGURE = re.compile(r'图\s*([A-Za-z]|\d+(?:\s*[.．\-]\s*\d+)+)')
SNAPSHOT_KEYS = ('block_id', 'block_type', 'text', 'section_path', 'page_start', 'page_end', 'bbox',
                 'equations', 'table_title', 'table_header', 'table_rows', 'source_kind', 'review_status')
ATTRIBUTE_KEYS = ('source_page_idx', 'source_block_index', 'bbox_space', 'bbox_format', 'bbox_units',
                  'mineru_type', 'semantic_role', 'asset_id', 'asset_hash', 'asset_status')


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value, *, include_projection=True):
    keys = ('question_text', 'answer', 'explanation') + (('projection',) if include_projection else ())
    return hashlib.sha256(canonical_json({key: value.get(key, '' if key != 'projection' else None) for key in keys}).encode('utf-8')).hexdigest()


def snapshot(block, order):
    raw = block.to_dict()
    return {**{key: deepcopy(raw[key]) for key in SNAPSHOT_KEYS}, 'order': order,
            'attributes': {key: deepcopy(raw['attributes'][key]) for key in ATTRIBUTE_KEYS if key in raw['attributes']}}


def marker(block):
    match = SOLUTION.match(block['text'])
    role = block.get('attributes', {}).get('semantic_role')
    if match:
        return 'answer' if match[1] == '答案' else 'explanation'
    return {'answer': 'answer', 'solution': 'explanation', 'proof': 'explanation'}.get(role, '')


def figure_labels(text):
    return list(dict.fromkeys('图' + re.sub(r'\s+', '', m).replace('．', '.').replace('-', '.') for m in FIGURE.findall(text)))


def source_registry(canonical, units, allowed_ids):
    """Only unit members, bounded proof adjacency and explicitly referenced figures."""
    selected = {bid for unit in units for bid in unit['source_block_ids']}
    by_id = {b.block_id: i for i, b in enumerate(canonical.blocks)}
    for unit in units:
        if not unit['source_block_ids']:
            continue
        last = by_id[unit['source_block_ids'][-1]]
        following = canonical.blocks[last + 1:last + 81]
        if following and following[0].block_id in allowed_ids and marker(snapshot(following[0], last + 1)):
            path = canonical.blocks[last].section_path
            for block in following:
                if (block.block_id not in allowed_ids or block.section_path != path or block.block_type == 'heading'
                        or (block.page_start or 0) - (unit['page_start'] or 0) > 8
                        or re.match(r'^\s*(?:【?例\s*\d|\d+[.、])', block.text)):
                    break
                selected.add(block.block_id)
    labels = set(figure_labels('\n'.join(u['text'] for u in units)))
    for block in canonical.blocks:
        if block.block_id in allowed_ids and block.block_type == 'figure' and labels.intersection(figure_labels(block.text)):
            selected.add(block.block_id)
    result = [snapshot(b, i) for i, b in enumerate(canonical.blocks) if b.block_id in selected]
    if len(result) > 12000 or len(canonical_json(result).encode('utf-8')) > 8_000_000:
        raise ValueError('来源注册表超出安全预算，请缩小教材范围后重试')
    return result


def issue(code, blocks=(), dependency_id=None, category='content'):
    return dict(key=code + ':' + (dependency_id or ','.join(blocks)), category=category, code=code,
                block_ids=list(blocks), dependency_id=dependency_id)


def serialize_block(block):
    text = block['text']
    # The existing reader already recognizes simple roman-variable equations.
    # Preserve those working bytes (and exact duplicate identities); complex/tagged
    # formulas need explicit display delimiters to avoid inline KaTeX failures.
    already_readable = (r'\mathrm' in text and not re.search(r'\\(?:tag|frac|begin|sum|int|sqrt)\b|\$', text))
    if block['block_type'] == 'formula' and text.strip() and not already_readable and not text.strip().startswith(('$$', r'\[')):
        return '$$\n' + text + '\n$$'
    if block['block_type'] == 'table' and not text.strip() and block.get('table_rows'):
        header = block.get('table_header') or [''] * max(map(len, block['table_rows']))
        rows = [header, ['---'] * len(header), *block['table_rows']]
        return '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows)
    return text


def serialize_parts(spans, registry):
    parts = []
    for span in spans:
        block = registry[span['block_id']]
        text = block['text'][span['start']:span['end']]
        if span['start'] == 0 and span['end'] is None:
            text = serialize_block(block)
        if text.strip():
            parts.append(text)
    return '\n\n'.join(parts)


def project_units(units, source_blocks, canonical_hash, scope):
    """Return proposals keyed by original units; never rewrite the supplied units."""
    registry = {b['block_id']: b for b in source_blocks}
    groups = []
    for unit in units:
        first = registry[unit['source_block_ids'][0]]
        if (first['block_type'] == 'formula' and groups
                and registry[groups[-1][-1]['source_block_ids'][-1]]['order'] + 1 == first['order']
                and registry[groups[-1][0]['source_block_ids'][0]]['section_path'] == first['section_path']):
            groups[-1].append(unit)
        else:
            groups.append([unit])
    proposals = []
    used = {bid for u in units for bid in u['source_block_ids']}
    for group in groups:
        unit = group[0]
        ids = [bid for u in group for bid in u['source_block_ids']]
        blocks = [registry[bid] for bid in ids]
        last = blocks[-1]
        extra = [b for b in source_blocks if b['order'] > last['order'] and b['block_id'] not in used]
        if extra and extra[0]['order'] == last['order'] + 1 and marker(extra[0]):
            expected = last['order'] + 1
            for b in extra:
                if b['order'] != expected or b['section_path'] != last['section_path'] or b['block_type'] == 'heading':
                    break
                blocks.append(b)
                expected += 1
        problems = []
        def warn(code, bids=(), dep=None):
            entry = issue(code, bids, dep)
            if entry not in problems:
                problems.append(entry)
        if len(blocks) > 80 or (blocks[-1]['page_end'] or blocks[-1]['page_start'] or 0) - (blocks[0]['page_start'] or 0) > 8 or any(u['truncated'] for u in group):
            warn('boundary_uncertain', ids)
        if blocks[0]['block_type'] == 'formula':
            warn('boundary_uncertain', [blocks[0]['block_id']])
        same_block = any(INLINE_SOLUTION.search(b['text']) and not marker(b) for b in blocks)
        boundary = next((i for i, b in enumerate(blocks) if i > 0 and marker(b)), None)
        if same_block or (unit['kind'] == 'example' and boundary is None):
            warn('solution_in_stem', [b['block_id'] for b in blocks if INLINE_SOLUTION.search(b['text'])] or ids[:1])
        # A numbered short title is ambiguous with a legitimate numbered subquestion.
        # Keep it as evidence and request a specific boundary decision.
        for b in blocks[1:]:
            text = b['text'].strip()
            if (b['block_type'] == 'heading' or (re.match(r'^[（(]\d+[）)]\s*[^\d\W]', text)
                and len(text) < 35 and not re.search(r'[。？?=，,；;]|求|证明|计算|说明|分析|比较|再|试|设|是否|确定|多少', text))):
                warn('boundary_uncertain', [b['block_id']])
            if b.get('review_status') and any(s in b['review_status'] for s in ('truncated', 'formula', 'fragment')):
                warn('formula_review' if b['block_type'] == 'formula' else 'boundary_uncertain', [b['block_id']])
        parts = {role: [] for role in ROLES}
        unresolved = any(p['code'] in ('solution_in_stem', 'boundary_uncertain') for p in problems)
        method = 'unresolved' if unresolved else ('block_boundary' if boundary else 'whole_unit')
        role = 'question'
        for i, b in enumerate(blocks):
            if marker(b) and i > 0:
                role = marker(b)
            assigned = 'unassigned' if unresolved else role
            parts[assigned].append(dict(block_id=b['block_id'], start=0, end=None))
        body = {r: serialize_parts(parts[r], registry) for r in ('question', 'answer', 'explanation')}
        if unresolved:
            body['question'] = serialize_parts(parts['unassigned'], registry)
        # Preserve already working whole-unit text byte for byte (including dedup fingerprints).
        if method == 'whole_unit' and len(group) == 1 and all(serialize_block(b) == b['text'] for b in blocks):
            body['question'] = unit['text']
        if boundary and any(b['block_type'] == 'table' for b in blocks[:boundary]):
            warn('formula_review', [b['block_id'] for b in blocks if b['block_type'] == 'table'])
        dependencies = []
        question_source = '\n'.join(b['text'] for b in (blocks[:boundary] if boundary else blocks) if b['block_type'] != 'figure')
        required_labels = set(figure_labels(question_source))
        all_labels = set(figure_labels('\n'.join(b['text'] for b in blocks)))
        for label in sorted(all_labels):
            targets = [b for b in source_blocks if b['block_type'] == 'figure' and label in figure_labels(b['text'])]
            dep_id = 'figure:' + label
            requirement = 'required' if label in required_labels else 'reference'
            dependencies.append(dict(id=dep_id, kind='figure', label=label, requirement=requirement,
                                     block_ids=[b['block_id'] for b in targets],
                                     asset_ids=[b['attributes']['asset_id'] for b in targets if b['attributes'].get('asset_id')],
                                     resolution='identified' if targets else 'unresolved'))
            for b in targets:
                if b['block_id'] not in {s['block_id'] for spans in parts.values() for s in spans}:
                    parts['context'].append(dict(block_id=b['block_id'], start=0, end=None))
            if requirement == 'required':
                warn('missing_required_input', [b['block_id'] for b in targets], dep_id)
            if len(targets) > 1:
                warn('dependency_uncertain', [b['block_id'] for b in targets], dep_id)
        for b in blocks:
            if b['block_type'] == 'figure' and not set(figure_labels(b['text'])).intersection(set(figure_labels(question_source))):
                warn('boundary_uncertain', [b['block_id']])
            if b['block_type'] in ('formula', 'table'):
                kind = b['block_type']
                dependencies.append(dict(id=kind + ':' + b['block_id'], kind=kind, label=kind,
                                         requirement='required' if b['block_id'] in {s['block_id'] for s in parts['question']} else 'reference',
                                         block_ids=[b['block_id']], asset_ids=[], resolution='embedded'))
                if kind == 'formula' and (b['text'].count('{') != b['text'].count('}') or not b['text'].strip()):
                    warn('formula_review', [b['block_id']])
                if kind == 'table' and b['text'].strip() and b.get('table_rows'):
                    visible = re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', b['text'])))
                    cells = [*b.get('table_header', []), *(cell for row in b['table_rows'] for cell in row)]
                    if any(re.sub(r'\s+', '', cell) not in visible for cell in cells if cell.strip()):
                        warn('boundary_uncertain', [b['block_id']])
                if kind == 'table' and b.get('table_rows') and len({len(row) for row in [b.get('table_header') or b['table_rows'][0], *b['table_rows']]}) > 1:
                    warn('boundary_uncertain', [b['block_id']])
        if PRIOR_CONTEXT.search(question_source):
            dep_id = 'prior_context'
            dependencies.append(dict(id=dep_id, kind='prior_context', label='前例条件', requirement='required', block_ids=[], asset_ids=[], resolution='unresolved'))
            warn('missing_required_input', [], dep_id)
        if len(body['question']) < 12:
            warn('boundary_uncertain', ids[:1])
        if len(re.findall(r'(?m)^\s*\d+\s*[.、．)]\s*', body['question'])) > len(group):
            warn('boundary_uncertain', ids)
        if '选择题' in body['question'] and len(re.findall(r'(?:^|\s|[（(])[A-D]\s*[.、．)]', body['question'], re.I)) < 3:
            warn('boundary_uncertain', ids)
        projection = dict(version=1, canonical_hash=canonical_hash, unit_ids=[u['unit_id'] for u in group],
                          scope=deepcopy(scope), method=method, parts=parts, dependencies=dependencies)
        proposals.append(dict(unit=unit, question_text=body['question'], answer=body['answer'], explanation=body['explanation'], projection=projection, issues=problems))
    return proposals
