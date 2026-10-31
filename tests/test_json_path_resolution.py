"""Model Windows realpath's exclusive handle during concurrent JSON publication."""
import json
import threading
from pathlib import Path

import pytest

from utils import json_io, path_safety
from utils.state_locks import get_state_lock


@pytest.mark.parametrize('lookup', ['safe_child', 'state_lock'])
def test_path_lookup_cannot_block_concurrent_json_replacement(tmp_path, monkeypatch, lookup):
    target = tmp_path / 'state.json'
    json_io.atomic_write_json(target, {'count': 1})
    metadata_open, release_metadata = threading.Event(), threading.Event()
    staged, finished = threading.Event(), threading.Event()
    failures = []
    resolve, replace, fsync = Path.resolve, json_io.os.replace, json_io.os.fsync

    def resolve_with_windows_handle(path, *args, **kwargs):
        if path == target:
            metadata_open.set()
            try:
                assert release_metadata.wait(3), 'path lookup was not released'
            finally:
                metadata_open.clear()
        return resolve(path, *args, **kwargs)

    def replace_with_windows_sharing(source, destination):
        if metadata_open.is_set():
            raise PermissionError('Windows path lookup still owns the destination handle')
        return replace(source, destination)

    def staging_complete(fd):
        fsync(fd)
        staged.set()

    def run(function, *, writer=False):
        try:
            function()
        except BaseException as exc:
            failures.append(exc)
        finally:
            if writer:
                finished.set()

    monkeypatch.setattr(Path, 'resolve', resolve_with_windows_handle)
    monkeypatch.setattr(json_io.os, 'replace', replace_with_windows_sharing)
    monkeypatch.setattr(json_io.os, 'fsync', staging_complete)
    lookup_path = (lambda: path_safety.safe_child_path(tmp_path, target.name)) if lookup == 'safe_child' else (lambda: get_state_lock(target))
    reader = threading.Thread(target=run, args=(lookup_path,))
    writer = threading.Thread(target=run, args=(lambda: json_io.atomic_write_json(target, {'count': 2}),), kwargs={'writer': True})
    reader.start()
    try:
        assert metadata_open.wait(2)
        writer.start()
        assert staged.wait(2)
        assert not finished.wait(.1), 'replacement raced the open Windows metadata handle'
    finally:
        release_metadata.set()
        reader.join(3)
        if writer.ident is not None:
            writer.join(3)
    assert not reader.is_alive() and not writer.is_alive()
    assert not failures
    assert json.loads(target.read_text(encoding='utf-8')) == {'count': 2}
    assert not list(tmp_path.glob('*.tmp'))
