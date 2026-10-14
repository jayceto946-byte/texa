"""Audit one/many existing textbooks without OCR, image editing or index writes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.figure_audit import textbook_figure_audit
from ingestion.figure_audit import compare_audits
from utils.path_safety import safe_book_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--book', action='append', help='Repeat for several books')
    selection.add_argument('--all', action='store_true', help='All books with a persisted Canonical IR')
    parser.add_argument('--progress-root', type=Path, required=True)
    parser.add_argument('--vector-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--compare-with', type=Path, help='Prior audit; valid only for one book and same policy/IR')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if any(output.is_relative_to(root.resolve()) for root in [args.progress_root, args.vector_root]):
        parser.error('Audit output must be outside textbook/index directories')
    names = sorted(path.parent.name for path in args.progress_root.glob('*/canonical_document.jsonl')) if args.all else args.book
    if args.compare_with and len(names) != 1:
        parser.error('--compare-with requires exactly one book')
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in names:
        try:
            report = textbook_figure_audit(name, progress_root=args.progress_root, vector_root=args.vector_root)
            if args.compare_with:
                report['comparison'] = compare_audits(json.loads(args.compare_with.read_text(encoding='utf-8')), report)
            path = output / f'{safe_book_name(name)}.figure-audit.json'
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            results.append(dict(book=name, status=report['status'], summary=report['summary'], report=str(path)))
        except (ValueError, FileNotFoundError) as exc:
            # A broken/stale book cannot hide results from other books.
            results.append(dict(book=name, status='failed', error=str(exc)))
    (output / 'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False))
    if any(row['status'] in {'failed', 'blocked'} for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
