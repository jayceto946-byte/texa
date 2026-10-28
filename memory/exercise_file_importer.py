"""Extract text from uploaded exercise files before rule-based candidate analysis."""
from __future__ import annotations

import re
import time
import zipfile
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

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
    paragraphs: list[str] = []
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as docx:
            infos, _ = inspect_zip_limits(
                docx,
                max_files=MAX_DOCX_FILES,
                max_expanded_bytes=MAX_DOCX_EXPANDED_BYTES,
                max_member_bytes=MAX_DOCX_MEMBER_BYTES,
            )
            names = [info.filename for info in infos if info.filename.startswith("word/") and info.filename.endswith(".xml")]
            main_names = ["word/document.xml"] + sorted(name for name in names if name.startswith("word/header") or name.startswith("word/footer"))
            for name in main_names:
                if name not in docx.namelist():
                    continue
                root = ET.fromstring(docx.read(name))
                paragraphs.extend(_paragraph_texts(root))
    except zipfile.BadZipFile as exc:
        raise ValueError("Word 文件格式无效或已损坏") from exc
    except ET.ParseError as exc:
        raise ValueError("Word XML 解析失败") from exc

    text = _normalize_text("\n".join(paragraphs))
    if not text:
        warnings.append("未从 Word 文件中提取到文本，可能是图片型文档或加密文档。")
    return ExtractedExerciseText(text=text, file_type="docx", provider="docx-xml", warnings=warnings)


def _paragraph_texts(root: ET.Element) -> list[str]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    output: list[str] = []
    for para in root.findall(".//w:p", ns):
        pieces: list[str] = []
        for node in para.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                pieces.append(node.text)
            elif tag == "tab":
                pieces.append("\t")
            elif tag in {"br", "cr"}:
                pieces.append("\n")
        line = "".join(pieces).strip()
        if line:
            output.append(line)
    return output


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
    text = '\n\n'.join(b.text for b in canonical.blocks if b.text)
    if not text.strip():
        raise ValueError("MinerU 未返回可切分文本")
    return ExtractedExerciseText(text=text, file_type="pdf", provider="mineru", warnings=[], canonical_book=canonical,
                                 asset_root=output_dir)


def _extract_pdf_text_layer(path: Path) -> ExtractedExerciseText:
    import fitz
    from ingestion.document_ir import CanonicalBook, DocumentBlock

    warnings: list[str] = []
    pages: list[str] = []
    blocks = []
    with fitz.open(path) as doc:
        page_count = doc.page_count
        text_pages = 0
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                text_pages += 1
                pages.append(f"\n\n[Page {index}]\n{text}")
            else:
                pages.append(f"\n\n[Page {index}]\n")
            for block_index, raw in enumerate(page.get_text('blocks')):
                if len(raw) > 6 and raw[6] == 0 and raw[4].strip():
                    blocks.append(DocumentBlock(f'p{index}-b{block_index}', 'paragraph', raw[4], [path.stem],
                        page_start=index, page_end=index, bbox=[raw[0] / page.rect.width, raw[1] / page.rect.height,
                                                              raw[2] / page.rect.width, raw[3] / page.rect.height],
                        source_kind='pdf_text', source_file=path.name,
                        attributes=dict(bbox_space='page', bbox_format='xyxy', bbox_units='normalized')))

    text = _normalize_text("".join(pages))
    if page_count and text_pages == 0:
        warnings.append("该 PDF 未检测到文本层，疑似扫描件。")
    elif page_count and text_pages < page_count:
        warnings.append(f"部分页面没有文本层：共 {page_count} 页，提取到文本的页面 {text_pages} 页。")
    canonical = CanonicalBook(path.stem, path.stem, blocks, 'exercise-pdf-text-v1', source_page_count=page_count)
    return ExtractedExerciseText(text=text, file_type="pdf", page_count=page_count, text_pages=text_pages,
                                 provider="pdf-text-layer", warnings=warnings, canonical_book=canonical)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
