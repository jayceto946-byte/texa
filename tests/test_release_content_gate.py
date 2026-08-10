import hashlib
import json

import pytest

from scripts.check_release_content import check


def test_release_content_gate_accepts_empty_sample_directory(tmp_path):
    assert check(tmp_path) == []


def test_release_content_gate_rejects_undeclared_file(tmp_path):
    (tmp_path / "book.pdf").write_bytes(b"pdf")
    (tmp_path / "content-manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": []}), encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="undeclared"):
        check(tmp_path)


def test_release_content_gate_verifies_license_and_checksum(tmp_path):
    content = b"licensed-demo"
    (tmp_path / "demo.bin").write_bytes(content)
    (tmp_path / "content-manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "files": [{
            "path": "demo.bin",
            "source": "https://example.invalid/demo",
            "license": "CC0-1.0",
            "redistributable": True,
            "sha256": hashlib.sha256(content).hexdigest(),
        }],
    }), encoding="utf-8")

    assert check(tmp_path) == ["demo.bin"]
