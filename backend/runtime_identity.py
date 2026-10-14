"""Read-only process/build evidence. Capture source identity once, not live HEAD per request."""
import hashlib
import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

def _capture_source():
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=_ROOT, stderr=subprocess.DEVNULL, timeout=2).decode().strip()
        diff = subprocess.check_output(['git', 'diff', 'HEAD', '--', 'backend', 'graph', 'llm', 'memory', 'config.py'], cwd=_ROOT, stderr=subprocess.DEVNULL, timeout=2)
        return {'revision': revision, 'tracked_dirty': bool(diff), 'tracked_diff_sha256': hashlib.sha256(diff).hexdigest()}
    except (OSError, subprocess.SubprocessError):
        return {'revision': 'unknown', 'tracked_dirty': None, 'tracked_diff_sha256': None}

_SOURCE = _capture_source()
try:
    _backend_hash = hashlib.sha256()
    for _file in sorted((_ROOT / 'backend').rglob('*.py')):
        if _file.is_symlink():
            continue
        _backend_hash.update(str(_file.relative_to(_ROOT)).encode())
        _backend_hash.update(_file.read_bytes())
    _SOURCE['backend_python_sha256'] = _backend_hash.hexdigest()
except OSError:
    _SOURCE['backend_python_sha256'] = None

def runtime_build_identity():
    # This is the shell currently served from disk, not evidence that a phone has refreshed it.
    try:
        shell = (_ROOT / 'frontend' / 'dist' / 'index.html').read_bytes()
        match = re.search(rb'<meta\s+name="texa-build"\s+content="([^"]+)"', shell)
        frontend = {'build': match.group(1).decode() if match else 'unknown', 'shell_sha256': hashlib.sha256(shell).hexdigest()}
    except OSError:
        frontend = {'build': 'unknown', 'shell_sha256': None}
    return {'source_at_import': dict(_SOURCE), 'served_frontend': frontend}
