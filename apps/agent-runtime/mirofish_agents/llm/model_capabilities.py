"""Infer LLM capability flags when catalog metadata is still the FALSE default.

OpenAI-compatible providers rarely publish supports_json. A hard gate on that
column previously blocked real DeepSeek / GPT chat models before any request.
Inference is permissive for chat models; only non-chat or reasoning-only ids
stay unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InferredModelCapabilities:
    supports_json: bool = False
    supports_tools: bool = False


def normalize_model_id(model_id: str | None) -> str:
    if not isinstance(model_id, str):
        return ""
    trimmed = model_id.strip()
    if not trimmed:
        return ""
    while trimmed.startswith("["):
        end = trimmed.find("]")
        if end <= 0:
            break
        trimmed = trimmed[end + 1 :].strip()
    return "".join(trimmed.lower().split())


def infer_model_capabilities(model_id: str | None) -> InferredModelCapabilities:
    normalized = normalize_model_id(model_id)
    if not normalized:
        return InferredModelCapabilities()
    if _is_non_chat_model(normalized) or _is_reasoning_only_model(normalized):
        return InferredModelCapabilities()
    return InferredModelCapabilities(supports_json=True, supports_tools=True)


def effective_supports_json(*, model_id: str | None, stored: bool) -> bool:
    if stored:
        return True
    return infer_model_capabilities(model_id).supports_json


def effective_supports_tools(*, model_id: str | None, stored: bool) -> bool:
    if stored:
        return True
    return infer_model_capabilities(model_id).supports_tools


def _is_reasoning_only_model(normalized: str) -> bool:
    if "deepseek" in normalized and (
        "reasoner" in normalized
        or "deepseek-r1" in normalized
        or "deepseek_r1" in normalized
        or "/r1" in normalized
    ):
        return True
    if normalized.startswith("qwq") or "-qwq" in normalized:
        return True
    return False


def _is_non_chat_model(normalized: str) -> bool:
    tokens = (
        "embedding",
        "embed",
        "whisper",
        "tts",
        "dall-e",
        "dalle",
        "gpt-image",
        "image-",
        "-image",
        "moderation",
        "realtime",
        "audio",
        "speech",
        "transcribe",
        "asr",
    )
    return any(token in normalized for token in tokens)
