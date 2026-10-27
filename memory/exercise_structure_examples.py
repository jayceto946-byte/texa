"""Explicit, local, versioned examples of source-backed solution boundaries.

Only literal labels are reused. Saving never trains a model, rewrites an import,
or promotes generated output to a gold answer. Profiles are immutable for replay.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import threading

from utils.json_io import atomic_write_json

_lock = threading.RLock()
LABEL = re.compile(r'^\s*(?:[【\[]\s*)?([\u4e00-\u9fff]{1,12})\s*(?:[】\]][：:]?|[：:])')


class StructureExampleStore:
    def __init__(self, progress_root):
        self.root = Path(progress_root) / 'exercise_structure_examples'

    def load(self, version=None):
        if version is None:
            pointer = self.root / 'current.json'
            if not pointer.exists():
                return '', []
            version = json.loads(pointer.read_text())['version']
        if not version:
            return '', []
        if not re.fullmatch(r'[a-f0-9]{64}', version):
            raise ValueError('结构样例版本无效')
        path = self.root / f'{version}.json'
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != version:
            raise ValueError('结构样例版本校验失败')
        payload = json.loads(raw)
        rules = payload['rules']
        if len(rules) > 100 or any(not re.fullmatch(r'[\u4e00-\u9fff]{1,12}', r['label']) or r['role'] not in ('answer', 'explanation') for r in rules):
            raise ValueError('结构样例超出受限合同')
        return version, rules

    @contextmanager
    def _writing(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with _lock, (self.root / '.lock').open('a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                handle.write(b'0')
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def save(self, *, projection, registry):
        rules = []
        for role in ('answer', 'explanation'):
            for span in projection['parts'][role]:
                text = registry[span['block_id']]['text'][span['start']:span['end']]
                match = LABEL.match(text)
                if match:
                    from memory.exercise_structure import LABEL_ROLES
                    if match[1] in LABEL_ROLES and LABEL_ROLES[match[1]] != role:
                        raise ValueError('标准解答标题不能保存为冲突角色')
                    rules.append(dict(label=match[1], role=role))
        if not rules:
            raise ValueError('请先在原文中标出带明确标题的答案或解析起点，再确认本题结构')
        with self._writing():
            _, previous = self.load()
            by_label = {r['label']: r for r in previous}
            for rule in rules:
                if rule['label'] in by_label and by_label[rule['label']]['role'] != rule['role']:
                    raise ValueError('该标题已有不同角色的样例，请保留本题人工校对，不能自动推广')
                by_label[rule['label']] = rule
            if len(by_label) > 100:
                raise ValueError('样例标题达到预算，请先整理已有样例')
            payload = dict(version=1, rules=sorted(by_label.values(), key=lambda r: r['label']))
            raw = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode()
            version = hashlib.sha256(raw).hexdigest()
            target = self.root / f'{version}.json'
            if not target.exists():
                # A profile is invisible until the atomically written pointer is published.
                atomic_write_json(target, payload)
            if target.read_bytes() != raw:
                raise ValueError('结构样例版本已损坏，请保留当前候选并检查本地样例')
            receipt = dict(canonical_hash=projection['canonical_hash'], unit_ids=projection['unit_ids'],
                           parts=projection['parts'], rules=rules, profile_version=version)
            digest = hashlib.sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            atomic_write_json(self.root / 'confirmed' / f'{digest}.json', receipt)
            atomic_write_json(self.root / 'current.json', dict(version=version))
            return dict(profile_version=version, labels=sorted({r['label'] for r in rules}))
