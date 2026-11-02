"""Exercise-owned, managed source images; ownership never comes from a client path."""
from pathlib import Path
import re

FORMATS = {'.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
           '.gif': 'image/gif', '.bmp': 'image/bmp', '.tiff': 'image/tiff'}


def freeze_attachments(projection, extracted, *, book_name, progress_root):
    from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
    from ingestion.document_ir import canonical_paths
    from ingestion.document_adapters import _controlled_source_path
    root = Path(progress_root)
    registry = {b['block_id']: b for b in extracted.source_blocks}
    attachments = []
    excluded = set(projection.get('excluded_figure_ids') or [])
    for role, spans in projection['parts'].items():
        for span in spans:
            if span['block_id'] in excluded:
                continue
            block = registry[span['block_id']]
            attrs = block['attributes']
            if block['block_type'] != 'figure' or not attrs.get('asset_id'):
                continue
            aid, suffix = attrs['asset_id'], attrs.get('asset_format', '')
            if not re.fullmatch(r'[a-f0-9]{64}', aid) or suffix not in FORMATS:
                raise ValueError('题目来源图片格式无效')
            if projection.get('source_id'):
                source, _ = ExerciseFileAnalysisStore(root).asset(projection['source_id'], aid, book_name)
            else:
                # Textbook assets are owned by the active Canonical source.
                from ingestion.document_ir import load_canonical_book
                canonical = load_canonical_book(book_name, progress_root=root)
                source_block = next((b for b in canonical.blocks if b.block_id == block['block_id']), None)
                if source_block is None:
                    raise ValueError('教材图片来源已改变')
                source = _controlled_source_path(canonical_paths(book_name, progress_root=root)[0].parent,
                                                  source_block.attributes.get('asset_relpath', ''))
                if source is None:
                    raise ValueError('教材图片暂不可读取')
            target = root / 'exercise_assets' / (aid + suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                from ingestion.document_adapters import _atomic_copy
                _atomic_copy(source, target)
            attachments.append(dict(asset_id=aid, format=suffix, label=block['text'], role='question' if role == 'unassigned' else role,
                                    source_block_id=block['block_id'], page=block['page_start']))
    return list({(a['asset_id'], a['role']): a for a in attachments}.values())


def attachment_file(record, asset_id, *, progress_root):
    if not re.fullmatch(r'[a-f0-9]{64}', asset_id):
        raise FileNotFoundError('题目图片不存在')
    attachment = next((a for a in record.extra_fields.get('source_attachments', []) if a['asset_id'] == asset_id), None)
    if not attachment or attachment.get('format') not in FORMATS:
        raise FileNotFoundError('题目没有这张图片')
    path = Path(progress_root) / 'exercise_assets' / (asset_id + attachment['format'])
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError('题目图片缺失，请从备份恢复或重新导入')
    return path, FORMATS[attachment['format']]
