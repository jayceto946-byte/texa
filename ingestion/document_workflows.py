"""Read-only learning projections shared by import and textbook workflows."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

from config import VECTOR_DB_PATH
from ingestion.document_ir import (
    CanonicalBook, DocumentBlock, canonical_book_fingerprint,
    canonical_chapter_title, canonical_retrieval_paths, load_canonical_book,
)
from ingestion.index_snapshot import index_read_snapshot
from utils.path_safety import safe_book_name

EXAMPLE_START = re.compile(r'^\s*(?:【|\[|［)?\s*(?:例题\s*[\d.．-]*|例\s*\d+(?:[.．-]\d+)*|示例\s*\d*)\s*(?:】|\]|］)?')
_PROBLEM_START = re.compile(r'^\s*\d+\s*[.．、)]')
_SUBQUESTION_START = re.compile(r'^\s*[（(]\s*\d+\s*[）)]')
_SOLUTION_START = re.compile(r'^\s*(?:解|解答|答案|分析|证明)\s*[：:]')


def example_label(text: str) -> str:
    match = EXAMPLE_START.match(str(text or ''))
    return match.group().strip() if match else ''


def load_workflow_book(book_name: str, *, progress_root: Path,
                       vector_root: Path = VECTOR_DB_PATH) -> CanonicalBook | None:
    """Read a committed IR, checking the active manifest without opening IO stores."""
    with index_read_snapshot():
        try:
            book = load_canonical_book(book_name, progress_root=progress_root)
        except FileNotFoundError:
            return None
        manifest_path = Path(vector_root) / '_index_manifests' / f'{safe_book_name(book_name)}.json'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            expected = manifest.get('canonical_hash')
            if expected and canonical_book_fingerprint(book) != expected:
                raise ValueError('教材 Canonical 与活跃索引版本不一致，请检查教材版本')
        return book


def canonical_outline(book: CanonicalBook) -> list[dict]:
    paths = canonical_retrieval_paths(book.blocks)
    chapters: dict[str, dict] = {}
    for index, block in enumerate(book.blocks):
        path = paths.get(block.block_id) or [book.book_name]
        chapter = chapters.setdefault(path[0], dict(title=path[0], page_number=block.page_start or 1,
                                                   end_page=block.page_end, subsections=[], page_kind='physical'))
        chapter['end_page'] = max(chapter.get('end_page') or 0, block.page_end or block.page_start or 0)
        if block.block_type != 'heading' or canonical_chapter_title(block.text):
            continue
        end = next((n for n in range(index + 1, len(book.blocks))
                    if book.blocks[n].block_type == 'heading'
                    and len(paths.get(book.blocks[n].block_id, [])) <= len(path)), len(book.blocks))
        members = book.blocks[index:end]
        parent = next((candidate['heading_block_id'] for candidate in reversed(chapter['subsections'])
                       if candidate['level'] == len(path) - 1 and candidate['section_path'] == path[:-1]), '')
        chapter['subsections'].append(dict(
            title=block.text, page=block.page_start, page_number=block.page_start,
            end_page=max((member.page_end or member.page_start or 0 for member in members), default=block.page_start),
            heading_block_id=block.block_id, parent_heading_block_id=parent, level=len(path),
            section_path=path, source_block_ids=[member.block_id for member in members],
            printed_page=block.attributes.get('printed_page_number'), page_kind='physical',
        ))
    return list(chapters.values())


def enrich_chapters(chapters: list[dict], book: CanonicalBook | None) -> list[dict]:
    if book is None:
        return chapters
    outline = canonical_outline(book)
    by_title = {canonical_chapter_title(item['title']) or item['title']: item for item in outline}
    if not chapters:
        return outline
    result = []
    for chapter in chapters:
        projection = by_title.get(canonical_chapter_title(chapter.get('title', '')) or chapter.get('title'))
        # Existing persisted scope identities are authoritative for old assets.
        result.append({**chapter, 'subsections': projection['subsections'], 'page_kind': 'physical'}
                      if projection and not chapter.get('subsections') else dict(chapter))
    return result


@dataclass
class LearningUnit:
    kind: str
    label: str
    blocks: list[DocumentBlock]
    section_path: list[str]
    truncated: bool = False

    @property
    def unit_id(self) -> str:
        return self.blocks[0].block_id

    @property
    def text(self) -> str:
        return '\n\n'.join(block.text for block in self.blocks if block.text.strip())


def learning_units(book: CanonicalBook) -> list[LearningUnit]:
    """Retain ordered stem/solution/formula/table/figure blocks within explicit scopes."""
    paths = canonical_retrieval_paths(book.blocks)
    result: list[LearningUnit] = []
    active: LearningUnit | None = None
    for block in book.blocks:
        path = paths.get(block.block_id) or [book.book_name]
        label = example_label(block.text)
        exercise_scope = any(part.strip() in {'习题', '练习', '复习题', '思考题'} for part in path)
        problem = _PROBLEM_START.match(block.text) if exercise_scope else None
        start_kind = 'example' if label else ('exercise' if problem else '')
        if start_kind:
            active = LearningUnit(start_kind, label or problem.group().strip(), [block], path)
            result.append(active)
            continue
        if active is None:
            continue
        title_boundary = (block.attributes.get('mineru_type') == 'paragraph_title'
                          and not _SOLUTION_START.match(block.text)
                          and not _SUBQUESTION_START.match(block.text))
        if block.block_type == 'heading' or path != active.section_path or title_boundary:
            active = None
            continue
        if len(active.blocks) >= 80 or (block.page_start or 0) - (active.blocks[0].page_start or 0) > 8:
            active.truncated = True
            active = None
            continue
        active.blocks.append(block)
    return result


def annotate_learning_units(book: CanonicalBook) -> None:
    """Annotate a newly parsed candidate; never apply to the persisted active IR."""
    for unit in learning_units(book):
        for block in unit.blocks:
            block.attributes.update(learning_unit_id=unit.unit_id, **{f'{unit.kind}_id': unit.unit_id})
            if block.block_type == 'paragraph':
                block.block_type = unit.kind
                block.attributes['semantic_role'] = unit.kind
            if unit.truncated:
                block.review_status = ','.join(filter(None, [block.review_status, 'learning_unit_truncated']))


def figure_groups(book: CanonicalBook) -> dict[str, list[DocumentBlock]]:
    """Group only contiguous, same-page a/b/... crops with one shared figure number."""
    groups: dict[str, list[DocumentBlock]] = {}
    run: list[DocumentBlock] = []
    def flush():
        if len(run) < 2 or len(run) > 8:
            return
        labels = [re.match(r'^\s*[（(]([a-h])[）)]', member.text, re.I) for member in run]
        captions = [member for member in run if re.search(r'图\s*\d+(?:[.．-]\d+)+', member.text)]
        if (len(captions) == 1 and all(labels)
                and [match.group(1).lower() for match in labels] == list('abcdefgh'[:len(run)])):
            for member in run:
                groups[member.block_id] = list(run)
    for block in book.blocks:
        if (block.block_type == 'figure' and block.bbox and len(block.bbox) == 4
                and all(0 <= value <= 1 for value in block.bbox)
                and block.bbox[0] < block.bbox[2] and block.bbox[1] < block.bbox[3]
                and re.match(r'^\s*[（(][a-h][）)]', block.text, re.I)):
            if run and (run[-1].page_start != block.page_start or run[-1].section_path != block.section_path):
                flush()
                run = []
            run.append(block)
        else:
            flush()
            run = []
    flush()
    return groups


def content_review_signals(block: DocumentBlock) -> list[str]:
    """Review hints, never a semantic correctness verdict or an automatic deletion."""
    text = block.text
    signals = []
    sentences = [part.strip() for part in re.split(r'[；;。\n]', text) if len(part.strip()) >= 12]
    normalized = [re.sub(r'^\d+[.、]\s*', '', part) for part in sentences]
    if len(normalized) >= 6 and len(set(normalized)) <= len(normalized) / 3:
        signals.append('repeated_ocr_text')
    if re.search(r'无法(?:识别|辨认).{0,30}(?:图中|文本|文字)|由于图中未提供具体的数据', text):
        signals.append('ocr_refusal_text')
    return signals
