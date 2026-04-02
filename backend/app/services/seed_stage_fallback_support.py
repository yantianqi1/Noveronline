"""Seed 阶段的 LLM 失败归类与规则回退辅助。"""

from __future__ import annotations

from typing import Any, Dict

from ..utils.llm_transient import is_transient_llm_error
from ..utils.upstream_error_formatter import format_upstream_service_error


JSON_ERROR_PREFIX = "LLM返回的JSON格式无效"
MAX_REASON_LENGTH = 180
NON_FALLBACK_MARKERS = (
    "未配置 LLM 渠道",
    "缺少可用客户端",
    "绑定的渠道",
    "模块绑定",
)
SCHEMA_ERROR_MARKERS = (
    "必须返回 JSON 对象",
    "缺少必需字段",
)


def should_use_rule_fallback(exc: Exception) -> bool:
    message = str(exc)
    if any(marker in message for marker in NON_FALLBACK_MARKERS):
        return False
    return (
        message.startswith(JSON_ERROR_PREFIX)
        or any(marker in message for marker in SCHEMA_ERROR_MARKERS)
        or "上游调用失败" in message
        or is_transient_llm_error(exc)
    )


def summarize_stage_failure(exc: Exception) -> str:
    raw = str(exc).strip()
    if not raw:
        return "未知错误"
    if raw.startswith(JSON_ERROR_PREFIX):
        return "LLM JSON 结构不合法"
    if any(marker in raw for marker in SCHEMA_ERROR_MARKERS):
        return "LLM JSON 结构与预期 schema 不匹配"
    formatted = format_upstream_service_error(exc)
    if formatted != raw:
        raw = formatted
    else:
        raw = raw.splitlines()[0].strip()
    if len(raw) <= MAX_REASON_LENGTH:
        return raw
    return raw[: MAX_REASON_LENGTH - 3] + "..."


def attach_rule_fallback(payload: Dict[str, Any], exc: Exception, *, mode: str = "rule_fallback") -> Dict[str, Any]:
    return {
        **payload,
        "generation_mode": mode,
        "fallback_reason": summarize_stage_failure(exc),
    }
