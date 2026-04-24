"""段级 LLM 调用重试策略。

包装一个可重试的调用,区分永久错误与可恢复错误,并允许上层通过
on_retry 回调"无感"地更新 UI(不追加新 timeline 事件,只改 detail)。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


class PermanentLLMError(Exception):
    """永久错误:认证失败/额度耗尽/模型不存在,重试无意义。"""

    def __init__(self, original: Exception, error_class: str, detail: str) -> None:
        super().__init__(detail)
        self.original = original
        self.error_class = error_class
        self.detail = detail


class ExhaustedLLMRetries(Exception):
    """瞬态或内容错误用尽了段级重试预算。"""

    def __init__(
        self,
        original: Exception,
        error_class: str,
        detail: str,
        attempts: int,
    ) -> None:
        super().__init__(detail)
        self.original = original
        self.error_class = error_class
        self.detail = detail
        self.attempts = attempts


@dataclass
class RetryPolicy:
    """段级重试参数。max_attempts 含首次尝试在内。"""

    max_attempts: int = 2
    base_delay_seconds: float = 10.0
    max_delay_seconds: float = 30.0

    def compute_delay(self, retry_index: int) -> float:
        """retry_index: 1 表示第 1 次重试(第 2 次调用)。"""
        exponential = self.base_delay_seconds * (2 ** (retry_index - 1))
        return min(exponential, self.max_delay_seconds)


def classify_llm_error(exc: Exception) -> Tuple[str, str]:
    """把 LLM 异常归类到 (error_class, human_detail)。"""
    from .llm_transient import is_permanent_llm_error, is_transient_llm_error

    message = str(exc)
    lower = message.lower()

    if is_permanent_llm_error(exc):
        if any(m in lower for m in ("unauthorized", "api key", "authentication", " 401")):
            return ("permanent_auth", f"API 认证失败: {message}")
        if any(m in lower for m in ("quota", "insufficient", "billing", " 402")):
            return ("permanent_quota", f"API 额度或计费异常: {message}")
        if any(m in lower for m in ("model_not_found", "model not found", "does not exist", " 404")):
            return ("permanent_model", f"LLM 模型不存在或不可用: {message}")
        return ("permanent_other", f"LLM 永久错误: {message}")

    if is_transient_llm_error(exc):
        return ("transient", f"LLM 瞬时错误: {message}")

    return ("content", f"LLM 输出格式错误: {message}")


def retry_with_policy(
    fn: Callable[[int], Any],
    *,
    policy: RetryPolicy,
    on_retry: Optional[Callable[[int, int, float, str, Exception], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """按 policy 执行 ``fn(attempt)``。

    - ``fn`` 收到的 attempt 从 0 开始,可据此退化 prompt。
    - 捕获 ``PermanentLLMError`` 分类的异常时立即抛出 ``PermanentLLMError``。
    - 其它异常计入重试预算;用尽后抛出 ``ExhaustedLLMRetries``。
    - ``on_retry(attempt, max_attempts, wait_seconds, error_class, exc)``
      在每次准备重试前调用,便于无感更新 UI。
    """
    if policy.max_attempts < 1:
        raise ValueError("max_attempts 必须 ≥ 1")

    last_exc: Optional[Exception] = None
    for attempt in range(policy.max_attempts):
        try:
            return fn(attempt)
        except PermanentLLMError:
            raise
        except Exception as exc:
            last_exc = exc
            error_class, detail = classify_llm_error(exc)
            if error_class.startswith("permanent_"):
                raise PermanentLLMError(exc, error_class, detail) from exc

            is_last = attempt >= policy.max_attempts - 1
            if is_last:
                raise ExhaustedLLMRetries(
                    exc, error_class, detail, attempt + 1
                ) from exc

            delay = policy.compute_delay(attempt + 1)
            if on_retry is not None:
                try:
                    on_retry(attempt + 1, policy.max_attempts, delay, error_class, exc)
                except Exception:
                    logger.exception("retry on_retry 回调抛出异常,忽略并继续重试")

            logger.warning(
                "retry_with_policy 第 %d/%d 次失败 (%s),%ds 后重试: %s",
                attempt + 1,
                policy.max_attempts,
                error_class,
                int(delay),
                exc,
            )
            sleep(delay)

    # 仅防御性兜底:正常路径不会走到这里
    raise RuntimeError(f"retry_with_policy 意外返回,最后异常: {last_exc}")
