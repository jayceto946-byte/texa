"""Real DeepSeek/OpenAI SDK wire replay with no network or user data."""
import asyncio
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from llm.deepseek_chat import DeepSeekChatOpenAI, DeepSeekProtocolError
from llm.request_failure import ProviderRequestFailure, classify_provider_failure, stream_visible_answer

PRIVATE = "PRIVATE_BODY_API_KEY_REASONING"


def text_response(text="完整讲解"):
    parts = [
        {"id": "wire", "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]},
        {"id": "wire", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          content="".join("data: " + json.dumps(p) + "\n\n" for p in parts) + "data: [DONE]\n\n")


def model(transport):
    return DeepSeekChatOpenAI(model="deepseek-flash", api_key="offline-test-key", max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(transport)))


@pytest.mark.parametrize("status,category,retryable", [
    (400, "invalid_request", False), (401, "authentication", False),
    (402, "payment", False), (403, "authentication", False),
    (404, "invalid_request", False), (429, "rate_limit", False),
    (500, "service_unavailable", True), (503, "service_unavailable", True),
])
def test_deepseek_retains_safe_cause_and_public_image_stream_error(status, category, retryable, caplog):
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": PRIVATE}})
    llm = model(transport)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProviderRequestFailure) as failed:
            list(stream_visible_answer(lambda **_: llm, "题干"))
    assert failed.value.failure.category == category
    assert failed.value.failure.status == status
    assert str(status) in str(failed.value)
    assert len(requests) == (2 if retryable else 1)
    assert PRIVATE not in caplog.text + str(failed.value)


@pytest.mark.parametrize("kind", ["service", "timeout", "connection"])
def test_transient_failure_recovers_once_before_answer(kind):
    calls = []
    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            if kind == "timeout":
                raise httpx.ReadTimeout(PRIVATE, request=request)
            if kind == "connection":
                raise httpx.ConnectError(PRIVATE, request=request)
            return httpx.Response(503, json={"error": {"message": PRIVATE}})
        return text_response()
    llm = model(transport)
    assert "".join(stream_visible_answer(lambda **_: llm, "题干")) == "完整讲解"
    assert len(calls) == 2


def test_stream_failure_after_visible_text_never_restarts_answer():
    calls = []
    closed = []
    def chunks():
        try:
            yield SimpleNamespace(content="已经开始的答案")
            raise httpx.ReadTimeout(PRIVATE)
        finally:
            closed.append(True)
    def factory(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stream=lambda _: chunks())
    stream = stream_visible_answer(factory, "题干")
    assert next(stream) == "已经开始的答案"
    with pytest.raises(ProviderRequestFailure, match="超时"):
        list(stream)
    assert len(calls) == 1 and closed == [True]


def test_stop_after_failed_request_prevents_another_request():
    active = [True]
    calls = []
    def transport(request):
        calls.append(request)
        active[0] = False
        return httpx.Response(503, json={"error": {"message": PRIVATE}})
    llm = model(transport)
    with pytest.raises(ProviderRequestFailure):
        list(stream_visible_answer(lambda **_: llm, "题干", can_retry=lambda: active[0]))
    assert len(calls) == 1


def test_retry_uses_remaining_timeout_and_filters_thinking(monkeypatch):
    from llm import request_failure
    ticks = iter([0, 0, 300])
    monkeypatch.setattr(request_failure.time, "monotonic", lambda: next(ticks))
    calls = []
    def factory(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError(PRIVATE)
        return SimpleNamespace(stream=lambda _: iter([SimpleNamespace(content="<think>PRIVATE</think>答案")]))
    assert "".join(stream_visible_answer(factory, "题干")) == "答案"
    assert [call["request_timeout"] for call in calls] == [420, 120]
    assert all(call["max_retries"] == 0 for call in calls)


def test_protocol_integrity_error_is_never_retried():
    calls = []
    def factory(**kwargs):
        calls.append(kwargs)
        raise DeepSeekProtocolError("provider_protocol_invalid")
    with pytest.raises(DeepSeekProtocolError, match="provider_protocol_invalid"):
        list(stream_visible_answer(factory, "题干"))
    assert len(calls) == 1


def test_stream_cleanup_failure_does_not_replace_delivered_answer(caplog):
    class Chunks:
        def __iter__(self):
            yield SimpleNamespace(content="已生成的答案")
        def close(self):
            raise httpx.ReadError(PRIVATE)
    assert "".join(stream_visible_answer(lambda **_: SimpleNamespace(stream=lambda _: Chunks()), "题干")) == "已生成的答案"
    assert "visual_answer_close_failed" in caplog.text and PRIVATE not in caplog.text


@pytest.mark.parametrize("streaming", [False, True])
def test_async_deepseek_preserves_classification_without_private_bodies(streaming, caplog):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(402, json={"error": {"message": PRIVATE}}),
        )) as client:
            llm = DeepSeekChatOpenAI(model="deepseek-flash", api_key="test", max_retries=0, http_async_client=client)
            with pytest.raises(DeepSeekProtocolError) as error:
                if streaming:
                    async for _ in llm.astream("题干"):
                        pass
                else:
                    await llm.ainvoke("题干")
            assert str(error.value) == "provider_request_failed"
            assert classify_provider_failure(error.value).category == "payment"
    asyncio.run(run())
    assert PRIVATE not in caplog.text


@pytest.mark.parametrize("failure", [False, True])
def test_image_sse_keeps_crop_for_vision_display_and_reload(monkeypatch, tmp_path, failure):
    from backend import conversation_memory as cm
    from backend.api import mistakes
    from backend.main import app
    from backend.services.multimodal_bridge import VisualProblemIR
    from tests.test_mistakes_api import _configure_visual_stream, _stream_events
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    original_stream = mistakes._iter_visual_solution_chunks
    _, tasks = _configure_visual_stream(monkeypatch, tmp_path, visual_ir=VisualProblemIR(problem_text="选择区域内的题目"))
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", original_stream)
    ocr_pixels = []
    def ocr(path, **kwargs):
        with Image.open(path) as image:
            ocr_pixels.append((image.size, image.getpixel((20, 20))))
        return VisualProblemIR(problem_text="选择区域内的题目")
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", ocr)
    attempts = []
    def transport(request):
        attempts.append(request)
        if failure:
            return httpx.Response(402, json={"error": {"message": PRIVATE}})
        if len(attempts) == 1:
            return httpx.Response(503, json={"error": {"message": PRIVATE}})
        return text_response()
    llm = model(transport)
    monkeypatch.setattr(mistakes, "_get_image_reasoning_llm", lambda **_: llm)
    def image_bytes(size, color):
        buf = io.BytesIO()
        Image.new("RGB", size, color).save(buf, format="PNG")
        return buf.getvalue()
    full = image_bytes((320, 240), "red")
    crop = image_bytes((120, 60), "blue")
    client = TestClient(app)
    response = client.post("/api/mistakes/solve-image-stream", files={
        "file": ("crop.png", crop, "image/png"), "original_file": ("full.png", full, "image/png"),
    }, data={"question": "请讲解裁剪的题目", "conversation_id": "crop", "turn_id": "turn"})
    events = _stream_events(response)
    task_id = events[-1]["execution_event"]["task_id"]
    task = tasks.get(task_id)
    assert task.status == ("failed" if failure else "completed")
    assert len(attempts) == (1 if failure else 2)
    assert ocr_pixels[0][0] == (120, 60) and ocr_pixels[0][1][2] > 240
    for suffix in ("", "?preview=true"):
        image = client.get(f"/api/mistakes/tasks/{task_id}/image" + suffix)
        assert image.status_code == 200
        assert image.headers["cache-control"] == "no-store"
        with Image.open(io.BytesIO(image.content)) as decoded:
            assert decoded.size == (120, 60) and decoded.getpixel((20, 20))[2] > 240
    assert client.get(f"/api/mistakes/tasks/{task_id}/image?original=true").content == full
    assert Path(task.artifacts["original_image_path"]).read_bytes() == full
    assert PRIVATE not in response.text
    if failure:
        assert "HTTP 402" in events[-1]["execution_event"]["summary"]
        assert task.artifacts["vision_pending"] is False
    else:
        history = cm.load_full_history("crop")
        assert [message["role"] for message in history] == ["user", "assistant"]
        url = history[0]["learning_task"]["artifacts"]["image_url"]
        with Image.open(io.BytesIO(client.get(url).content)) as reloaded:
            assert reloaded.size == (120, 60)


def test_missing_selected_image_does_not_silently_show_full_camera_frame(monkeypatch, tmp_path):
    from backend.api import mistakes
    from backend.main import app
    from backend.services.learning_task import LearningTaskStore
    from tests.test_mistake_image_lifecycle import _store
    store = _store(tmp_path)
    tasks = LearningTaskStore(tmp_path / "progress")
    original = store.image_root / "full.png"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"full frame")
    task = tasks.create(task_type="visual_qa", goal="题目", artifacts={
        "image_path": str(original.with_name("missing.png")), "original_image_path": str(original),
    })
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: tasks)
    client = TestClient(app)
    assert client.get(f"/api/mistakes/tasks/{task.id}/image").status_code == 404
    assert client.get(f"/api/mistakes/tasks/{task.id}/image?original=true").content == b"full frame"
