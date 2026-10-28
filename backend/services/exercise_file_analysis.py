"""Immutable file sources for the same source-backed candidate admission path."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import uuid

from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint
from ingestion.heading_policy import body_title
from memory.exercise_candidate_projection import source_registry, canonical_json
from memory.exercise_structure import CATALOG, ORIGINAL, SECTION, TOPIC, exercise_units, header_metadata, solution_markers, topic_level
from memory.exercise_structure_examples import StructureExampleStore
from memory.textbook_exercise_importer import ExtractedTextbookExerciseText
from utils.json_io import atomic_write_json

ANSWER_HEADING = re.compile(r'^\s*(?:参考答案|答案与解析|习题解答|答案解析|参考解答)\s*$')


def file_book(extracted, *, name, prefix='q'):
    """Keep raw blocks available; line projections retain parent ID and offsets."""
    original = getattr(extracted, 'canonical_book', None)
    parents = original.blocks if original else [DocumentBlock(prefix + '-raw', 'paragraph', extracted.text, [name], source_kind=extracted.provider)]
    blocks, path = [], [name]
    for parent in parents:
        native = original is not None and parent.source_kind == 'mineru'
        if native:
            path = [name, *[p for p in parent.section_path if p != original.book_name]]
        if parent.block_type in ('formula', 'table', 'figure'):
            block = deepcopy(parent)
            block.block_id = prefix + '-' + parent.block_id
            block.section_path = list(path)
            blocks.append(block)
            continue
        cursor = 0
        for line in parent.text.splitlines(keepends=True):
            start, cursor = cursor, cursor + len(line)
            if not line.strip():
                continue
            text = line.rstrip('\r\n')
            block = deepcopy(parent)
            block.block_id = f'{prefix}-{parent.block_id}-{start}'
            block.text = text
            heading = (not CATALOG.match(text) and not re.match(r'^\s*(?:【?例|例题)', text)
                       and not solution_markers(text) and len(text) < 120
                       and (bool(SECTION.match(text)) or bool(TOPIC.match(text)) or bool(ANSWER_HEADING.match(text))
                            or parent.block_type == 'heading' or parent.attributes.get('mineru_type') == 'paragraph_title')
                       and not (ORIGINAL.match(text) and not SECTION.match(text))
                       and not re.search(r'[=。？?]', text))
            if native:
                heading = parent.block_type == 'heading' and not ORIGINAL.match(text) and not body_title(text)
            if heading:
                # Decimal numbering is one signal; native levels are advisory.
                numbered = re.match(r'^\s*(\d+(?:\.\d+)+)', text)
                raw_level = parent.attributes.get('raw_level')
                level = len(numbered[1].split('.')) if numbered else (topic_level(text, path[1:]) if TOPIC.match(text) else (raw_level if type(raw_level) is int and 1 <= raw_level <= 8 else 1))
                if not native:
                    path = path[:max(1, min(level, 8))] + [text.strip()]
            block.block_type = 'heading' if heading else 'paragraph'
            block.section_path = list(path)
            block.attributes.update(source_parent_id=parent.block_id, source_start=start, source_end=start + len(text))
            blocks.append(block)
    return CanonicalBook(name, name, blocks, 'exercise-file-lines-v1')


def _number(unit, blocks):
    text = blocks[unit['source_block_ids'][0]].text
    header = header_metadata(text)
    if header:
        return 'catalog', header['catalog_number']
    match = ORIGINAL.match(text)
    return ('original', match[1] or match[2]) if match else ('', '')


def pair_answer_units(units, answer_units, book):
    """Unique scoped identities only. Repeated numbers never choose a last match."""
    blocks = {b.block_id: b for b in book.blocks}
    def key(unit):
        return (tuple(p for p in unit.get('section_path', [])[1:] if not ANSWER_HEADING.match(p)), *_number(unit, blocks))
    question_counts = Counter(key(u) for u in units)
    answers = {}
    for answer in answer_units:
        answers.setdefault(key(answer), []).append(answer)
    paired = 0
    for unit in units:
        matches = answers.get(key(unit), [])
        already_solved = any(solution_markers(blocks[bid].text) for bid in unit['source_block_ids'])
        if len(matches) == 1 and question_counts[key(unit)] == 1 and key(unit)[-1] and not already_solved:
            answer = matches[0]
            unit['answer_block_ids'] = answer['source_block_ids']
            unit['source_block_ids'] += answer['source_block_ids']
            unit['answer_header_ids'] = answer.get('header_ids', [])
            paired += 1
        else:
            unit['answer_pairing_uncertain'] = True
    return paired


class ExerciseFileAnalysisStore:
    def __init__(self, progress_root):
        self.root = Path(progress_root) / 'exercise_import_sources'
        self.examples = StructureExampleStore(progress_root)

    def create(self, extracted, *, book_name, answer=None):
        self._preserve_assets(extracted)
        if answer:
            self._preserve_assets(answer)
        book = file_book(extracted, name=book_name)
        answer_at = next((i for i, b in enumerate(book.blocks) if ANSWER_HEADING.match(b.text)), None)
        question_book = deepcopy(book)
        if answer_at is not None:
            question_book.blocks = book.blocks[:answer_at]
        units = exercise_units(question_book, unrestricted=True)
        if not units and book.blocks:
            # Unnumbered source remains available as an explicitly uncertain unit.
            body = [b for b in book.blocks if b.block_type != 'heading']
            if body:
                units = [dict(unit_id=body[0].block_id, kind='example', text='\n\n'.join(b.text for b in body),
                              chapter=book_name, section_path=[book_name], page_start=body[0].page_start,
                              page_end=body[-1].page_end, source_block_ids=[b.block_id for b in body], truncated=False, header_ids=[])]
        paired, all_answer_ids = 0, set()
        if answer_at is not None:
            answer_book = deepcopy(book)
            answer_book.blocks = book.blocks[answer_at + 1:]
            all_answer_ids.update(b.block_id for b in answer_book.blocks)
            paired = pair_answer_units(units, exercise_units(answer_book, unrestricted=True), book)
        if answer:
            answer_book = file_book(answer, name=book_name, prefix='a')
            answer_units = exercise_units(answer_book, unrestricted=True)
            all_answer_ids.update(b.block_id for b in answer_book.blocks)
            book.blocks.extend(answer_book.blocks)
            paired = pair_answer_units(units, answer_units, book)
        version, _ = self.examples.load()
        registry = source_registry(book, units, {b.block_id for b in book.blocks})
        source_id = uuid.uuid4().hex
        payload = dict(book_name=book_name, source_id=source_id, canonical_hash=canonical_book_fingerprint(book),
                       units=units, source_blocks=registry, profile_version=version,
                       provider=extracted.provider, paired_answers=paired,
                       raw_hash=hashlib.sha256(extracted.text.encode()).hexdigest(),
                       unmatched_answer_text='\n\n'.join(b.text for b in book.blocks if b.block_id in all_answer_ids
                           and b.block_id not in {bid for u in units for bid in u.get('answer_block_ids', [])}))
        payload['snapshot_hash'] = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        # Validation of the registry budgets occurs before persistence.
        atomic_write_json(self.root / f'{source_id}.json', payload)
        return self._extracted(payload), source_id, paired

    def _preserve_assets(self, extracted):
        root = getattr(extracted, 'asset_root', None)
        canonical = getattr(extracted, 'canonical_book', None)
        if root is None or canonical is None:
            return
        from ingestion.document_adapters import _controlled_source_path, _inspect_figure_image, _atomic_copy
        for block in canonical.blocks:
            visual = block.attributes.get('original_visual_asset')
            if block.block_type != 'figure' and not isinstance(visual, dict):
                continue
            relative = (visual.get('source_relpath', '') if isinstance(visual, dict)
                        else block.attributes.get('source_asset_relpath', ''))
            path = _controlled_source_path(Path(root), relative)
            if path is None:
                block.attributes['asset_status'] = 'missing'
                continue
            try:
                _, _, suffix = _inspect_figure_image(path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                target = self.root / 'assets' / (digest + suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    _atomic_copy(path, target)
                block.attributes.update(asset_id=digest, asset_hash=digest, asset_format=suffix, asset_status='ready')
            except (OSError, ValueError):
                block.attributes['asset_status'] = 'invalid'

    def asset(self, source_id, asset_id, book_name):
        extracted = self.load(source_id, book_name)
        if not re.fullmatch(r'[a-f0-9]{64}', asset_id):
            raise ValueError('来源图片身份无效')
        block = next((b for b in extracted.source_blocks if b['attributes'].get('asset_id') == asset_id), None)
        formats = {'.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
                   '.gif': 'image/gif', '.bmp': 'image/bmp', '.tiff': 'image/tiff'}
        suffix = block['attributes'].get('asset_format') if block else None
        if suffix not in formats:
            raise ValueError('来源图片格式无效')
        path = self.root / 'assets' / (asset_id + suffix)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != asset_id:
            raise ValueError('来源图片校验失败')
        return path, formats[suffix]

    def load(self, source_id, book_name):
        if not re.fullmatch(r'[a-f0-9]{32}', source_id or ''):
            raise ValueError('文件来源身份无效')
        payload = json.loads((self.root / f'{source_id}.json').read_text())
        checksum = payload.pop('snapshot_hash', '')
        if hashlib.sha256(canonical_json(payload).encode()).hexdigest() != checksum:
            raise ValueError('文件来源快照校验失败，请重新分析')
        if payload['book_name'] != book_name or payload['source_id'] != source_id:
            raise ValueError('文件来源不属于当前题库范围')
        return self._extracted(payload)

    def _extracted(self, payload):
        version, markers = self.examples.load(payload['profile_version'])
        return ExtractedTextbookExerciseText(text='\n\n'.join(u['text'] for u in payload['units']),
            provider='file-source-units', book_name=payload['book_name'], units=payload['units'],
            canonical_hash=payload['canonical_hash'], source_blocks=payload['source_blocks'],
            profile_version=version, solution_markers=markers, unmatched_answer_text=payload.get('unmatched_answer_text', ''))
