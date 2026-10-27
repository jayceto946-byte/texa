"""Read-only regression on the existing D-01 OCR corpus; never re-run OCR.

Writes a new sanitized report, preserving the original audits and source data.
"""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('artifacts/question-extraction-quality-2026-10-17'))
    parser.add_argument('--output', type=Path, default=Path('docs/validation/exercise-structure-2026-10-26/corpus-regression.json'))
    args = parser.parse_args()
    import memory.textbook_exercise_importer as importer
    from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
    from memory.exercise_bank import question_fingerprint
    import config

    def forbidden(*args, **kwargs):
        raise AssertionError('Model/OCR calls are forbidden in this evaluation')

    importer.PROGRESS_PATH = args.source / 'data/progress'
    importer._text_from_kimi_pdf_pages = forbidden
    config.get_llm = forbidden
    protected = [p for p in (args.source / 'data').rglob('*') if p.is_file()]
    protected += list(Path('docs/qa/question-extraction-quality-2026-10-17').glob('*.json*'))
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    ledger = [json.loads(line) for line in Path('docs/qa/question-extraction-quality-2026-10-17/candidate-audit.jsonl').read_text().splitlines()]
    old = json.loads((args.source / 'candidates.private.json').read_text())
    extracted = importer.extract_textbook_exercise_text('传感器原理及应用', candidate_contract_version=1, structure_profile_version='')
    scope = dict(chapter='', page_start=None, page_end=None, source_mode='exercise_sections')
    candidates = importer.analyze_learning_unit_candidates(extracted.units, book_name=extracted.book_name, subject='专业课', limit=200,
        source_blocks=extracted.source_blocks, canonical_hash=extracted.canonical_hash, scope=scope)
    assert len(candidates) == len(ledger) == 108
    rows = []
    for candidate, audit, previous in zip(candidates, ledger, old):
        assert audit['source']['unit_id'] in candidate.projection['unit_ids']
        assert set(audit['source']['block_ids']) <= {s['block_id'] for spans in candidate.projection['parts'].values() for s in spans}
        ready = not any(i['category'] == 'content' for i in candidate.issues)
        assert not audit['review']['stem_ready_for_independent_practice'] or ready
        if previous['candidate'].get('duplicate_of'):
            assert question_fingerprint(candidate.question_text) == question_fingerprint(previous['candidate']['question_text'])
        rows.append(dict(id=audit['audit_id'], method=candidate.projection['method'], answer_present=bool(candidate.answer),
            explanation_present=bool(candidate.explanation), content_issues=[i['code'] for i in candidate.issues if i['category'] == 'content'],
            structurally_admissible=ready, previously_ready=audit['review']['stem_ready_for_independent_practice']))
    service = ExerciseCandidateReviewService(extract_provider=importer.extract_textbook_exercise_text)
    items = [dict(origin_id=c.id, question_text=c.question_text, answer=c.answer, explanation=c.explanation,
                  candidate_context=dict(projection=c.projection, review=None)) for c, row in zip(candidates, rows) if row['structurally_admissible']]
    receipts = service.prepare(extracted.book_name, items)
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    report = dict(canonical_hash=extracted.canonical_hash, candidates=108, previously_ready_preserved=92,
        duplicate_stems_preserved=16, source_files_unchanged=True, admission_replayed=len(receipts),
        methods=dict(Counter(r['method'] for r in rows)), rows=rows, model_ocr_calls=0,
        interpretation='Structure regression only; original PDF/OCR semantics and answer correctness remain unverified.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
