"""Automatic intake diagnostics and deterministic source-to-index loss checks."""
from ingestion.heading_policy import body_title, exercise_heading, PROBLEM_START


def structure_summary(book):
    from ingestion.document_ir import canonical_retrieval_paths, canonical_chapter_title
    from ingestion.document_workflows import learning_units
    paths = canonical_retrieval_paths(book.blocks)
    headings = [b for b in book.blocks if b.block_type == 'heading']
    units = learning_units(book)
    exercise_sections = [b for b in headings if exercise_heading(b.text) or b.attributes.get('outline_role') == 'exercise']
    exercise_paths = [paths.get(b.block_id, []) for b in exercise_sections]
    exercise_starts = [b.block_id for b in book.blocks if not b.attributes.get('outline_toc') and PROBLEM_START.match(b.text)
                       and any(paths.get(b.block_id, [])[:len(p)] == p for p in exercise_paths)]
    recognized = {u.unit_id for u in units if u.kind == 'exercise'}
    empty_sections = [b.block_id for b, path in zip(exercise_sections, exercise_paths)
                      if not any(u.kind == 'exercise' and u.section_path[:len(path)] == path for u in units)]
    return dict(policy_version=1,
                chapters=sum(b.attributes.get('outline_level') == 1 if 'outline_source' in b.attributes
                             else bool(canonical_chapter_title(b.text)) for b in headings),
                headings=len(headings),
                title_blocks_retained_as_body=sum(b.attributes.get('heading_decision') == 'retained_as_body' for b in book.blocks),
                suspicious_heading_ids=[b.block_id for b in headings if body_title(b.text) and not b.attributes.get('outline_level')],
                exercise_sections=len(exercise_sections),
                exercise_starts=len(exercise_starts),
                exercise_units=sum(u.kind == 'exercise' for u in units),
                example_units=sum(u.kind == 'example' for u in units),
                exercise_sections_without_units=empty_sections,
                unrecognized_exercise_start_ids=[bid for bid in exercise_starts if bid not in recognized])


def validate_index_structure(book, chunks):
    """Check exact source ranges, content integrity and same-chapter coverage.

    This is a mechanical preservation check, before opening vector stores.
    Ambiguous OCR/title semantics are report warnings, never guessed answers.
    """
    from ingestion.document_ir import BODY_BLOCK_TYPES, canonical_retrieval_paths
    from ingestion.source_spans import SPAN_SCHEMA, TEXT_REPRESENTATION, source_representation, text_hash, uncovered_ranges
    paths = canonical_retrieval_paths(book.blocks)
    sources = {b.block_id: (b, *source_representation(b)) for b in book.blocks}
    covered = {}
    ranges = {}
    errors = []
    for chunk in chunks:
        if not chunk.get('retrieval_excluded'):
            for bid in chunk.get('source_block_ids', []):
                covered.setdefault(bid, set()).add(chunk.get('chapter'))
            content = str(chunk.get('content') or '')
            if not content.strip():
                continue
            spans = chunk.get('source_spans')
            if chunk.get('source_span_schema') != SPAN_SCHEMA or not isinstance(spans, list) or not spans:
                errors.append('missing_source_spans:' + str(chunk.get('chunk_id')))
                continue
            content_ranges, ids = [], set()
            for span in spans:
                if (not isinstance(span, dict) or not isinstance(span.get('block_id'), str)
                        or span['block_id'] not in sources):
                    errors.append('unknown_source_span')
                    continue
                bid = span['block_id']
                block, representation, source = sources[bid]
                start, end, left, right = [span.get(k) for k in ('source_start', 'source_end', 'content_start', 'content_end')]
                if (not all(type(n) is int for n in (start, end, left, right))
                        or not 0 <= start < end <= len(source) or not 0 <= left < right <= len(content)):
                    errors.append('invalid_source_span:' + bid)
                    continue
                if (span.get('representation') != representation or span.get('source_sha256') != text_hash(block.text)
                        or source[start:end] != content[left:right]):
                    errors.append('source_span_content_mismatch:' + bid)
                    continue
                ids.add(bid)
                content_ranges.append((left, right))
                ranges.setdefault(bid, []).append((start, end))
                if (paths.get(bid) or [book.book_name])[0] != chunk.get('chapter'):
                    errors.append('wrong_chapter_span:' + bid)
            if ids != set(chunk.get('source_block_ids') or []):
                errors.append('source_span_membership_mismatch:' + str(chunk.get('chunk_id')))
            if any(content[a:b].strip() for a, b in uncovered_ranges(len(content), content_ranges)):
                errors.append('unattributed_content:' + str(chunk.get('chunk_id')))
    missing, misplaced = [], []
    verbatim_blocks = rendered_tables = 0
    for block in book.blocks:
        searchable_title = block.block_type == 'heading' and block.attributes.get('heading_rule') == 'bounded_unnumbered'
        if (block.attributes.get('outline_toc') or
                (block.block_type not in BODY_BLOCK_TYPES and not searchable_title) or not block.text.strip()):
            continue
        chapters = covered.get(block.block_id, set())
        if not chapters:
            missing.append(block.block_id)
        elif (paths.get(block.block_id) or [book.book_name])[0] not in chapters:
            misplaced.append(block.block_id)
        representation, source = sources[block.block_id][1:]
        if representation == TEXT_REPRESENTATION:
            verbatim_blocks += 1
        else:
            rendered_tables += 1
        gaps = uncovered_ranges(len(source), ranges.get(block.block_id, []))
        # Whitespace inserted by the deterministic table serializer is layout;
        # verbatim source text (including its internal spaces) is fully covered.
        if any(a < b if representation == TEXT_REPRESENTATION else bool(source[a:b].strip()) for a, b in gaps):
            errors.append('uncovered_source_span:' + block.block_id)
    if missing or misplaced or errors:
        raise RuntimeError('教材结构保真校验失败，候选索引未发布：'
                           f'missing_body_blocks={missing[:20]}, wrong_chapter_blocks={misplaced[:20]}, span_errors={errors[:20]}')
    return dict(covered_body_blocks=len(covered), missing_body_blocks=0, wrong_chapter_blocks=0,
                source_span_contract=SPAN_SCHEMA, span_errors=0,
                verbatim_blocks=verbatim_blocks, rendered_table_blocks=rendered_tables,
                table_originals='retained_in_canonical')
