"""种子分析阶段的瞬时 LLM 重试封装。"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from ..utils.llm_transient import is_transient_llm_error
from ..utils.upstream_error_formatter import format_upstream_service_error


T = TypeVar("T")

SEED_LLM_RETRY_LIMIT = 2
SEED_LLM_RETRY_INITIAL_DELAY_SECONDS = 2.0
SEED_LLM_RETRY_MAX_DELAY_SECONDS = 8.0

logger = logging.getLogger(__name__)


def call_with_seed_llm_retry(action: Callable[[], T], *, stage_label: str, target_label: str) -> T:
    delay = SEED_LLM_RETRY_INITIAL_DELAY_SECONDS
    for attempt in range(SEED_LLM_RETRY_LIMIT + 1):
        try:
            return action()
        except Exception as exc:
            if not is_transient_llm_error(exc):
                raise
            if attempt >= SEED_LLM_RETRY_LIMIT:
                message = format_upstream_service_error(exc)
                raise RuntimeError(f"{stage_label} {target_label} 上游调用失败：{message}") from exc
            logger.warning(
                "种子分析 LLM 瞬时失败，准备重试 (stage=%s, target=%s, attempt=%s, delay=%.1fs): %s",
                stage_label,
                target_label,
                attempt + 1,
                delay,
                exc,
            )
            time.sleep(delay)
            delay = min(delay * 2, SEED_LLM_RETRY_MAX_DELAY_SECONDS)
