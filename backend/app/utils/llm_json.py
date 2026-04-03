"""LLM JSON 响应解析与对象归一化工具。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List


MAX_PAYLOAD_PREVIEW_LENGTH = 240
logger = logging.getLogger(__name__)

# 管道分隔记录的行头标识
_PIPE_RECORD_TYPES = ("EVENT", "ENTITY", "RELATION", "THREAD", "REF")
_PIPE_LINE_RE = re.compile(
    r"^(" + "|".join(_PIPE_RECORD_TYPES) + r")\|(.+)$",
)


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


def parse_json_response(response: str, *, truncated: bool = False) -> Any:
    cleaned = clean_json_response_text(response)
    # 若已知截断，先做激进修复
    if truncated:
        cleaned = _repair_truncated_json(cleaned)
    # Level 1: 直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Level 2: 括号修复 + 控制字符归一化
    repaired = repair_json_response_text(cleaned)
    if repaired != cleaned:
        try:
            payload = json.loads(repaired)
            logger.warning("LLM JSON 已自动修复后解析成功")
            return payload
        except json.JSONDecodeError:
            pass
    # Level 3: 正则提取 JSON + 换行修复 + 控制字符清理
    regex_result = _try_regex_extract_json(cleaned)
    if regex_result is not None:
        logger.warning("LLM JSON 通过正则提取后解析成功")
        return regex_result
    # Level 4: 管道分隔格式 (EVENT|key=value|...)
    pipe_result = _try_parse_pipe_delimited(response)
    if pipe_result is not None:
        return pipe_result
    # Level 5: 放弃
    raise ValueError(f"LLM返回的JSON格式无效: {_preview_payload(cleaned)}")


def _try_parse_pipe_delimited(response: str) -> Any:
    """尝试将管道分隔的记录转换为等价 JSON 结构。

    某些模型（如 Gemini）在 JSON 模式下偶尔返回管道分隔格式:
        EVENT|summary=事件概要|characters=角色A,角色B|sentence_refs=...
    此函数将其转换为下游归一化器可以处理的 dict 结构。
    """
    lines = response.strip().splitlines()
    # 过滤掉空行和验证/错误提示行（如 "EVENT 记录缺少字段 organizations: ..."）
    record_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 如果是"错误: 原始记录"的格式，提取冒号后面的原始记录
        if "记录缺少字段" in line or "record missing" in line.lower():
            colon_pos = line.find(": ")
            if colon_pos >= 0:
                line = line[colon_pos + 2:].strip()
        if _PIPE_LINE_RE.match(line):
            record_lines.append(line)
    if not record_lines:
        return None
    events: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    threads: List[Dict[str, Any]] = []
    for line in record_lines:
        match = _PIPE_LINE_RE.match(line)
        if not match:
            continue
        record_type, fields_str = match.group(1), match.group(2)
        fields = _parse_pipe_fields(fields_str)
        if record_type == "EVENT":
            events.append(_pipe_event_to_dict(fields))
        elif record_type == "ENTITY":
            entities.append(_pipe_entity_to_dict(fields))
        elif record_type == "RELATION":
            relations.append(_pipe_relation_to_dict(fields))
        elif record_type == "THREAD":
            threads.append(_pipe_thread_to_dict(fields))
    if not events and not entities and not relations and not threads:
        return None
    return {
        "local_events": events,
        "local_entities": entities,
        "local_relationship_changes": relations,
        "local_threads": threads,
        "unresolved_refs": [],
        "local_summary": events[0]["summary"] if events else "",
        "evidence_spans": [],
        "world_rules": [],
    }


def _parse_pipe_fields(fields_str: str) -> Dict[str, str]:
    """解析 key=value|key=value 格式的字段。"""
    fields: Dict[str, str] = {}
    for segment in fields_str.split("|"):
        eq_pos = segment.find("=")
        if eq_pos < 0:
            continue
        key = segment[:eq_pos].strip()
        value = segment[eq_pos + 1:].strip()
        fields[key] = value
    return fields


def _split_comma(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _pipe_event_to_dict(fields: Dict[str, str]) -> Dict[str, Any]:
    return {
        "summary": fields.get("summary", ""),
        "characters": _split_comma(fields.get("characters", "")),
        "organizations": _split_comma(fields.get("organizations", "")),
        "evidence": _split_comma(fields.get("evidence", fields.get("sentence_refs", ""))),
    }


def _pipe_entity_to_dict(fields: Dict[str, str]) -> Dict[str, Any]:
    return {
        "name": fields.get("name", ""),
        "entity_type": fields.get("entity_type", fields.get("type", "character")),
        "aliases": _split_comma(fields.get("aliases", "")),
        "summary": fields.get("summary", ""),
        "importance_tier": fields.get("importance_tier", "supporting"),
        "evidence": _split_comma(fields.get("evidence", "")),
    }


def _pipe_relation_to_dict(fields: Dict[str, str]) -> Dict[str, Any]:
    return {
        "source": fields.get("source", ""),
        "target": fields.get("target", ""),
        "change": fields.get("change", fields.get("relation_type", "co_occurrence")),
        "weight": 1,
        "evidence": _split_comma(fields.get("evidence", "")),
    }


def _pipe_thread_to_dict(fields: Dict[str, str]) -> Dict[str, Any]:
    return {
        "thread_key": fields.get("thread_key", fields.get("key", "")),
        "status": fields.get("status", "open"),
        "summary": fields.get("summary", ""),
    }


def _try_regex_extract_json(text: str) -> Any:
    """从混合文本中正则提取 JSON 对象并尝试解析。

    处理 LLM 在 JSON 前后混入解释文字、字符串值内包含换行符、
    或存在控制字符等情况。
    """
    # 尝试提取最大的 JSON 对象
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        # 尝试提取 JSON 数组
        match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return None
    json_str = match.group()
    # 修复字符串值内的换行符
    def _fix_string_newlines(m: re.Match) -> str:
        s = m.group(0)
        s = s.replace("\n", " ").replace("\r", " ")
        s = re.sub(r"\s+", " ", s)
        return s
    json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', _fix_string_newlines, json_str)
    # 移除控制字符
    json_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    # 再次尝试括号修复后解析
    repaired = _repair_container_closers(json_str)
    if repaired != json_str:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
    return None


def _repair_truncated_json(text: str) -> str:
    """激进修复被截断的 JSON（finish_reason='length'时使用）。

    比 _repair_container_closers 更激进：处理未闭合字符串、
    尾部不完整 key-value、尾部逗号等。
    """
    text = text.rstrip()
    if not text:
        return text
    # 检测并闭合未闭合的字符串（奇数个未转义引号）
    in_string = False
    escaping = False
    for char in text:
        if escaping:
            escaping = False
            continue
        if char == "\\":
            if in_string:
                escaping = True
            continue
        if char == '"':
            in_string = not in_string
    if in_string:
        text += '"'
    # 移除尾部不完整的 key-value（如 "key":  或 "key": "val 被截断后已闭合）
    # 模式: 逗号后跟一个 key 但没有完整 value
    text = re.sub(r',\s*"[^"]*"\s*:\s*$', "", text)
    # 移除尾部悬挂逗号（闭合括号前）
    text = re.sub(r",\s*$", "", text)
    # 最后用标准括号修复闭合
    return _repair_container_closers(text)


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
            # 跳过其他控制字符（\x00-\x08, \x0b-\x0c, \x0e-\x1f, \x7f-\x9f）
            code = ord(char)
            if code < 0x20 or 0x7F <= code <= 0x9F:
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
