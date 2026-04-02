"""种子管线四大章节定义与 stage→chapter 映射。"""

from __future__ import annotations

from typing import Dict, List

PIPELINE_CHAPTERS: List[Dict] = [
    {
        "key": "text_prep",
        "label": "文本准备",
        "stages": ["uploading", "extract_text", "segment_chapters", "build_blocks"],
    },
    {
        "key": "world_scan",
        "label": "世界扫描",
        "stages": ["skeleton_timeline", "anchor_generation"],
    },
    {
        "key": "fact_extract",
        "label": "事实提取",
        "stages": [
            "extract_local_facts",
            "merge_story_memory",
            "entity_resolution",
            "contextual_block_analysis",
            "chapter_card_generation",
            "consistency_audit",
            "build_continuity",
        ],
    },
    {
        "key": "output_settle",
        "label": "成果沉淀",
        "stages": ["seed_analysis", "ontology", "completed", "failed"],
    },
]

STAGE_TO_CHAPTER: Dict[str, str] = {
    stage: chapter["key"]
    for chapter in PIPELINE_CHAPTERS
    for stage in chapter["stages"]
}

CHAPTER_LABEL: Dict[str, str] = {ch["key"]: ch["label"] for ch in PIPELINE_CHAPTERS}


def chapter_for_stage(stage: str) -> str:
    """返回 stage 所属的 chapter key，未匹配时返回空字符串。"""
    return STAGE_TO_CHAPTER.get(stage, "")


def label_for_chapter(chapter_key: str) -> str:
    """返回 chapter key 对应的中文标签。"""
    return CHAPTER_LABEL.get(chapter_key, "")
