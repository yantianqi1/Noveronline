"""把多个块的文风结果聚合成一份最终 writing_style 资产。

策略：对单值字段做众数 + 取最常见的几种；对列表字段做去重并按出现频率排序保留 top N；
对 example_snippets 直接合并去重保留前若干条。
"""

from __future__ import annotations

from collections import Counter
from typing import Any


_SINGLE_FIELDS = ("narrative_pov", "tense", "pacing", "vocabulary", "dialogue_style", "tone")
_LIST_FIELDS = ("sentence_features", "rhetoric", "distinctive_devices")


def _top_strings(values: list[str], top: int) -> list[str]:
    counter = Counter(v.strip() for v in values if isinstance(v, str) and v.strip())
    return [v for v, _ in counter.most_common(top)]


def aggregate_chunk_results(chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunk_results:
        return {}

    aggregated: dict[str, Any] = {}

    for field in _SINGLE_FIELDS:
        values = [r.get(field) for r in chunk_results if isinstance(r.get(field), str)]
        if values:
            top = _top_strings(values, top=3)
            aggregated[field] = top[0] if len(top) == 1 else " / ".join(top)

    for field in _LIST_FIELDS:
        flat: list[str] = []
        for r in chunk_results:
            v = r.get(field) or []
            if isinstance(v, list):
                flat.extend(str(x) for x in v if x)
        aggregated[field] = _top_strings(flat, top=8)

    snippets: list[str] = []
    for r in chunk_results:
        for s in r.get("example_snippets") or []:
            if isinstance(s, str) and s.strip() and s not in snippets:
                snippets.append(s.strip())
    aggregated["example_snippets"] = snippets[:12]
    aggregated["chunk_count"] = len(chunk_results)
    return aggregated


def render_style_content(payload: dict[str, Any]) -> str:
    """Format the aggregated payload as a human + LLM-friendly text block.

    This text is what the writer agent gets injected into its prompt; it should
    be self-contained and easy to follow.
    """
    lines: list[str] = ["# 写作风格指南", ""]
    label_map = {
        "narrative_pov": "叙事视角",
        "tense": "时态",
        "pacing": "节奏",
        "vocabulary": "用词偏好",
        "dialogue_style": "对白风格",
        "tone": "总体基调",
    }
    for k, label in label_map.items():
        if payload.get(k):
            lines.append(f"- **{label}**：{payload[k]}")

    list_label = {
        "sentence_features": "句式特征",
        "rhetoric": "修辞偏好",
        "distinctive_devices": "标志性笔法",
    }
    for k, label in list_label.items():
        items = payload.get(k) or []
        if items:
            lines.append(f"- **{label}**：" + "；".join(items))

    snippets = payload.get("example_snippets") or []
    if snippets:
        lines.append("")
        lines.append("## 风格示例片段")
        for s in snippets:
            lines.append(f"> {s}")

    return "\n".join(lines)
