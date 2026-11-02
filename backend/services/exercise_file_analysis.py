"""Immutable file sources for the same source-backed candidate admission path."""
from __future__ import annotations

from collections import Counter,defaultdict
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

ANSWER_HEADING = re.compile(r'^\s*(?:答案|参考答案|答案与解析|习题解答|答案解析|参考解答|answers?|solutions?)\s*$',re.I)


def select_physical_pages(extracted, *, page_start=None, page_end=None):
    if page_start is None and page_end is None:
        return extracted
    if not extracted.canonical_book or not extracted.canonical_book.source_page_count:
        raise ValueError('该文件没有物理页信息；请选择 PDF 或保留页码的 MinerU 包')
    from dataclasses import replace
    book = deepcopy(extracted.canonical_book)
    start, end = page_start or 1, page_end or book.source_page_count
    if start > end or end > book.source_page_count:
        raise ValueError('物理页范围无效或超出文件页数')
    book.blocks = [b for b in book.blocks if b.page_start and start <= b.page_start <= end]
    book.source_metadata['selected_physical_pages'] = dict(start=start, end=end)
    return replace(extracted, canonical_book=book, text='\n\n'.join(b.text for b in book.blocks))


def file_book(extracted, *, name, prefix='q'):
    """Keep raw blocks available; line projections retain parent ID and offsets."""
    original = getattr(extracted, 'canonical_book', None)
    parents = original.blocks if original else [DocumentBlock(prefix + '-raw', 'paragraph', extracted.text, [name], source_kind=extracted.provider)]
    blocks, path = [], [name]
    identities = {}
    by_parent=defaultdict(list)
    for parent in parents:
        native = original is not None and (parent.source_kind == 'mineru' or bool(original.source_metadata.get('review_book_name')))
        if native:
            path = [name, *[p for p in parent.section_path if p != original.book_name]]
        if parent.block_type in ('formula', 'table', 'figure'):
            block = deepcopy(parent)
            block.block_id = prefix + '-' + parent.block_id
            identities[parent.block_id] = block.block_id
            block.section_path = list(path)
            blocks.append(block)
            by_parent[parent.block_id].append(block)
            continue
        cursor = 0
        for line in parent.text.splitlines(keepends=True):
            start, cursor = cursor, cursor + len(line)
            if not line.strip():
                continue
            text = line.rstrip('\r\n')
            block = deepcopy(parent)
            block.block_id = f'{prefix}-{parent.block_id}-{start}'
            identities.setdefault(parent.block_id, block.block_id)
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
            block.block_type = 'heading' if heading else ('example' if parent.block_type=='example' and start==0 else 'paragraph')
            block.section_path = list(path)
            block.attributes.update(source_parent_id=parent.block_id, source_start=start, source_end=start + len(text))
            if start and parent.attributes.get('structure_unit_start'):
                # A reviewed paragraph starts one question, not one per line.
                block.attributes['structure_unit_start'] = False
                block.attributes.setdefault('structure_unit_id', parent.block_id)
                block.attributes.pop('structure_question_number', None)
            blocks.append(block)
            by_parent[parent.block_id].append(block)
    parents_by_id={b.block_id:b for b in parents}
    for block in blocks:
        for key in ('outline_parent_id', 'outline_root_id', 'structure_unit_id'):
            if block.attributes.get(key) in identities:
                block.attributes[key] = identities[block.attributes[key]]
        if block.attributes.get('structure_group_members'):
            block.attributes['structure_group_members'] = [identities[bid] for bid in block.attributes['structure_group_members']]
        metadata=block.attributes.get('exercise_metadata')
        if metadata:
            evidence=[]
            for e in metadata.get('evidence',[]):
                lines=by_parent.get(e['block_id'],[])
                matches=[b for b in lines if e['quote'] in b.text]
                if len(matches)==1:
                    evidence.append(dict(block_id=matches[0].block_id,quote=e['quote']));continue
                parent=parents_by_id.get(e['block_id'])
                start=parent.text.find(e['quote']) if parent else -1
                if start>=0:
                    end=start+len(e['quote'])
                    for line in lines:
                        offset=line.attributes.get('source_start',0)
                        quote=line.text[max(0,start-offset):min(len(line.text),end-offset)] if end>offset and start<offset+len(line.text) else ''
                        if quote.strip():evidence.append(dict(block_id=line.block_id,quote=quote))
                else:evidence.append(dict(block_id=identities.get(e['block_id'],e['block_id']),quote=e['quote']))
            metadata['evidence']=evidence
    return CanonicalBook(name, name, blocks, 'exercise-file-lines-v2',
                         source_metadata=deepcopy(original.source_metadata) if original else {},
                         source_page_count=original.source_page_count if original else None)


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
    from ingestion.heading_policy import exercise_heading
    def key(unit):
        return (tuple(p for p in unit.get('section_path', [])[1:] if not exercise_heading(p)), *_number(unit, blocks))
    question_counts = Counter(key(u) for u in units)
    answers = {}
    for answer in answer_units:
        answers.setdefault(key(answer), []).append(answer)
    paired = 0
    for unit in units:
        matches = answers.get(key(unit), [])
        already_solved = any(solution_markers(blocks[bid].text) or blocks[bid].attributes.get('structure_unit_role') in {'answer','explanation'} for bid in unit['source_block_ids'])
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

    def textbook_review_source(self, extracted):
        """Freeze the selected raw textbook scope for optional AI work, never its index."""
        if extracted.review_book is None:
            return None
        from ingestion.document_ir import canonical_paths
        from memory.exercise_file_importer import ExtractedExerciseText
        assets = canonical_paths(extracted.book_name, progress_root=self.root.parent)[0].parent
        raw = ExtractedExerciseText(text='\n\n'.join(b.text for b in extracted.review_book.blocks),
            file_type='textbook', provider='textbook-source', canonical_book=extracted.review_book, asset_root=assets)
        _, source_id, _ = self.create(raw, book_name=extracted.book_name)
        return source_id

    def attach_review_pdf(self, source_id, book_name, pdf):
        from backend.services.structure_review_jobs import resolve_source, review_directory
        from ingestion.document_adapters import _atomic_copy
        target = dict(kind='file',reference=source_id,book_name=book_name)
        book, _, _ = resolve_source(target, progress_root=self.root.parent, books_root=self.root, jobs=None)
        directory = review_directory(self.root.parent, 'file', source_id)
        directory.mkdir(parents=True,exist_ok=True)
        _atomic_copy(pdf,directory/'source.pdf')
        atomic_write_json(directory/'source_pdf.json',dict(source_version=canonical_book_fingerprint(book)))

    def create(self, extracted, *, book_name, answer=None):
        self._preserve_assets(extracted)
        if answer:
            self._preserve_assets(answer)
        book = file_book(extracted, name=book_name)
        all_units=exercise_units(book,unrestricted=True)
        answer_units=[u for u in all_units if any(ANSWER_HEADING.match(p) for p in u['section_path'])]
        units=[u for u in all_units if not any(ANSWER_HEADING.match(p) for p in u['section_path'])]
        if book.source_metadata.get('review_source_mode') == 'examples':
            units = [u for u in units if u['kind']=='example']
        if not units and book.blocks and book.source_metadata.get('review_source_mode') != 'examples':
            # Unnumbered source remains available as an explicitly uncertain unit.
            from ingestion.document_structure import block_role, NON_PRACTICE
            body = [b for b in book.blocks if b.block_type != 'heading' and block_role(b) not in NON_PRACTICE and not any(ANSWER_HEADING.match(p) for p in b.section_path)]
            if body:
                units = [dict(unit_id=body[0].block_id, kind='example', text='\n\n'.join(b.text for b in body),
                              chapter=book_name, section_path=[book_name], page_start=body[0].page_start,
                              page_end=body[-1].page_end, source_block_ids=[b.block_id for b in body], truncated=False, header_ids=[])]
        paired, all_answer_ids = 0, set()
        if answer_units:
            all_answer_ids.update(bid for unit in answer_units for bid in unit['source_block_ids'])
            paired = pair_answer_units(units,answer_units,book)
        if answer:
            answer_book = file_book(answer, name=book_name, prefix='a')
            answer_units = exercise_units(answer_book, unrestricted=True)
            all_answer_ids.update(b.block_id for b in answer_book.blocks)
            book.blocks.extend(answer_book.blocks)
            paired += pair_answer_units(units, answer_units, book)
        version, _ = self.examples.load()
        registry = source_registry(book, units, {b.block_id for b in book.blocks})
        source_id = uuid.uuid4().hex
        payload = dict(book_name=book_name, source_id=source_id, canonical_hash=canonical_book_fingerprint(book),
                       units=units, source_blocks=registry, profile_version=version,
                       provider=extracted.provider, paired_answers=paired,
                       raw_hash=hashlib.sha256(extracted.text.encode()).hexdigest(),
                       unmatched_answer_text='\n\n'.join(b.text for b in book.blocks if b.block_id in all_answer_ids
                           and b.block_id not in {bid for u in units for bid in u.get('answer_block_ids', [])}))
        from dataclasses import asdict
        payload['canonical_source'] = asdict(extracted.canonical_book or file_book(extracted,name=book_name))
        payload['answer_source'] = (dict(text=answer.text, file_type=answer.file_type, provider=answer.provider,
            canonical_book=asdict(answer.canonical_book) if answer.canonical_book else None) if answer else None)
        payload['structure_review'] = (extracted.canonical_book.source_metadata.get('structure_review', {}) if extracted.canonical_book else {})
        payload['snapshot_hash'] = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        # Validation of the registry budgets occurs before persistence.
        atomic_write_json(self.root / f'{source_id}.json', payload)
        if extracted.file_type=='zip' and extracted.asset_root:
            pdfs=list(Path(extracted.asset_root).rglob('*.pdf'))
            if len(pdfs)==1:
                self.attach_review_pdf(source_id,book_name,pdfs[0])
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
                managed = visual.get('asset_relpath','') if isinstance(visual,dict) else block.attributes.get('asset_relpath','')
                path = _controlled_source_path(Path(root),managed)
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
        payload = json.loads((self.root / f'{source_id}.json').read_text(encoding='utf-8'))
        checksum = payload.pop('snapshot_hash', '')
        if hashlib.sha256(canonical_json(payload).encode()).hexdigest() != checksum:
            raise ValueError('文件来源快照校验失败，请重新分析')
        if payload['book_name'] != book_name or payload['source_id'] != source_id:
            raise ValueError('文件来源不属于当前题库范围')
        return self._extracted(payload)

    def answer_source(self, source_id, book_name):
        self.load(source_id, book_name)
        raw = json.loads((self.root / f'{source_id}.json').read_text(encoding='utf-8')).get('answer_source')
        if not raw:
            return None
        from memory.exercise_file_importer import ExtractedExerciseText
        canonical = raw.get('canonical_book')
        if canonical:
            canonical = CanonicalBook(**{**canonical, 'blocks': [DocumentBlock.from_dict(b) for b in canonical['blocks']]})
        return ExtractedExerciseText(text=raw['text'], file_type=raw['file_type'], provider=raw['provider'], canonical_book=canonical)

    def review_reference(self, source_id, book_name):
        self.load(source_id,book_name)
        raw=json.loads((self.root/f'{source_id}.json').read_text(encoding='utf-8'))
        origin=((raw.get('canonical_source') or {}).get('source_metadata') or {}).get('review_origin_source_id') or source_id
        if origin!=source_id:self.load(origin,book_name)
        return origin

    def rebuild(self,source_id,book_name):
        """Reproject stored raw/corrected sources locally; never request a model."""
        origin=self.review_reference(source_id,book_name)
        def raw_book(reference):
            data=json.loads((self.root/f'{reference}.json').read_text(encoding='utf-8'))['canonical_source']
            return CanonicalBook(**{**data,'blocks':[DocumentBlock.from_dict(b) for b in data['blocks']]})
        reviewed,original=raw_book(source_id),raw_book(origin)
        from ingestion.document_structure import has_exercise_scopes
        reviewed.source_metadata['exercise_scope_policy']='regions' if has_exercise_scopes(original) else 'all'
        reviewed.source_metadata['review_origin_source_id']=origin
        reviewed.source_metadata['local_reprojection_from']=source_id
        from memory.exercise_file_importer import ExtractedExerciseText
        extracted=ExtractedExerciseText('\n\n'.join(b.text for b in reviewed.blocks),'zip',provider='local-reprojection',canonical_book=reviewed)
        _,next_id,_=self.create(extracted,book_name=book_name,answer=self.answer_source(source_id,book_name))
        return next_id

    def _extracted(self, payload):
        version, markers = self.examples.load(payload['profile_version'])
        return ExtractedTextbookExerciseText(text='\n\n'.join(u['text'] for u in payload['units']),
            provider='file-source-units', book_name=payload['book_name'], units=payload['units'],
            canonical_hash=payload['canonical_hash'], source_blocks=payload['source_blocks'],
            profile_version=version, solution_markers=markers, unmatched_answer_text=payload.get('unmatched_answer_text', ''),
            source_coverage=((payload.get('canonical_source') or {}).get('source_metadata') or {}).get('source_page_coverage',[]))
