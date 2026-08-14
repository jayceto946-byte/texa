from pathlib import Path

import pytest

from scripts.validate_standard_release import scan_forbidden


@pytest.mark.parametrize(
    "relative",
    [
        "_internal/torch/__init__.pyc",
        "_internal/sentence_transformers/core.pyc",
        "_internal/transformers/model.pyc",
        "_internal/safetensors/_safetensors_rust.pyd",
        "_internal/c10.dll",
        "_internal/torch_cpu.dll",
        "_internal/cudart64_12.dll",
    ],
)
def test_forbidden_standard_runtime_paths_fail(relative, tmp_path):
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"runtime")
    expected = Path(relative).as_posix()
    if any(part in {"torch", "sentence_transformers", "transformers", "safetensors"} for part in Path(relative).parts):
        expected = "/".join(Path(relative).as_posix().split("/")[:2])
    assert scan_forbidden(tmp_path) == [expected]


def test_license_text_does_not_count_as_a_runtime_dependency(tmp_path):
    notice = tmp_path / "THIRD_PARTY_NOTICES" / "README.txt"
    notice.parent.mkdir(parents=True)
    notice.write_text("torch transformers safetensors sentence_transformers", encoding="utf-8")
    assert scan_forbidden(tmp_path) == []
