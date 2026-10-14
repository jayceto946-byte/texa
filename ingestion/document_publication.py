"""Candidate IR publication inside the existing index snapshot boundary.

This is additive per-book retention, not a migration of existing progress data.
Asset names are immutable; failed candidates never replace active IR files.
"""
from __future__ import annotations
from pathlib import Path
from ingestion.document_ir import canonical_paths, load_canonical_book, canonical_book_fingerprint
from ingestion.document_assets import controlled_target
from ingestion.document_adapters import _atomic_copy

_DOCUMENT_FILES = ('canonical_document.jsonl', 'ingestion_report.json',
                   'acceptance_probes.generated.jsonl', 'acceptance_probes.generated.report.json')
# Derived audits can change when rules/assets change without changing the IR.
# Publish/restore them with the candidate, but do not make them immutable IR
# snapshot contents. Retained rollback can regenerate the audit via the API.
_PUBLICATION_FILES = (*_DOCUMENT_FILES, 'figure_audit.json')


class CanonicalPublication:
    def __init__(self, book_name: str, *, candidate_root: Path, progress_root: Path):
        self.book_name = book_name
        self.progress_root = Path(progress_root).resolve()
        self.candidate_dir = canonical_paths(book_name, progress_root=candidate_root)[0].parent
        name = canonical_paths(book_name, progress_root=progress_root)[0].parent.name
        self.active_dir = controlled_target(self.progress_root, name)
        self.old_files: dict[str, bytes | None] = {}
        book = load_canonical_book(book_name, progress_root=candidate_root)
        self.canonical_hash = canonical_book_fingerprint(book)
        self.old_hash = ''
        self.started = False
        self.created_files: list[Path] = []
        self.created_directories: list[Path] = []

    def record(self) -> dict:
        return dict(canonical_hash=self.canonical_hash, canonical_snapshot=f'canonical_versions/{self.canonical_hash}',
                    canonical_progress_root=str(self.progress_root))

    def previous_record(self) -> dict:
        if not self.old_hash:
            return {}
        return dict(canonical_hash=self.old_hash, canonical_snapshot=f'canonical_versions/{self.old_hash}',
                    canonical_progress_root=str(self.progress_root))

    def _retain(self, source: Path, digest: str) -> None:
        directory = controlled_target(self.active_dir, f'canonical_versions/{digest}')
        if source == self.candidate_dir and not directory.exists():
            self.created_directories.append(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for name in _DOCUMENT_FILES:
            original = source / name
            if not original.is_file():
                continue
            target = controlled_target(self.active_dir, f'canonical_versions/{digest}/{name}')
            if target.exists():
                if target.read_bytes() != original.read_bytes():
                    raise ValueError('immutable Canonical snapshot differs for the same fingerprint')
            else:
                _atomic_copy(original, target)
                if source == self.candidate_dir:
                    self.created_files.append(target)

    def publish(self) -> None:
        """Caller must own index_publication; readers cannot observe these writes."""
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.old_files = {name: (self.active_dir / name).read_bytes() if (self.active_dir / name).is_file() else None
                          for name in _PUBLICATION_FILES}
        if self.old_files['canonical_document.jsonl'] is not None:
            # Read directly while owning the publication lock (no nested snapshot).
            from ingestion.document_ir import _load_canonical_book
            previous = _load_canonical_book(self.book_name, progress_root=self.progress_root)
            self.old_hash = canonical_book_fingerprint(previous)
            self._retain(self.active_dir, self.old_hash)
        self._retain(self.candidate_dir, self.canonical_hash)
        # Copy new immutable crops first. Existing readers' paths remain valid.
        for directory_name in ('figures', 'original_visuals'):
            directory = self.candidate_dir / directory_name
            if not directory.exists():
                continue
            for source in directory.iterdir():
                target = controlled_target(self.active_dir, f'{directory_name}/{source.name}')
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != source.read_bytes():
                    raise ValueError('immutable document asset differs')
                if not target.exists():
                    _atomic_copy(source, target)
                    self.created_files.append(target)
        self.started = True
        for name in _PUBLICATION_FILES:
            source = self.candidate_dir / name
            if source.is_file():
                _atomic_copy(source, controlled_target(self.active_dir, name))
            else:
                (self.active_dir / name).unlink(missing_ok=True)

    def restore(self) -> None:
        from ingestion.index_pipeline import _atomic_write_bytes
        if self.started:
            for name, value in self.old_files.items():
                target = self.active_dir / name
                if value is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(target, value)
        for path in self.created_files:
            path.unlink(missing_ok=True)
        for directory in reversed(self.created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        self.created_files.clear()
        self.created_directories.clear()
        self.started = False


def retained_publication(book_name: str, record: dict) -> CanonicalPublication | None:
    relative = record.get('canonical_snapshot')
    root = record.get('canonical_progress_root')
    if not relative or not root:
        return None
    active = canonical_paths(book_name, progress_root=root)[0].parent
    retained = controlled_target(active, relative)
    # Constructor takes a progress root containing a book directory. A small
    # object override reuses publication logic without copying the retained IR.
    result = object.__new__(CanonicalPublication)
    result.book_name = book_name
    result.progress_root = Path(root).resolve()
    result.candidate_dir = retained
    result.active_dir = active
    result.old_files = {}
    result.canonical_hash = str(record.get('canonical_hash') or '')
    result.old_hash = ''
    result.started = False
    result.created_files = []
    result.created_directories = []
    if not (retained / 'canonical_document.jsonl').is_file():
        raise RuntimeError('retained Canonical snapshot is unavailable')
    return result
