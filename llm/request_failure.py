"""Closed, body-free provider diagnostics and bounded text-stream recovery."""
from dataclasses import dataclass
import logging
import time

import httpx
from openai import APIConnectionError, APITimeoutError

from utils.thinking_filter import ThinkingFilter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderFailure:
    category: str
    message: str
    retryable: bool = False
    status: int | None = None


class ProviderRequestFailure(RuntimeError):
    def __init__(self, failure: ProviderFailure):
        self.failure = failure
        super().__init__(failure.message)


class ProviderProtocolError(ValueError):
    """Non-transport protocol failures must never trigger request recovery."""


def classify_provider_failure(exc: Exception) -> ProviderFailure:
    """Inspect only types and HTTP status, never exception/body/header text."""
    saved = getattr(exc, "failure", None)
    if isinstance(saved, ProviderFailure):
        return saved
    if isinstance(exc, (APITimeoutError, httpx.TimeoutException, TimeoutError)):
        return ProviderFailure("timeout", "模型服务响应超时，请稍后重试。", True)
    if isinstance(exc, (APIConnectionError, httpx.NetworkError, httpx.RemoteProtocolError)):
        return ProviderFailure("connection", "无法连接模型服务，请检查桌面主机的网络或代理后重试。", True)
    status = getattr(exc, "status_code", None)
    if status is None and isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    status = status if type(status) is int and 400 <= status <= 599 else None
    if status in {401, 403}:
        return ProviderFailure("authentication", f"模型服务认证或权限校验失败（HTTP {status}），请检查模型设置中的 API Key 和访问权限。", status=status)
    if status == 402:
        return ProviderFailure("payment", "模型服务账户余额或额度不足（HTTP 402），请检查账户后重试。", status=status)
    if status == 429:
        return ProviderFailure("rate_limit", "模型服务限流或额度受限（HTTP 429），请稍后重试并检查账户额度。", status=status)
    if status in {408, 500, 502, 503, 504}:
        return ProviderFailure("service_unavailable", f"模型服务暂时不可用（HTTP {status}），请稍后重试。", True, status)
    if status in {400, 404, 413, 422}:
        return ProviderFailure("invalid_request", f"模型服务拒绝请求（HTTP {status}），请检查模型名称、接口地址与参数配置。", status=status)
    return ProviderFailure("request_failed", "模型请求未能完成，请检查模型连接后重试。", status=status)


def stream_visible_answer(model_factory, prompt, *, timeout=420, can_retry=None):
    """Retry a transient failure once, only before any visible answer escapes.

    The caller owns the turn/run and supplies its current ownership check. Never
    replay a partial answer, change model roles, or retry authentication errors.
    """
    deadline = time.monotonic() + timeout
    visible = False
    last_failure = ProviderFailure("timeout", "模型服务响应超时，请稍后重试。")
    for attempt in range(2):
        # Factory cache keys include timeout; do not create a new cached HTTP
        # client for every microsecond difference between otherwise equal runs.
        remaining = int(deadline - time.monotonic())
        if remaining < 1 or (can_retry is not None and not can_retry()):
            break
        provider = None
        thinking = ThinkingFilter()
        try:
            provider = model_factory(request_timeout=remaining, max_retries=0).stream(prompt)
            for chunk in provider:
                if can_retry is not None and not can_retry():
                    return
                clean = thinking.filter(str(getattr(chunk, "content", "") or ""))
                if clean:
                    visible = True
                    yield clean
            tail = thinking.flush()
            if tail:
                visible = True
                yield tail
            return
        except Exception as exc:
            # Preserve protocol integrity failures as fixed codes, not transport errors.
            if isinstance(exc, ProviderProtocolError) and not isinstance(getattr(exc, "failure", None), ProviderFailure):
                raise
            last_failure = classify_provider_failure(exc)
            logger.warning("visual_answer_request_failed attempt=%d category=%s http_status=%s visible=%s",
                           attempt + 1, last_failure.category, last_failure.status, visible)
            if visible or not last_failure.retryable or attempt:
                raise ProviderRequestFailure(last_failure) from None
        finally:
            close = getattr(provider, "close", None)
            if close:
                try:
                    close()
                except Exception as exc:
                    failure = classify_provider_failure(exc)
                    logger.warning("visual_answer_close_failed category=%s http_status=%s", failure.category, failure.status)
    raise ProviderRequestFailure(last_failure) from None
