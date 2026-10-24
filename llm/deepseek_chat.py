"""DeepSeek wire compatibility. Hidden protocol text never enters LC messages.

The scope belongs to one native run, not the cached client. Closing the shared
object also fences workers which still hold a copied ContextVar after timeout.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from threading import RLock
import logging
from typing import ClassVar

from langchain_openai import ChatOpenAI
from llm.request_failure import ProviderProtocolError, classify_provider_failure


class DeepSeekProtocolError(ProviderProtocolError):
    """Fixed codes only; never include provider bodies or private text."""


def _request_failed(exc):
    failure = classify_provider_failure(exc)
    logging.getLogger(__name__).warning("provider_request_failed category=%s http_status=%s",
                                        failure.category, failure.status)
    error = DeepSeekProtocolError("provider_request_failed")
    error.failure = failure
    return error


class PrivateProtocol:
    def __init__(self):
        self._lock = RLock()
        self._closed = False
        self._parts = []
        self._messages = {}
        self._bytes = 0
        self._seen = False

    def begin(self):
        with self._lock:
            if self._closed:
                raise DeepSeekProtocolError("provider_protocol_state_lost")
            self._parts.clear()
            self._seen = False

    def consume(self, value):
        with self._lock:
            if self._closed:
                raise DeepSeekProtocolError("provider_protocol_state_lost")
            if value is not None and not isinstance(value, str):
                raise DeepSeekProtocolError("provider_protocol_invalid")
            self._seen = True
            if value:
                self._bytes += len(value.encode("utf-8"))
                if self._bytes > 1024 * 1024:
                    raise DeepSeekProtocolError("provider_protocol_budget_exhausted")
                self._parts.append(value)

    def commit(self, message):
        with self._lock:
            if self._closed or not message.id:
                raise DeepSeekProtocolError("provider_protocol_state_lost")
            if message.tool_calls and not self._seen:
                raise DeepSeekProtocolError("provider_protocol_invalid")
            self._messages[message.id] = "".join(self._parts)
            self._parts.clear()

    def reasoning(self, message):
        with self._lock:
            if self._closed or message.id not in self._messages:
                raise DeepSeekProtocolError("provider_protocol_state_lost")
            return self._messages[message.id]

    def close(self):
        with self._lock:
            self._closed = True
            self._parts.clear()
            self._messages.clear()
            self._bytes = 0


_protocol: ContextVar[PrivateProtocol | None] = ContextVar("deepseek_native_protocol", default=None)


def _normalized_usage(raw):
    if not isinstance(raw, dict):
        return raw
    usage = dict(raw)
    cached = usage.get("prompt_cache_hit_tokens")
    if isinstance(cached, int) and cached >= 0:
        usage["prompt_tokens_details"] = {**(usage.get("prompt_tokens_details") or {}), "cached_tokens": cached}
    return usage


@contextmanager
def private_protocol_scope():
    state = PrivateProtocol()
    token = _protocol.set(state)
    try:
        yield state
    finally:
        state.close()
        _protocol.reset(token)


class DeepSeekChatOpenAI(ChatOpenAI):
    # Thinking shares the output allowance with public text. Keep the bounded
    # native allowance on this provider adapter; other providers retain 4096.
    native_output_token_limit: ClassVar[int] = 8192
    def native_protocol_scope(self):
        if (self.extra_body or {}).get("thinking", {}).get("type") == "disabled":
            return nullcontext(None)
        return private_protocol_scope()

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        if chunk.get("usage"):
            chunk = {**chunk, "usage": _normalized_usage(chunk["usage"])}
        state = _protocol.get()
        choices = chunk.get("choices") or []
        if state and choices:
            if len(choices) != 1 or choices[0].get("index", 0) != 0:
                raise DeepSeekProtocolError("provider_protocol_invalid")
            delta = choices[0].get("delta") or {}
            if "reasoning_content" in delta:
                state.consume(delta["reasoning_content"])
        # Base conversion intentionally drops reasoning before callbacks/streams.
        return super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)

    def _create_chat_result(self, response, generation_info=None):
        raw = response if isinstance(response, dict) else response.model_dump()
        state = _protocol.get()
        if state and raw.get("choices"):
            if len(raw["choices"]) != 1:
                raise DeepSeekProtocolError("provider_protocol_invalid")
            message = raw["choices"][0]["message"]
            if "reasoning_content" in message:
                state.consume(message["reasoning_content"])
        if raw.get("usage"):
            raw = {**raw, "usage": _normalized_usage(raw["usage"])}
        return super()._create_chat_result(raw, generation_info)

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if self._use_responses_api(payload) or payload.get("n", 1) != 1:
            raise DeepSeekProtocolError("provider_protocol_invalid")
        if _protocol.get() and logging.getLogger("openai._base_client").isEnabledFor(logging.DEBUG):
            raise DeepSeekProtocolError("provider_private_logging_enabled")
        # ChatOpenAI rewrites this OpenAI parameter; DeepSeek uses max_tokens.
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        thinking = (payload.get("extra_body") or {}).get("thinking", {})
        if payload.get("tools") and thinking.get("type", "enabled") != "disabled":
            from langchain_core.messages import AIMessage
            state = _protocol.get()
            for message, wire in zip(self._convert_input(input_).to_messages(), payload["messages"]):
                if isinstance(message, AIMessage):
                    if state is None:
                        raise DeepSeekProtocolError("provider_protocol_state_lost")
                    wire["reasoning_content"] = state.reasoning(message)
        return payload

    def _stream(self, *args, **kwargs):
        try:
            yield from super()._stream(*args, **kwargs)
        except DeepSeekProtocolError:
            raise
        except Exception as exc:
            # BaseChatModel dispatches on_llm_error after this boundary. Never
            # expose SDK exceptions which can include private wire bodies.
            raise _request_failed(exc) from None

    def _generate(self, *args, **kwargs):
        try:
            return super()._generate(*args, **kwargs)
        except DeepSeekProtocolError:
            raise
        except Exception as exc:
            raise _request_failed(exc) from None

    async def _astream(self, *args, **kwargs):
        try:
            async for chunk in super()._astream(*args, **kwargs):
                yield chunk
        except DeepSeekProtocolError:
            raise
        except Exception as exc:
            raise _request_failed(exc) from None

    async def _agenerate(self, *args, **kwargs):
        try:
            return await super()._agenerate(*args, **kwargs)
        except DeepSeekProtocolError:
            raise
        except Exception as exc:
            raise _request_failed(exc) from None
