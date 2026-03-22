"""块级事实提取辅助函数。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


ALIAS_PATTERNS = (
    re.compile(r"([\u4e00-\u9fff]{2,4})(?:又叫|也叫|被叫做|人称|被称作)([\u4e00-\u9fff]{2,4})"),
    re.compile(r"([\u4e00-\u9fff]{2,4})(?:正是|就是)([\u4e00-\u9fff]{2,4})"),
)
RULE_HINTS = ("规则", "法则", "禁制", "试炼", "协议", "系统")
SKELETON_CHARACTER_LIMIT = 12
SKELETON_ORGANIZATION_LIMIT = 8
FINGERPRINT_BLOCK_LIMIT = 2


def build_chapter_text(chapters: Sequence[Dict[str, Any]]) -> str:
    return "\n\n".join(
        f"### {item.get('title', item['chapter_id'])}\n{item['content']}"
        for item in chapters
    )


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？!?]\s*|\n+", text)
    return [item.strip(" \t，,；;") for item in parts if item.strip()]


def extract_world_rules(text: str) -> List[str]:
    return [sentence[:120] for sentence in split_sentences(text) if any(hint in sentence for hint in RULE_HINTS)][:6]


def extract_aliases(text: str) -> Dict[str, Any]:
    alias_to_names: Dict[str, set] = {}
    for pattern in ALIAS_PATTERNS:
        for match in pattern.finditer(text):
            canonical, alias = _canonical_alias_pair(*match.groups())
            alias_to_names.setdefault(alias, set()).add(canonical)
    aliases: Dict[str, List[str]] = {}
    ambiguities = []
    for alias, names in alias_to_names.items():
        if len(names) == 1:
            canonical = next(iter(names))
            aliases.setdefault(canonical, []).append(alias)
            continue
        ambiguities.append(
            {
                "alias": alias,
                "candidate_names": sorted(names),
                "reason": "同一别名在文本中指向多个角色",
            }
        )
    return {
        "aliases": {name: sorted(items) for name, items in aliases.items()},
        "ambiguities": ambiguities,
    }


def build_skeleton_context(
    block: Dict[str, Any],
    skeleton: Optional[Dict[str, Any]],
) -> str:
    if not skeleton:
        return "未提供骨架时间线。"
    global_characters = _format_ranked_entities(
        skeleton.get("global_characters", []),
        SKELETON_CHARACTER_LIMIT,
    )
    global_organizations = ", ".join(
        item["name"] for item in skeleton.get("global_organizations", [])[:SKELETON_ORGANIZATION_LIMIT]
    ) or "无"
    range_characters = ", ".join(_range_entities(block, skeleton, "characters")) or "无"
    range_organizations = ", ".join(_range_entities(block, skeleton, "organizations")) or "无"
    return "\n".join(
        [
            f"已知全文角色（按出现频率排序）：{global_characters}",
            f"已知组织：{global_organizations}",
            f"当前块({block['block_id']})覆盖{_block_range_text(block)}，该范围内已知出场角色：{range_characters}",
            f"该范围内已知出场组织：{range_organizations}",
        ]
    )


def build_anchor_context(
    block: Dict[str, Any],
    anchors: Optional[Sequence[Dict[str, Any]]],
) -> str:
    anchor = _previous_anchor(block, anchors or [])
    if not anchor:
        return "无可用前情锚点。"
    world_state = anchor.get("world_state", {})
    active_characters = _format_named_states(world_state.get("active_characters", []), "last_action")
    active_organizations = _format_named_states(world_state.get("active_organizations", []), "key_change")
    relationships = _format_relationships(world_state.get("key_relationships", []))
    open_threads = "，".join(world_state.get("open_plot_threads", [])[:6]) or "无"
    summary = world_state.get("recent_events_summary") or "无"
    return "\n".join(
        [
            f"最近锚点：{anchor.get('anchor_id', '未知锚点')}（截至第{anchor.get('chapter_range', {}).get('end', 0)}章）",
            f"当前活跃角色：{active_characters}",
            f"当前活跃组织：{active_organizations}",
            f"关键关系：{relationships}",
            f"开放线索：{open_threads}",
            f"最近事件：{summary}",
        ]
    )


def build_fingerprint_context(
    block: Dict[str, Any],
    blocks: Sequence[Dict[str, Any]],
    skeleton: Optional[Dict[str, Any]],
) -> str:
    if not skeleton:
        return "无可用前文指纹。"
    sketch_map = {item["chapter_id"]: item for item in skeleton.get("chapter_sketches", [])}
    previous_blocks = _previous_blocks(block, blocks)[:FINGERPRINT_BLOCK_LIMIT]
    if not previous_blocks:
        return "无可用前文指纹。"
    lines = []
    for previous in previous_blocks:
        fingerprints = []
        for chapter_id in previous.get("owned_chapter_ids", []):
            sketch = sketch_map.get(chapter_id, {})
            fingerprint = sketch.get("fingerprint")
            if fingerprint:
                fingerprints.append(fingerprint)
        if not fingerprints:
            continue
        lines.append(f"{previous['block_id']}: {'；'.join(fingerprints[:2])}")
    return "\n".join(lines) or "无可用前文指纹。"


def _canonical_alias_pair(first: str, second: str) -> tuple[str, str]:
    if len(first) >= len(second):
        return first, second
    return second, first


def _format_ranked_entities(items: Sequence[Dict[str, Any]], limit: int) -> str:
    visible = items[:limit]
    if not visible:
        return "无"
    return ", ".join(
        f"{item['name']}(出现{item.get('appearance_count', len(item.get('chapter_ids', [])))}章, 提及{item.get('mention_count', 0)}次)"
        for item in visible
    )


def _range_entities(
    block: Dict[str, Any],
    skeleton: Dict[str, Any],
    key: str,
) -> List[str]:
    chapter_ids = set(block.get("owned_chapter_ids", []))
    names: List[str] = []
    seen = set()
    for sketch in skeleton.get("chapter_sketches", []):
        if sketch.get("chapter_id") not in chapter_ids:
            continue
        for name in sketch.get(key, []):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names[:SKELETON_CHARACTER_LIMIT]


def _block_range_text(block: Dict[str, Any]) -> str:
    chapter_range = block.get("owned_chapter_range") or {}
    start = chapter_range.get("start_order")
    end = chapter_range.get("end_order")
    if start and end:
        return f"第{start}-{end}章"
    return "当前章节范围"


def _previous_anchor(
    block: Dict[str, Any],
    anchors: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    block_order = block.get("order") or _numeric_suffix(block.get("block_id", ""))
    visible = [item for item in anchors if item.get("end_block_order", 0) < block_order]
    if not visible:
        return None
    return max(visible, key=lambda item: item.get("end_block_order", 0))


def _previous_blocks(
    block: Dict[str, Any],
    blocks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    block_order = block.get("order") or _numeric_suffix(block.get("block_id", ""))
    ordered = sorted(blocks, key=lambda item: item.get("order", _numeric_suffix(item.get("block_id", ""))))
    previous = [item for item in ordered if (item.get("order") or _numeric_suffix(item.get("block_id", ""))) < block_order]
    return previous[-FINGERPRINT_BLOCK_LIMIT:]


def _format_named_states(items: Sequence[Dict[str, Any]], detail_key: str) -> str:
    if not items:
        return "无"
    return "，".join(
        f"{item.get('name', '未知')}({item.get('status', 'unknown')}{_detail_suffix(item.get(detail_key, ''))})"
        for item in items[:6]
    )


def _format_relationships(items: Sequence[Dict[str, Any]]) -> str:
    if not items:
        return "无"
    return "，".join(
        f"{item.get('source', '未知')}↔{item.get('target', '未知')}({item.get('state', 'unknown')})"
        for item in items[:6]
    )


def _detail_suffix(text: str) -> str:
    return f", {text}" if text else ""


def _numeric_suffix(value: str) -> int:
    try:
        return int(value.rsplit("_", 1)[-1])
    except ValueError:
        return 0
