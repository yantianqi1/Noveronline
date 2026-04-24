"""LLM 瞬时错误与永久错误的识别。"""

from __future__ import annotations

from openai import APIConnectionError, APIStatusError, APITimeoutError


RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_ERROR_MARKERS = (
    "504 gateway time-out",
    "504: gateway time-out",
    "gateway timeout",
    "gateway time-out",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "connection error",
    "error code 504",
)

PERMANENT_STATUS_CODES = {400, 401, 402, 403, 404, 422}
PERMANENT_ERROR_MARKERS = (
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "permission denied",
    "permission_denied",
    "insufficient_quota",
    "insufficient quota",
    "quota exceeded",
    "billing",
    "model not found",
    "model_not_found",
    "does not exist",
    "not a valid model",
)


def _status_code(exc: Exception):
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    return status_code


def is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        if _status_code(exc) in RETRYABLE_STATUS_CODES:
            return True
    message = str(exc).lower()
    return any(marker in message for marker in RETRYABLE_ERROR_MARKERS)


def is_permanent_llm_error(exc: Exception) -> bool:
    """永久错误:重试无意义,立即暴露给用户(典型:鉴权/额度/模型不存在/请求体非法)。"""
    try:
        from openai import (
            AuthenticationError,
            NotFoundError,
            PermissionDeniedError,
        )
        if isinstance(exc, (AuthenticationError, NotFoundError, PermissionDeniedError)):
            return True
    except Exception:
        pass
    if isinstance(exc, APIStatusError):
        if _status_code(exc) in PERMANENT_STATUS_CODES:
            return True
    message = str(exc).lower()
    return any(marker in message for marker in PERMANENT_ERROR_MARKERS)
