"""LLM JSON 响应解析与对象归一化工具。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict


MAX_PAYLOAD_PREVIEW_LENGTH = 240
logger = logging.getLogger(__name__)


def clean_json_response_text(response: str) -> str:
    cleaned = response.strip()
    # 移除 BOM 标记
    cleaned = cleaned.lstrip("\ufeff")
    # 移除 markdown 代码块包裹
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()
    # 如果 LLM 在 JSON 前面加了解释性文字，尝试定位第一个 '{' 或 '['
    if cleaned and cleaned[0] not in ("{", "["):
        brace = cleaned.find("{")
        bracket = cleaned.find("[")
        candidates = [pos for pos in (brace, bracket) if pos >= 0]
        if candidates:
            start = min(candidates)
            cleaned = cleaned[start:]
    # 如果 LLM 在 JSON 后面加了解释性文字，尝试截断到最后一个 '}' 或 ']'
    if cleaned and cleaned[-1] not in ("}", "]"):
        brace = cleaned.rfind("}")
        bracket = cleaned.rfind("]")
        candidates = [pos for pos in (brace, bracket) if pos >= 0]
        if candidates:
            end = max(candidates)
            cleaned = cleaned[: end + 1]
    return cleaned.strip()


def parse_json_response(response: str) -> Any:
    cleaned = clean_json_response_text(response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = repair_json_response_text(cleaned)
        if repaired != cleaned:
            try:
                payload = json.loads(repaired)
                logger.warning("LLM JSON 已自动修复后解析成功")
                return payload
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM返回的JSON格式无效: {cleaned}") from exc


def repair_json_response_text(response: str) -> str:
    return _repair_container_closers(_normalize_string_control_chars(response))


def normalize_json_object(payload: Any, label: str) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return _normalize_list_payload(payload, label)
    raise ValueError(f"{label}必须返回 JSON 对象，实际收到 {type(payload).__name__}: {_preview_payload(payload)}")


def _normalize_list_payload(payload: list[Any], label: str) -> Dict[str, Any]:
    if not payload:
        raise ValueError(f"{label}必须返回 JSON 对象，实际收到空 list")
    if len(payload) != 1:
        raise ValueError(
            f"{label}必须返回单个 JSON 对象，实际收到包含 {len(payload)} 个元素的 list: {_preview_payload(payload)}"
        )
    item = payload[0]
    if not isinstance(item, dict):
        raise ValueError(
            f"{label}必须返回 JSON 对象，实际收到 list[{type(item).__name__}]: {_preview_payload(payload)}"
        )
    return item


def _preview_payload(payload: Any) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        text = repr(payload)
    if len(text) <= MAX_PAYLOAD_PREVIEW_LENGTH:
        return text
    return text[: MAX_PAYLOAD_PREVIEW_LENGTH - 3] + "..."


def _normalize_string_control_chars(text: str) -> str:
    chunks: list[str] = []
    in_string = False
    escaping = False
    for char in text:
        if in_string:
            if escaping:
                chunks.append(char)
                escaping = False
                continue
            if char == "\\":
                chunks.append(char)
                escaping = True
                continue
            if char == '"':
                chunks.append(char)
                in_string = False
                continue
            if char in "\r\n\t":
                chunks.append(" ")
                continue
            chunks.append(char)
            continue
        chunks.append(char)
        if char == '"':
            in_string = True
    if in_string:
        chunks.append('"')
    return "".join(chunks)


def _repair_container_closers(text: str) -> str:
    chunks: list[str] = []
    closers: list[str] = []
    in_string = False
    escaping = False
    for char in text:
        if in_string:
            chunks.append(char)
            if escaping:
                escaping = False
                continue
            if char == "\\":
                escaping = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            chunks.append(char)
            in_string = True
            continue
        if char == "{":
            chunks.append(char)
            closers.append("}")
            continue
        if char == "[":
            chunks.append(char)
            closers.append("]")
            continue
        if char in "}]":
            while closers and closers[-1] != char:
                chunks.append(closers.pop())
            if closers and closers[-1] == char:
                chunks.append(char)
                closers.pop()
            continue
        chunks.append(char)
    if in_string:
        chunks.append('"')
    while closers:
        chunks.append(closers.pop())
    return "".join(chunks)
