"""Extract text from uploaded exercise files before rule-based candidate analysis."""
from __future__ import annotations

import re
import time
import zipfile
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path

from config import MINERU_API_URL, MINERU_OUTPUT_PATH, MINERU_TASK_POLL_SECONDS, MINERU_TASK_TIMEOUT_SECONDS
from utils.resource_limits import (
    MAX_DOCX_EXPANDED_BYTES,
    MAX_DOCX_FILES,
    MAX_DOCX_MEMBER_BYTES,
    inspect_zip_limits,
    validate_zip_paths,
    ensure_disk_space,
)



@dataclass
class ExtractedExerciseText:
    text: str
    file_type: str
    page_count: int = 0
    text_pages: int = 0
    provider: str = "local"
    warnings: list[str] | None = None
    canonical_book: object | None = None
    asset_root: Path | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "text_pages": self.text_pages,
            "provider": self.provider,
            "warnings": self.warnings or [],
        }


def extract_exercise_text(path: str | Path) -> ExtractedExerciseText:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_text(file_path)
    if suffix == ".pdf":
        return extract_pdf_text(file_path)
    if suffix == ".zip":
        return extract_mineru_archive(file_path)
    raise ValueError("仅支持 Word、PDF 和 MinerU 解析包（.zip）")


def extract_mineru_archive(path: Path) -> ExtractedExerciseText:
    """Use the textbook adapter directly; never submit an existing OCR ZIP."""
    from ingestion.document_adapters import MinerUAdapter
    root = Path(tempfile.mkdtemp(prefix='mineru-exercises-', dir=path.parent))
    try:
        with zipfile.ZipFile(path) as archive:
            infos, expanded = inspect_zip_limits(archive)
            validate_zip_paths(infos, root)
            ensure_disk_space(root, expanded)
            archive.extractall(root)
        canonical = MinerUAdapter.from_output_dir(root, book_name=path.stem)
        from ingestion.source_page_coverage import mark_page_coverage
        canonical=mark_page_coverage(canonical)
        text = '\n\n'.join(b.text for b in canonical.blocks if b.text)
        if not text.strip():
            raise ValueError('包中没有可用的 MinerU 解析正文，请选择完整解析结果 ZIP')
        return ExtractedExerciseText(text=text, file_type='zip', provider='mineru-archive',
            page_count=canonical.source_page_count or 0,
            text_pages=len({b.page_start for b in canonical.blocks if b.text and b.page_start}),
            warnings=list(canonical.warnings), canonical_book=canonical, asset_root=root)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def extract_docx_text(path: Path) -> ExtractedExerciseText:
    from ingestion.docx_source import read_docx
    root=Path(tempfile.mkdtemp(prefix='word-exercises-',dir=path.parent))
    try:
        with zipfile.ZipFile(path) as archive:
            inspect_zip_limits(archive,max_files=MAX_DOCX_FILES,max_expanded_bytes=MAX_DOCX_EXPANDED_BYTES,max_member_bytes=MAX_DOCX_MEMBER_BYTES)
            book,warnings=read_docx(archive,name=path.stem,asset_root=root)
        text='\n\n'.join(b.text for b in book.blocks)
        if not text:warnings.append('未从Word提取到内容，请提供可读取的Word或PDF。')
        return ExtractedExerciseText(text=text,file_type='docx',provider='docx-xml',warnings=warnings,canonical_book=book,asset_root=root)
    except Exception:
        shutil.rmtree(root,ignore_errors=True)
        raise


def extract_pdf_text(path: Path) -> ExtractedExerciseText:
    if MINERU_API_URL:
        try:
            return _extract_pdf_text_with_mineru(path)
        except Exception as exc:
            local = _extract_pdf_text_layer(path)
            local.warnings = (local.warnings or []) + [f"MinerU 解析失败，已降级为 PDF 文本层：{exc}"]
            return local
    local = _extract_pdf_text_layer(path)
    if local.page_count and local.text_pages < local.page_count:
        local.warnings = (local.warnings or []) + ["未配置 MINERU_API_URL，扫描页无法可靠切题。"]
    return local


def _extract_pdf_text_with_mineru(path: Path) -> ExtractedExerciseText:
    from ingestion.mineru_client import MinerUClient
    from ingestion.document_adapters import MinerUAdapter

    output_dir = MINERU_OUTPUT_PATH / "exercise_imports" / f"{path.stem}_{int(time.time())}"
    output_dir.mkdir(parents=True, exist_ok=True)
    client = MinerUClient(MINERU_API_URL)
    task_id = client.submit_pdf(path, parse_method="auto")
    client.wait_for_task(task_id, MINERU_TASK_TIMEOUT_SECONDS, MINERU_TASK_POLL_SECONDS)
    client.fetch_result(task_id, output_dir)
    canonical = MinerUAdapter.from_output_dir(output_dir, book_name=path.stem)
    from ingestion.source_page_coverage import mark_page_coverage
    canonical=mark_page_coverage(canonical)
    text = '\n\n'.join(b.text for b in canonical.blocks if b.text)
    if not text.strip():
        raise ValueError("MinerU 未返回可切分文本")
    return ExtractedExerciseText(text=text, file_type="pdf", provider="mineru", warnings=[], canonical_book=canonical,
                                 asset_root=output_dir)


def _ordered_pdf_blocks(page):
    """Read column bands between spanning headings, keeping physical block identities."""
    # A PDF text block may combine left/right column lines on the same baseline.
    # Keep each physical line's own box before ordering column bands.
    blocks=[]
    for i,block in enumerate(page.get_text('dict')['blocks']):
        if block['type']!=0:continue
        for j,line in enumerate(block['lines']):
            text=''.join(span['text'] for span in line['spans'])
            if text.strip():blocks.append((f'{i}-l{j}',(*line['bbox'],text,i,0)))
    middle=page.rect.width/2;gutter=page.rect.width*.02
    spanning=sorted([(i,b) for i,b in blocks if b[0]<middle and b[2]>middle],key=lambda item:item[1][1])
    remaining=[item for item in blocks if item not in spanning]
    result=[]
    for separator in [*spanning,None]:
        top=separator[1][1] if separator else float('inf')
        band=[item for item in remaining if (item[1][1]+item[1][3])/2<top]
        remaining=[item for item in remaining if item not in band]
        left=[item for item in band if item[1][2]<=middle+gutter]
        right=[item for item in band if item[1][0]>=middle-gutter]
        if len(left)>=2 and len(right)>=2 and len(left)+len(right)==len(band):
            result.extend(sorted(left,key=lambda item:item[1][1]));result.extend(sorted(right,key=lambda item:item[1][1]))
        else:result.extend(sorted(band,key=lambda item:(item[1][1],item[1][0])))
        if separator:result.append(separator)
    return result


def _extract_pdf_text_layer(path: Path) -> ExtractedExerciseText:
    import fitz
    from ingestion.document_ir import CanonicalBook, DocumentBlock

    warnings: list[str] = []
    blocks = []
    with fitz.open(path) as doc:
        page_count = doc.page_count
        text_pages = 0
        for index, page in enumerate(doc, start=1):
            ordered=_ordered_pdf_blocks(page)
            text_pages+=bool(ordered)
            for block_index, raw in ordered:
                if len(raw) > 6 and raw[6] == 0 and raw[4].strip():
                    blocks.append(DocumentBlock(f'p{index}-b{block_index}', 'paragraph', raw[4], [path.stem],
                        page_start=index, page_end=index, bbox=[raw[0] / page.rect.width, raw[1] / page.rect.height,
                                                              raw[2] / page.rect.width, raw[3] / page.rect.height],
                        source_kind='pdf_text', source_file=path.name,
                        attributes=dict(bbox_space='page', bbox_format='xyxy', bbox_units='normalized')))

    text = _normalize_text('\n\n'.join(f'[Page {page}]\n'+'\n\n'.join(b.text for b in blocks if b.page_start==page) for page in range(1,page_count+1)))
    if page_count and text_pages == 0:
        warnings.append("该 PDF 未检测到文本层，疑似扫描件。")
    elif page_count and text_pages < page_count:
        warnings.append(f"部分页面没有文本层：共 {page_count} 页，提取到文本的页面 {text_pages} 页。")
    canonical = CanonicalBook(path.stem, path.stem, blocks, 'exercise-pdf-text-v1', source_page_count=page_count)
    from ingestion.source_page_coverage import mark_page_coverage
    canonical=mark_page_coverage(canonical)
    return ExtractedExerciseText(text=text, file_type="pdf", page_count=page_count, text_pages=text_pages,
                                 provider="pdf-text-layer", warnings=warnings, canonical_book=canonical)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
