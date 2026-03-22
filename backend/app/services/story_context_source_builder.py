"""构造优先使用故事记忆的 LLM 输入源。"""

from typing import Any, Dict, List, Optional, Sequence


def build_story_context_source(
    max_length: int,
    combined_text: str,
    chapter_continuity: Optional[Dict[str, Any]],
    story_memory: Optional[Dict[str, Any]],
    block_analyses: Optional[Sequence[Dict[str, Any]]],
) -> str:
    structured = _structured_story_source(story_memory, block_analyses)
    if structured:
        return _trim(structured, max_length, "故事记忆已截断")
    continuity = _continuity_source(chapter_continuity)
    if continuity:
        return _trim(continuity, max_length, "章节摘要已截断")
    return _trim(combined_text, max_length, "文本已截断")


def _structured_story_source(
    story_memory: Optional[Dict[str, Any]],
    block_analyses: Optional[Sequence[Dict[str, Any]]],
) -> str:
    if not story_memory and not block_analyses:
        return ""
    lines: List[str] = ["## 故事记忆"]
    if story_memory:
        lines.append(f"剧情块数量: {story_memory.get('block_count', 0)}")
        for item in story_memory.get("block_summaries", [])[:12]:
            lines.append(f"- {item.get('block_id', '')}: {item.get('summary', '')}")
        lines.append("## 关键实体")
        entities = sorted(
            story_memory.get("entity_registry", {}).values(),
            key=lambda item: (-len(item.get("mention_blocks", [])), item.get("name", "")),
        )[:12]
        for entity in entities:
            lines.append(
                f"- {entity.get('name', '')} ({entity.get('entity_type', '')})：{entity.get('summary', '')}"
            )
    if block_analyses:
        lines.append("## 块级剧情分析")
        for item in list(block_analyses)[:12]:
            lines.append(f"- {item.get('block_id', '')}: {item.get('plot_summary', '')}")
    return "\n".join(line for line in lines if line).strip()


def _continuity_source(chapter_continuity: Optional[Dict[str, Any]]) -> str:
    if not chapter_continuity or not chapter_continuity.get("chapters"):
        return ""
    lines = ["## 全局连续性摘要", chapter_continuity.get("global_summary", "")]
    for item in chapter_continuity.get("chapters", [])[:60]:
        lines.extend(
            [
                f"### {item.get('title', item.get('chapter_id', '章节'))}",
                f"承接: {item.get('head_context', '')}",
                "角色: " + "、".join(item.get("key_characters", [])[:6]),
                "组织: " + "、".join(item.get("key_organizations", [])[:4]),
                "冲突: " + "；".join(item.get("core_conflicts", [])[:3]),
                "尾钩: " + "；".join(item.get("tail_hooks", [])[:3]),
            ]
        )
    return "\n".join(lines).strip()


def _trim(text: str, max_length: int, suffix: str) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n...({suffix})"
