"""Build/reversibly install a source-coordinate projection, never an IR/index rewrite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.document_ir import canonical_paths
from ingestion.document_workflows import load_workflow_book
from ingestion.figure_layout import LAYOUT_FILENAME, load_caption_projection, project_figure_layout
from ingestion.mineru_structured import build_caption_projection
from ingestion.figure_audit import audit_figures, verify_figure_repair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', required=True)
    parser.add_argument('--progress-root', type=Path, required=True)
    parser.add_argument('--vector-root', type=Path, required=True)
    parser.add_argument('--source-json', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--install', action='store_true', help='Install only the derived, rollbackable caption file')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.progress_root.resolve()) or output.is_relative_to(args.vector_root.resolve()):
        parser.error('Candidate report must be outside textbook/index directories')
    book = load_workflow_book(args.book, progress_root=args.progress_root, vector_root=args.vector_root)
    if book is None:
        parser.error('Canonical textbook not found')
    source_bytes = args.source_json.read_bytes()
    projection = build_caption_projection(book, json.loads(source_bytes))
    projection['source_sha256'] = hashlib.sha256(source_bytes).hexdigest()
    layout = project_figure_layout(book, projection['caption_nodes'])
    document, _ = canonical_paths(args.book, progress_root=args.progress_root)
    audit = audit_figures(book, nodes=projection['caption_nodes'], asset_root=document.parent)
    projection['audit'] = audit
    projection['verification'] = verify_figure_repair(book, project_figure_layout(book), layout, audit)
    unique_groups = {tuple(m.block_id for m in g) for g in layout.groups.values()}
    figures = [b for b in book.blocks if b.block_type == 'figure']
    projection['summary'] = dict(figure_blocks=len(figures), groups=len(unique_groups),
                                 grouped_members=len(layout.groups), numbered_members=len(layout.details),
                                 catalog_items=len(figures)-len(layout.groups)+len(unique_groups),
                                 unresolved=len(layout.issues),
                                 structural_status=projection['verification']['structural_status'],
                                 quality_status=projection['verification']['quality_status'],
                                 audit_suspects=audit['summary']['suspects'],
                                 audit_unverifiable=audit['summary']['unverifiable'],
                                 unnumbered_blocks=[b.block_id for b in figures if b.block_id not in layout.details])
    projection['resolved_figures'] = {bid: detail for bid, detail in layout.details.items()
                                      if bid == detail['member_ids'][-1]}
    projection['issues'] = layout.issues
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(projection, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    load_caption_projection(book, output)  # Validate candidate contract before install.
    if args.install:
        if projection['verification']['structural_status'] != 'passed':
            raise ValueError('修复候选未通过结构校验；审核报告已保存，关联未安装')
        from ingestion.index_snapshot import index_read_snapshot
        # Recheck the version before installation. Readers also reject stale
        # hashes, including imports occurring in a different desktop process.
        with index_read_snapshot():
            current = load_workflow_book(args.book, progress_root=args.progress_root, vector_root=args.vector_root)
            from ingestion.document_ir import canonical_book_fingerprint
            if current is None or canonical_book_fingerprint(current) != projection['canonical_hash']:
                raise RuntimeError('教材在修复期间发生版本变化，关联未安装')
            document, _ = canonical_paths(args.book, progress_root=args.progress_root)
            target = document.parent / LAYOUT_FILENAME
            if target.is_symlink():
                raise ValueError('Refusing a symlink projection target')
            if target.exists():
                prior = target.read_bytes()
                backup = target.with_name(f'figure_layout.previous-{hashlib.sha256(prior).hexdigest()[:12]}.json')
                if not backup.exists():
                    backup.write_bytes(prior)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.figure-layout-', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(output.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        projection['summary']['installed_path'] = str(target)
    print(json.dumps(projection['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
