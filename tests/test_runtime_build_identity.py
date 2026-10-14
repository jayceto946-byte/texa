from backend import runtime_identity


def test_process_identity_is_frozen_and_served_shell_is_read_at_request(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_identity, '_ROOT', tmp_path)
    directory = tmp_path / 'frontend' / 'dist'
    directory.mkdir(parents=True)
    shell = directory / 'index.html'
    shell.write_text('<meta name="texa-build" content="first-build">')
    first = runtime_identity.runtime_build_identity()
    shell.write_text('<meta name="texa-build" content="second-build">')
    second = runtime_identity.runtime_build_identity()
    assert first['source_at_import'] == second['source_at_import']
    assert first['served_frontend']['build'] == 'first-build'
    assert second['served_frontend']['build'] == 'second-build'
    assert first['served_frontend']['shell_sha256'] != second['served_frontend']['shell_sha256']
    first['source_at_import']['revision'] = 'mutated'
    assert runtime_identity.runtime_build_identity()['source_at_import']['revision'] != 'mutated'
    shell.unlink()
    assert runtime_identity.runtime_build_identity()['served_frontend']['build'] == 'unknown'
