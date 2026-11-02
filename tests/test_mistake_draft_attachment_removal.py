"""Image detachment must preserve edited text and accepted mistake snapshots."""
import pytest

from backend.services.mistake_lifecycle import remove_draft_attachment
from backend.api import mistake_lifecycle as api
from memory.mistake_book import MistakeBookStore
from memory.mistake_lifecycle import MistakeLifecycleStore


def test_detach_image_keeps_edits_and_remaining_image_on_save(tmp_path, monkeypatch):
    store = MistakeBookStore(tmp_path / "mistakes.db")
    lifecycle = MistakeLifecycleStore(store)
    paths = [tmp_path / "note.png", tmp_path / "question.png"]
    for path in paths:
        path.write_bytes(b"synthetic image")
    attachments = [{"id": str(i), "filename": path.name, "original_path": str(path), "work_path": str(path)} for i, path in enumerate(paths)]
    draft = lifecycle.create_draft({"question_text": "已手动修正的题干", "user_answer": "已写作答", "content_complete": True, "attachments": attachments, "image_path": str(paths[0])})
    with pytest.raises(ValueError, match="revision changed"):
        remove_draft_attachment(lifecycle, draft["id"], "0", expected_revision=2)
    assert lifecycle.get_draft(draft["id"])["attachments"] == attachments
    monkeypatch.setattr(api, "_store", lambda _book_name: lifecycle)
    updated = api.detach_draft_attachment(draft["id"], "0", api.DraftAttachmentRemove(expected_revision=1))["data"]
    assert updated["revision"] == 2
    assert updated["question_text"] == draft["question_text"]
    assert updated["user_answer"] == draft["user_answer"]
    assert updated["attachments"] == attachments[1:]
    assert updated["image_path"] == str(paths[1])
    receipt = api.save_draft(draft["id"], api.DraftSave(expected_revision=2, operation_id="save"))["data"]
    record = store.get(receipt["mistake_id"])
    assert record.attachments == attachments[1:]
    assert record.image_path == str(paths[1])
    with pytest.raises(ValueError, match="已保存为正式错题"):
        remove_draft_attachment(lifecycle, draft["id"], "1", expected_revision=2)
    assert store.get(record.id).attachments == attachments[1:]
    assert all(path.exists() for path in paths)


def test_remove_last_image_does_not_restore_it_as_primary_image(tmp_path):
    lifecycle = MistakeLifecycleStore(MistakeBookStore(tmp_path / "draft.db"))
    draft = lifecycle.create_draft({"question_text": "保留题干", "content_complete": True, "attachments": [{"id": "a", "original_path": "draft/figure.png"}], "image_path": "draft/figure.png"})
    updated = remove_draft_attachment(lifecycle, draft["id"], "a", expected_revision=1)
    assert updated["attachments"] == []
    assert updated["image_path"] == ""
    with pytest.raises(ValueError, match="attachment not found"):
        remove_draft_attachment(lifecycle, draft["id"], "missing", expected_revision=2)
