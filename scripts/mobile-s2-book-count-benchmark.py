"""Read-only local-data probe; no textbook names/content, databases or models in output.
Run with Python3.10 and progress/vector paths. These are local CPU/I/O measurements, not DERP.
"""
import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.book_read_cache import BookReadCache
from backend.services.book_chapters import looks_like_external_ocr_chunk_titles, chapters_from_embedded_toc, chapters_from_ocr_headings
from ingestion.document_workflows import enrich_chapters, load_workflow_book

parser = argparse.ArgumentParser()
parser.add_argument('progress', type=Path)
parser.add_argument('vector', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
cache = BookReadCache()
files = sorted(args.progress.glob('*/_chapters.json'))

def original(path):
    data = cache.read_json(path, [])
    chapters = data if isinstance(data, list) else []
    if looks_like_external_ocr_chunk_titles(chapters):
        chapters = chapters_from_embedded_toc(chapters) or chapters_from_ocr_headings(chapters) or chapters
    return len(enrich_chapters(chapters, load_workflow_book(path.parent.name, progress_root=args.progress, vector_root=args.vector)))

def sample(fn):
    start = perf_counter()
    counts = [fn(path) for path in files]
    return {'ms': (perf_counter() - start) * 1000, 'counts': counts}

result = {'environment': 'local-read-only-data', 'books': len(files), 'baseline': [sample(original) for _ in range(6)]}
if hasattr(cache, 'chapter_count'):
    def optimized(path):
        dependencies = (path, path.parent / 'canonical_document.jsonl', args.vector / '_index_manifests' / f'{path.parent.name}.json')
        return cache.chapter_count(dependencies, lambda: original(path))
    result['optimized'] = [sample(optimized) for _ in range(6)]
    result['identicalCounts'] = all(row['counts'] == result['baseline'][0]['counts'] for row in result['baseline'] + result['optimized'])
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2))
print(json.dumps(result))
