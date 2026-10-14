import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image

from backend.api import mistakes
from backend.services.mistake_images import MistakeImageStore
from backend.services.multimodal_bridge import VisualProblemIR


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


def _store(tmp_path, *, max_image_bytes=20 * 1024 * 1024):
    return MistakeImageStore(
        images_path=tmp_path / "images",
        allowed_extensions=frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"}),
        max_image_bytes=max_image_bytes,
        ocr_max_side=1600,
        ocr_jpeg_quality=86,
        pending_max_age_seconds=24 * 60 * 60,
    )


def test_uploaded_image_stays_pending_until_record_is_saved(tmp_path):
    store = _store(tmp_path)

    pending_path = store.save_upload(_upload("question.png", b"not-a-real-image"))
    assert pending_path.parent.name == "pending"
    assert pending_path.exists()

    committed_path, moved = store.commit_pending(str(pending_path))
    committed = Path(committed_path)
    assert moved is True
    assert committed.parent == tmp_path / "images" / "mistakes"
    assert committed.exists()
    assert not pending_path.exists()


def test_image_cleanup_is_confined_to_mistake_directory(tmp_path):
    store = _store(tmp_path)
    inside = tmp_path / "images" / "mistakes" / "inside.png"
    outside = tmp_path / "outside.png"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"inside")
    outside.write_bytes(b"outside")

    store.delete(inside)
    store.delete(outside)

    assert not inside.exists()
    assert outside.exists()


def test_recognition_failure_removes_pending_image(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(mistakes, "_image_store", store)

    def fail_ocr(_path, **_kwargs):
        raise RuntimeError("vision unavailable")

    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", fail_ocr)
    result = mistakes.recognize_mistake_image(_upload("failed.png", b"image"))

    assert result["success"] is False
    assert not any(store.pending_root.iterdir())


def test_recognition_returns_visual_ir(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(
        mistakes,
        "_ocr_image_with_kimi",
        lambda _path, **_kwargs: VisualProblemIR(
            problem_text="求电路输出",
            visual_type="circuit",
            relations=[{"type": "connected_to", "source": "R1", "target": "C1"}],
        ),
    )

    result = mistakes.recognize_mistake_image(_upload("circuit.png", b"image"))

    assert result["success"] is True
    assert result["ocr_text"] == "求电路输出"
    assert result["visual_ir"]["visual_type"] == "circuit"


def test_successful_optimization_replaces_raw_upload(tmp_path):
    raw = tmp_path / "sample_raw.png"
    Image.new("RGB", (32, 24), color="white").save(raw)

    store = _store(tmp_path)
    optimized = store.optimize_for_ocr(raw)

    assert optimized.name == "sample_ocr.jpg"
    assert optimized.exists()
    assert not raw.exists()


def test_upload_size_error_uses_configured_limit(tmp_path):
    store = _store(tmp_path, max_image_bytes=2 * 1024 * 1024)
    upload = _upload("large.png", b"x" * (2 * 1024 * 1024 + 1))

    with pytest.raises(ValueError, match="图片不能超过 2MB"):
        store.save_upload(upload)


def test_unexpected_optimization_failure_is_not_silenced(tmp_path, monkeypatch):
    raw = tmp_path / "sample_raw.png"
    raw.write_bytes(b"image")
    store = _store(tmp_path)

    def fail_open(_path):
        raise RuntimeError("bug")

    monkeypatch.setattr(Image, "open", fail_open)

    with pytest.raises(RuntimeError, match="bug"):
        store.optimize_for_ocr(raw)
    assert raw.exists()
