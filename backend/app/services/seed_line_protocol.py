"""Seed 阶段轻量行协议解析与句子引用物化。"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence


class LineProtocolError(ValueError):
    """行协议解析错误。"""


def clean_protocol_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:text|plain)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def protocol_lines(text: str) -> List[str]:
    return [line.strip() for line in clean_protocol_text(text).splitlines() if line.strip()]


def parse_kv_line(line: str, *, record_type: str, required_keys: Sequence[str]) -> Dict[str, str]:
    parts = [part.strip() for part in line.split("|")]
    if not parts or parts[0] != record_type:
        raise LineProtocolError(f"期望 {record_type} 记录，实际收到: {line}")
    payload: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            raise LineProtocolError(f"{record_type} 记录缺少 key=value 字段: {line}")
        key, value = part.split("=", 1)
        payload[key.strip()] = value.strip()
    for key in required_keys:
        if key not in payload:
            raise LineProtocolError(f"{record_type} 记录缺少字段 {key}: {line}")
    return payload


def parse_csv_list(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_sentence_ref_list(value: str, *, valid_sentence_ids: Iterable[str]) -> List[str]:
    valid = set(valid_sentence_ids)
    refs = parse_csv_list(value)
    unknown = [item for item in refs if item not in valid]
    if unknown:
        raise LineProtocolError(f"未知 sentence_id: {','.join(unknown)}")
    return refs


def parse_positive_int(value: str, *, default: int = 1) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def sentence_texts(sentence_refs: Sequence[str], sentence_map: Dict[str, Dict[str, object]], *, limit: int = 3) -> List[str]:
    texts: List[str] = []
    for ref in sentence_refs:
        item = sentence_map.get(ref)
        text = str((item or {}).get("text") or "").strip()
        if text and text not in texts:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def chapter_id_for_refs(sentence_refs: Sequence[str], sentence_map: Dict[str, Dict[str, object]]) -> str:
    for ref in sentence_refs:
        item = sentence_map.get(ref)
        chapter_id = str((item or {}).get("chapter_id") or "").strip()
        if chapter_id:
            return chapter_id
    return ""


def evidence_spans(sentence_refs: Sequence[str], sentence_map: Dict[str, Dict[str, object]], *, limit: int = 12) -> List[Dict[str, str]]:
    spans: List[Dict[str, str]] = []
    for ref in sentence_refs:
        item = sentence_map.get(ref) or {}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        spans.append({"chapter_id": str(item.get("chapter_id") or ""), "snippet": text, "sentence_id": ref})
        if len(spans) >= limit:
            break
    return spans
