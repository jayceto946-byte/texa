"""Read-only textbook audit use case; independent of HTTP and model runtimes."""
from pathlib import Path

from ingestion.document_ir import canonical_paths
from ingestion.document_workflows import load_workflow_book
from ingestion.figure_audit import audit_figures
from ingestion.figure_layout import LAYOUT_FILENAME, load_caption_projection


def textbook_figure_audit(book_name: str, *, progress_root: Path, vector_root: Path,
                           check_assets: bool = True) -> dict:
    book = load_workflow_book(book_name, progress_root=progress_root, vector_root=vector_root)
    if book is None:
        raise FileNotFoundError('教材没有 Canonical 来源，无法审核图片')
    directory = canonical_paths(book_name, progress_root=progress_root)[0].parent
    # Native IR owns its nodes. Historic IR can use a hash-bound projection.
    native = all('visual_captions' in b.attributes for b in book.blocks if b.block_type == 'figure')
    nodes = None if native else load_caption_projection(book, directory / LAYOUT_FILENAME)
    return audit_figures(book, nodes=nodes, asset_root=directory if check_assets else None)
