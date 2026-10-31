"""Explicit user outline boundaries, kept separately from untouched OCR text."""
from copy import deepcopy

from ingestion.document_ir import DocumentBlock


def apply_outline_edits(book, edits):
    result = deepcopy(book)
    result.blocks = [b for b in result.blocks if not b.attributes.get('manual_outline_node')]
    by_id = {b.block_id: b for b in result.blocks}
    pending = {}
    seen = set()
    for edit in edits:
        node_id = edit['node_id']
        if node_id in seen:
            raise ValueError('同一标题不能重复提交修改')
        seen.add(node_id)
        original = by_id.get(node_id)
        boundary = by_id.get(node_id.removeprefix('boundary:')) if node_id.startswith('boundary:') else None
        level = edit['level']
        if not 0 <= level <= 6:
            raise ValueError('标题层级应为 1–6，或移出目录')
        if boundary and boundary.attributes.get('outline_boundary'):
            boundary.attributes.pop('outline_boundary')
        elif original:
            original.block_type = 'paragraph'
            original.attributes.update(outline_level=0, outline_method='user_edit')
        elif not edit.get('created'):
            raise ValueError('修改的标题已不存在，请重新打开目录')
        if level == 0:
            continue
        title = edit['title'].strip()
        if not title or len(title) > 140:
            raise ValueError('请输入不超过140字的目录标题')
        page = edit['page']
        anchor = by_id.get(edit.get('anchor_block_id', ''))
        if anchor is not None and anchor.page_start != page:
            raise ValueError('正文起点与物理页不一致，请重新选择')
        if anchor is None:
            anchor = next((b for b in result.blocks if b.page_start == page and not b.attributes.get('outline_toc')), None)
        if anchor is None:
            raise ValueError(f'物理第 {page} 页没有可定位的正文')
        pending.setdefault(anchor.block_id, []).append(DocumentBlock(
            block_id=f'manual:{node_id.removeprefix("boundary:")}:{anchor.block_id}', block_type='heading', text=title,
            section_path=[result.book_name], page_start=page, page_end=page,
            source_kind='user', source_file='outline correction',
            attributes=dict(manual_outline_node=True, manual_node_id=node_id, outline_level=level,
                heading_level=level, outline_title=title, outline_role=edit.get('role', 'section'),
                outline_method='user_edit', outline_visible=True)))
    blocks = []
    for block in result.blocks:
        blocks.extend(pending.get(block.block_id, []))
        blocks.append(block)
    result.blocks = blocks
    stack = []
    for block in blocks:
        if block.attributes.get('outline_toc'):
            continue
        boundary = block.attributes.get('outline_boundary')
        if boundary and not any(b.attributes['outline_level'] == 1 for b in pending.get(block.block_id, [])):
            from ingestion.document_ir import canonical_chapter_title
            title = canonical_chapter_title(boundary['title']) or boundary['title']
            level = next((i + 1 for i, value in enumerate(block.section_path) if value == title), 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title, f'toc:{boundary["source_block_id"]}:{boundary["toc_row"]}'))
        level = block.attributes.get('outline_level', 0) if block.block_type == 'heading' else 0
        if level:
            while stack and stack[-1][0] >= level:
                stack.pop()
            block.attributes['outline_parent_id'] = stack[-1][2] if stack else ''
            stack.append((level, block.attributes.get('outline_title', block.text), block.block_id))
        block.section_path = [entry[1] for entry in stack] or [result.book_name]
        block.attributes['outline_root_id'] = stack[0][2] if stack else ''
    roots = {}
    for block in blocks:
        root_id = block.attributes.get('outline_root_id')
        if not root_id:
            continue
        title = block.section_path[0]
        previous = roots.get(title)
        if previous and previous != root_id and (previous.startswith('manual:') or root_id.startswith('manual:')):
            raise ValueError(f'一级标题“{title}”已存在，请先移出原条目或使用不同标题')
        roots[title] = root_id
    result.source_metadata['outline_edits'] = deepcopy(edits)
    result.source_metadata['outline_recovery'].update(stable_scope_ids=True,
        roots=len({b.attributes['outline_root_id'] for b in blocks if b.attributes.get('outline_root_id')}))
    from ingestion.document_workflows import annotate_learning_units
    annotate_learning_units(result)
    return result
