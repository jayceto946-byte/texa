from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest

from utils.path_safety import _resolved_within_root, safe_child_path


@pytest.mark.parametrize('root,candidate,allowed', [
    ('C:/study', '//?/C:/study/default/concept_memory.json', True),
    ('//?/C:/study', 'c:/STUDY/default/concept_memory.json', True),
    ('C:/study', '//?/C:/study', True),
    ('//server/share/study', '//?/UNC/server/share/study/default/data.json', True),
    ('//?/UNC/server/share/study', '//SERVER/SHARE/study/default/data.json', True),
    ('C:/study', '//?/C:/study-other/data.json', False),
    ('C:/study', '//?/D:/study/data.json', False),
    ('//server/share/study', '//?/UNC/other/share/study/data.json', False),
    ('//server/share/study', '//?/UNC/server/other/study/data.json', False),
])
def test_windows_resolved_aliases_preserve_containment(root, candidate, allowed):
    assert _resolved_within_root(PureWindowsPath(root), PureWindowsPath(candidate)) is allowed


def test_safe_child_path_still_rejects_parent_and_absolute_escape(tmp_path):
    root = tmp_path / 'data'
    root.mkdir()
    assert safe_child_path(root, 'default', 'memory.json') == root / 'default/memory.json'
    assert safe_child_path(root) == root
    with pytest.raises(ValueError, match='escapes root'):
        safe_child_path(root, '..', 'outside.json')
    with pytest.raises(ValueError, match='escapes root'):
        safe_child_path(root, tmp_path / 'outside.json')


def test_safe_child_path_resolves_symlinks_before_containment(tmp_path):
    root = tmp_path / 'data'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    try:
        (root / 'link').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('This host cannot create a symlink')
    with pytest.raises(ValueError, match='escapes root'):
        safe_child_path(root, 'link', 'memory.json')


@pytest.mark.parametrize('plain,extended', [
    ('C:/_texa_alias_contract/data.json', '//?/C:/_texa_alias_contract/data.json'),
    ('//server/share/_texa_alias_contract/data.json', '//?/UNC/server/share/_texa_alias_contract/data.json'),
])
def test_equivalent_windows_realpaths_share_the_same_state_lock(monkeypatch, plain, extended):
    import utils.path_safety as safety
    from utils.state_locks import get_state_lock
    # Emulate the two resolved spellings actually returned by Windows on any host.
    monkeypatch.setattr(safety, 'Path', lambda value: SimpleNamespace(resolve=lambda: PureWindowsPath(value)))
    assert get_state_lock(plain) is get_state_lock(extended)
    assert get_state_lock(plain) is not get_state_lock(plain + '.other')
