"""Offline SDK/SSE tests. All HTTP is MockTransport; no credentials/network."""
import importlib.util
import json
from pathlib import Path
import httpx
import pytest

spec = importlib.util.spec_from_file_location("provider_timing", Path(__file__).parents[1] / "scripts/diagnostics/provider_stream_timing.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Bytes(httpx.SyncByteStream):
    def __init__(self, frames, fail=None):
        self.frames, self.fail = frames, fail

    def __iter__(self):
        for frame in self.frames:
            yield ("data: " + json.dumps(frame) + "\n\n").encode()
        if self.fail:
            raise self.fail
        yield b"data: [DONE]\n\n"


def frame(delta, finish=None):
    return {"id": "fixture", "object": "chat.completion.chunk", "created": 1,
            "model": "fixture", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def model(frames, fail=None, trace=False):
    probe = module.StreamTimingProbe()
    def handle(request):
        if trace:
            request.extensions["trace"]("http11.send_request_headers.started", {})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Bytes(frames, fail))
    client = httpx.Client(transport=httpx.MockTransport(handle), event_hooks={"request": [probe.request_hook], "response": [probe.response_hook]})
    return module.DiagnosticChatOpenAI(timing_probe=probe, model="fixture", api_key="fixture-local-only", base_url="https://offline.invalid/v1", http_client=client, max_retries=0, stream_usage=True), probe, client


def test_interleaved_reasoning_preserves_content_and_native_calls():
    secret = "PRIVATE_REASONING_NEVER_SAVE"
    frames = [frame({"role": "assistant", "content": ""}), frame({"reasoning_content": secret}),
              frame({"content": "<thi"}), frame({"content": "nk>filtered</think>公开"}),
              frame({"reasoning_content": secret}),
              frame({"tool_calls": [{"index": 0, "id": "call1", "type": "function", "function": {"name": "symbolic_math", "arguments": "{}"}}]}, "tool_calls"),
              {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 5}}}]
    m, p, client = model(frames, trace=True)
    try:
        bound = m.bind_tools([{"name": "symbolic_math", "description": "fixture", "parameters": {"type": "object", "properties": {}}}])
        for _ in range(2):
            chunks = list(bound.stream("fixture"))
            combined = chunks[0]
            for c in chunks[1:]: combined += c
            assert combined.tool_calls[0]["id"] == "call1"
            assert combined.content == "<think>filtered</think>公开"
        assert len(p.records) == 2
        for r in p.records:
            assert r["times_ms"]["T3"] <= r["times_ms"]["T5"] <= r["times_ms"]["T4"]
            assert all(v is not None for v in r["times_ms"].values())
            assert r["reasoning_delta_count"] == 2
            assert r["sdk_delta_count"] == 7
            assert r["termination"] == "tool_handoff"
            assert r["usage"]["reasoning_tokens"] == 5
        saved = json.dumps(p.records)
        assert secret not in saved and "filtered" not in saved and "公开" not in saved
    finally: client.close()


def test_missing_reasoning_and_transport_trace_are_null():
    m, p, client = model([frame({"content": "answer"}, "stop")])
    try:
        list(m.stream("fixture"))
        r = p.records[0]
        assert r["times_ms"]["T0"] is None
        assert r["times_ms"]["T3"] is None and r["times_ms"]["T4"] is None
        assert r["complete_consumption"] and r["termination"] == "completed"
    finally: client.close()


@pytest.mark.parametrize("fail,termination", [(httpx.ReadTimeout("private error"), "timeout"), (httpx.ConnectError("private error"), "connection_failure")])
def test_partial_error_does_not_establish_last_reasoning(fail, termination):
    m, p, client = model([frame({"reasoning_content": "secret"})], fail=fail)
    try:
        with pytest.raises(Exception): list(m.stream("fixture"))
        r = p.records[0]
        assert r["times_ms"]["T3"] is not None and r["times_ms"]["T4"] is None
        assert r["termination"] == termination and not r["complete_consumption"]
        assert "secret" not in json.dumps(r) and "private error" not in json.dumps(r)
    finally: client.close()


def test_consumer_close_and_truncation():
    m, p, client = model([frame({"reasoning_content": "secret"}), frame({"content": "a"}, "length")])
    try:
        stream = m.stream("fixture")
        next(stream)
        stream.close()
        assert p.records[0]["termination"] == "consumer_closed"
        assert p.records[0]["times_ms"]["T4"] is None
        list(m.stream("fixture"))
        assert p.records[1]["termination"] == "truncated"
    finally: client.close()


def test_exact_gaps_and_first_public_can_precede_reasoning():
    values = iter([0, 1, 2, 12, 15])
    p = module.StreamTimingProbe(clock=lambda: next(values))
    state = p.begin()
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk
    p.observe(state, frame({"content": "a"}), ChatGenerationChunk(message=AIMessageChunk(content="a")), 1000)
    p.observe(state, frame({"reasoning_content": "secret"}), None, 2000)
    p.observe(state, frame({"reasoning_content": "secret"}), None, 12000)
    p.end(state, "completed", True)
    r = p.records[0]
    assert r["times_ms"]["T5"] < r["times_ms"]["T3"]
    assert r["max_sdk_gap_ms"] == 10000 and r["max_reasoning_gap_ms"] == 10000


def test_eof_without_terminal_finish_is_not_full_completion():
    m, p, client = model([frame({"reasoning_content": "secret"})])
    try:
        list(m.stream("fixture"))
        assert p.records[0]["termination"] == "protocol_incomplete"
        assert p.records[0]["times_ms"]["T4"] is None
        assert not p.records[0]["complete_consumption"]
    finally: client.close()
