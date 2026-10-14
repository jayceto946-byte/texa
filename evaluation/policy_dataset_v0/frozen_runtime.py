"""Execute the reviewed offline V0.1 modules without replacing production imports.

Only fixed, hash-checked repository snapshots can be loaded. Private module names
keep dataclass/Pydantic identities separate from the live Runtime. No input may
select a source directory; unpinned application imports fail closed.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import sys
import threading
from pathlib import Path
from types import ModuleType

from .baseline import (
    APPROVED_RUNTIME_VERSION, APPROVED_SOURCE_MANIFEST, FROZEN_SOURCE_ROOT,
    RUNTIME_SOURCES, SOURCE_PATHS,
)

EVIDENCE_FUNCTION_HASH = "cdf2ce44cd54939b3f770c16f981bcf57b64463496c801947064bd950efbd270"
_PURE_MODULES = {
    path[:-3].replace("/", ".") for path in RUNTIME_SOURCES
    if "/agent_runtime/" not in path
}
_modules: dict[str, ModuleType] = {}
_lock = threading.RLock()


def _verified_sources():
    pins = json.loads(APPROVED_SOURCE_MANIFEST.read_text())
    identity = json.dumps({p: pins[p] for p in RUNTIME_SOURCES},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if "sha256:" + hashlib.sha256(identity.encode()).hexdigest() != APPROVED_RUNTIME_VERSION:
        raise ValueError("approved runtime digest mismatch")
    sources = {}
    for path in SOURCE_PATHS:
        raw = (FROZEN_SOURCE_ROOT / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pins[path]:
            raise ValueError("source_content_digest_mismatch")
        sources[path] = raw
    return sources


def _evidence_helper():
    path = Path(__file__).with_name("evidence_helper_v01.py")
    tree = ast.parse(path.read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "has_textbook_evidence")
    if hashlib.sha256(ast.dump(helper, include_attributes=False).encode()).hexdigest() != EVIDENCE_FUNCTION_HASH:
        raise ValueError("reviewed evidence helper changed")
    module = ModuleType("_texa_policy_v01_evidence")
    # Execute only the already pinned pure function, never surrounding code.
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(path), "exec"), module.__dict__)
    return module


def frozen_module(name: str) -> ModuleType:
    if name not in _PURE_MODULES:
        raise ValueError("unapproved frozen module")
    with _lock:
        sources = _verified_sources()  # Recheck even when a module is cached.
        return _load(name, sources)


def _load(name, sources):
    if name in _modules:
        return _modules[name]
    path = name.replace(".", "/") + ".py"
    private_name = "_texa_policy_v01_" + name.replace(".", "_")
    module = ModuleType(private_name)
    module.__file__ = str(FROZEN_SOURCE_ROOT / path)

    def import_snapshot(target, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and target in _PURE_MODULES and fromlist:
            return _load(target, sources)
        if level == 0 and target == "graph.generator" and fromlist == ("has_textbook_evidence",):
            return _evidence_helper()
        if target.split(".")[0] in {"backend", "graph", "config", "llm", "memory", "knowledge"}:
            raise ImportError("unpinned application import in frozen evaluation")
        return builtins.__import__(target, globals, locals, fromlist, level)

    module.__dict__["__builtins__"] = {**vars(builtins), "__import__": import_snapshot}
    _modules[name] = module
    sys.modules[private_name] = module
    try:
        exec(compile(sources[path], module.__file__, "exec"), module.__dict__)
    except BaseException:
        _modules.pop(name, None)
        sys.modules.pop(private_name, None)
        raise
    return module
