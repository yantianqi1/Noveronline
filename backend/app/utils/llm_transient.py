"""LLM 瞬时错误识别。"""

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


def is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if status_code is None:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
        if status_code in RETRYABLE_STATUS_CODES:
            return True
    message = str(exc).lower()
    return any(marker in message for marker in RETRYABLE_ERROR_MARKERS)
