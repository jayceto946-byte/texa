"""Opt-in synchronous Chat Completions diagnostics; no network runner or credentials.

Install hooks on a dedicated httpx.Client, then use DiagnosticChatOpenAI with
the same model options/tools. Nothing imports this module in production.
T2 is the SDK-decoded provider delta before LangChain conversion, NOT a wire read.
"""
from contextvars import ContextVar
import time
from typing import Any
from pydantic import PrivateAttr
from langchain_openai import ChatOpenAI
from utils.thinking_filter import ThinkingFilter

_current = ContextVar("texa_stream_diagnostic", default=None)


class StreamTimingProbe:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.records = []

    def begin(self):
        record = {"request_index": len(self.records) + 1,
                  "times_ms": {f"T{i}": None for i in range(7)},
                  "sdk_delta_count": 0, "reasoning_delta_count": 0,
                  "public_delta_count": 0, "max_sdk_gap_ms": None,
                  "max_reasoning_gap_ms": None, "usage": {},
                  "finish_reason": None, "http_status": None,
                  "complete_consumption": False, "termination": "running"}
        self.records.append(record)
        # Private observation state is never serialized; filter retains only
        # incomplete markup, not reasoning_content. Delta text is never retained.
        return {"probe": self, "record": record, "origin": self.clock(),
                "filter": ThinkingFilter(), "last_delta": None, "last_reasoning": None,
                "last_reasoning_ms": None}

    def stamp(self, state):
        return round((self.clock() - state["origin"]) * 1000, 3)

    def request_hook(self, request):
        state = _current.get()
        if not state or state["probe"] is not self:
            return
        previous = request.extensions.get("trace")

        def trace(name, info):
            # httpcore starts sending request headers. Does not assert bytes
            # reached the wire/server. DNS/connect/TLS can precede this marker.
            if name.endswith(".send_request_headers.started"):
                times = state["record"]["times_ms"]
                if times["T0"] is None:
                    times["T0"] = self.stamp(state)
            if previous:
                previous(name, info)
        request.extensions["trace"] = trace

    def response_hook(self, response):
        state = _current.get()
        if state and state["probe"] is self:
            record = state["record"]
            record["times_ms"]["T1"] = self.stamp(state)
            record["http_status"] = response.status_code

    def observe(self, state, chunk, generation, now):
        record = state["record"]
        if record["times_ms"]["T2"] is None:
            record["times_ms"]["T2"] = now
        record["sdk_delta_count"] += 1
        if state["last_delta"] is not None:
            record["max_sdk_gap_ms"] = max(record["max_sdk_gap_ms"] or 0, now - state["last_delta"])
        state["last_delta"] = now
        choices = chunk.get("choices") or []
        if choices:
            choice = choices[0]
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                record["reasoning_delta_count"] += 1
                if record["times_ms"]["T3"] is None:
                    record["times_ms"]["T3"] = now
                if state["last_reasoning"] is not None:
                    record["max_reasoning_gap_ms"] = max(record["max_reasoning_gap_ms"] or 0, now - state["last_reasoning"])
                state["last_reasoning"] = now
                state["last_reasoning_ms"] = now
            finish = choice.get("finish_reason")
            if finish in {"stop", "tool_calls", "length", "content_filter", "function_call"}:
                record["finish_reason"] = finish
        usage = chunk.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if type(usage.get(key)) is int and usage[key] >= 0:
                record["usage"][key] = usage[key]
        details = usage.get("completion_tokens_details") or {}
        if type(details.get("reasoning_tokens")) is int and details["reasoning_tokens"] >= 0:
            record["usage"]["reasoning_tokens"] = details["reasoning_tokens"]
        content = getattr(getattr(generation, "message", None), "content", None)
        if isinstance(content, str) and state["filter"].filter(content).strip():
            record["public_delta_count"] += 1
            if record["times_ms"]["T5"] is None:
                record["times_ms"]["T5"] = self.stamp(state)

    def end(self, state, termination, complete=False):
        record = state["record"]
        record["times_ms"]["T6"] = self.stamp(state)
        record["complete_consumption"] = complete
        record["termination"] = termination
        # A cancelled/error stream cannot establish the LAST reasoning delta.
        if complete:
            record["times_ms"]["T4"] = state["last_reasoning_ms"]


class DiagnosticChatOpenAI(ChatOpenAI):
    _timing_probe: Any = PrivateAttr()

    def __init__(self, *, timing_probe, **kwargs):
        super().__init__(**kwargs)
        self._timing_probe = timing_probe

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        state = _current.get()
        now = self._timing_probe.stamp(state) if state and state["probe"] is self._timing_probe else None
        generation = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if state and state["probe"] is self._timing_probe:
            self._timing_probe.observe(state, chunk, generation, now)
        return generation

    def _stream(self, *args, **kwargs):
        state = self._timing_probe.begin()
        token = _current.set(state)
        try:
            yield from super()._stream(*args, **kwargs)
        except GeneratorExit:
            self._timing_probe.end(state, "consumer_closed")
            raise
        except BaseException as error:
            names = set()
            cause = error
            for _ in range(5):
                if cause is None:
                    break
                names.add(type(cause).__name__)
                cause = cause.__cause__ or cause.__context__
            termination = "timeout" if names & {"APITimeoutError", "ReadTimeout", "TimeoutError"} else "cancelled" if "RuntimeConflict" in names else "connection_failure" if names & {"APIConnectionError", "ConnectError"} else "stream_error"
            self._timing_probe.end(state, termination)
            raise
        else:
            finish = state["record"]["finish_reason"]
            termination = ("protocol_incomplete" if finish is None else
                           "tool_handoff" if finish == "tool_calls" else
                           "truncated" if finish == "length" else
                           "provider_filtered" if finish == "content_filter" else "completed")
            self._timing_probe.end(state, termination, finish is not None)
        finally:
            _current.reset(token)
