"""Materialize immutable source crops without changing their retrieval semantics."""
from __future__ import annotations
from pathlib import Path, PurePosixPath
import re
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_paths

ASSET_SCHEMA = 'texa.original-visual-asset'
_FORMATS = {'.jpg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP', '.bmp': 'BMP', '.gif': 'GIF', '.tiff': 'TIFF'}


def visual_asset_errors(block: DocumentBlock) -> list[str]:
    asset = block.attributes.get('original_visual_asset')
    if asset is None:
        return []
    if not isinstance(asset, dict):
        return ['invalid_original_visual_asset']
    errors = []
    if asset.get('schema') != ASSET_SCHEMA or asset.get('version') != 1 or asset.get('role') != 'original_crop':
        errors.append('unsupported_original_visual_asset')
    if block.block_type not in {'formula', 'table'}:
        errors.append('unexpected_original_visual_asset')
    if asset.get('status') not in {'pending', 'ready', 'missing', 'invalid'}:
        errors.append('invalid_original_visual_status')
    for field in ('source_relpath', 'asset_relpath'):
        value = asset.get(field, '')
        if not isinstance(value, str) or (value and not safe_relative(value)):
            errors.append(f'invalid_original_visual_{field}')
    if asset.get('block_id') != block.block_id or asset.get('page_start') != block.page_start or asset.get('bbox') != (block.bbox or []):
        errors.append('original_visual_provenance_mismatch')
    for field in ('bbox_space', 'bbox_format', 'bbox_units'):
        if asset.get(field) != block.attributes.get(field):
            errors.append('original_visual_coordinates_mismatch')
    if asset.get('status') == 'ready':
        path = asset.get('asset_relpath', '')
        if not isinstance(path, str) or not path.startswith('original_visuals/'):
            errors.append('missing_original_visual_asset_relpath')
        if not re.fullmatch(r'[0-9a-f]{64}', str(asset.get('sha256', ''))):
            errors.append('invalid_original_visual_sha256')
        if any(type(asset.get(field)) is not int or asset[field] < 1 for field in ('width', 'height')):
            errors.append('invalid_original_visual_dimensions')
        if asset.get('image_format') not in _FORMATS.values():
            errors.append('invalid_original_visual_format')
    return list(dict.fromkeys(errors))


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value.replace('\\', '/'))
    return bool(value) and not path.is_absolute() and '..' not in path.parts and ':' not in value


def controlled_target(root: Path, relative: str) -> Path:
    if not safe_relative(relative):
        raise ValueError('asset target must be a controlled relative path')
    target = root / relative
    resolved = target.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError('asset target escapes root') from exc
    # Reject even an internal symlink: immutable paths cannot alias a writable file.
    # Ancestors outside root are not part of the asset contract (e.g. /tmp).
    if any((root / Path(*PurePosixPath(relative).parts[:i])).is_symlink()
           for i in range(1, len(PurePosixPath(relative).parts)+1)):
        raise ValueError('asset target contains a symlink')
    return target


def materialize_document_assets(book: CanonicalBook, *, source_root: str | Path,
                                progress_root: str | Path, figures_only: bool = False) -> CanonicalBook:
    from ingestion.document_adapters import (
        _controlled_source_path, _inspect_figure_image, _sha256_file, _atomic_copy,
        _append_review_status, _append_book_warning,
    )
    progress = Path(progress_root).resolve()
    document, _ = canonical_paths(book.book_name, progress_root=progress)
    book_root = controlled_target(progress, document.parent.name)
    for block in book.blocks:
        figure = block.block_type == 'figure'
        asset = block.attributes.get('original_visual_asset')
        if not figure and (figures_only or not isinstance(asset, dict)):
            continue
        attrs = block.attributes
        if figure:
            attrs.update(figure_id=block.block_id, caption=str(attrs.get('caption') or block.text).strip(),
                         page_idx=block.page_start-1 if block.page_start else None,
                         page_bbox=list(block.bbox or []))
            attrs.setdefault('bbox_space', 'page')
            attrs.setdefault('bbox_format', 'xyxy')
            attrs.setdefault('bbox_units', 'mineru_source_units')
        source_rel = str((attrs if figure else asset).get('source_asset_relpath' if figure else 'source_relpath') or '')
        source = _controlled_source_path(Path(source_root).resolve(), source_rel) if safe_relative(source_rel) else None
        # Only a validated, explicitly persisted asset may survive a moved/removed source.
        existing_rel = str((attrs if figure else asset).get('asset_relpath') or '')
        if source is None and safe_relative(existing_rel):
            source = _controlled_source_path(book_root, existing_rel)
        status = 'missing'
        try:
            if source is not None:
                width, height, suffix = _inspect_figure_image(source)
                digest = _sha256_file(source)
                if not re.fullmatch(r'[a-zA-Z0-9_-]+', block.block_id):
                    raise ValueError('unsafe block id for asset filename')
                relative = f"{'figures' if figure else 'original_visuals'}/{block.block_id}_{digest}{suffix}"
                target = controlled_target(book_root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and _sha256_file(target) != digest:
                    raise ValueError('immutable asset hash mismatch')
                if not target.exists():
                    _atomic_copy(source, target)
                if figure:
                    attrs.update(asset_relpath=relative, asset_status='ready', image_width=width,
                                 image_height=height, content_hash=digest)
                else:
                    asset.update(asset_relpath=relative, status='ready', width=width, height=height,
                                 sha256=digest, image_format=_FORMATS[suffix])
                continue
        except (OSError, ValueError) as exc:
            status = 'invalid'
            _append_book_warning(book, f"{'Figure' if figure else 'Original visual'} asset invalid: {block.block_id} ({exc})")
        if figure:
            attrs.update(asset_relpath='', asset_status=status, image_width=0, image_height=0, content_hash='')
        else:
            asset.update(asset_relpath='', status=status, width=0, height=0, sha256='', image_format='')
        _append_review_status(block, f"{status}_{'figure' if figure else 'original_visual'}_asset")
        if status == 'missing':
            _append_book_warning(book, f"{'Figure' if figure else 'Original visual'} asset missing: {block.block_id} ({source_rel or 'no path'})")
    return book
