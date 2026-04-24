"""种子管线章节定义与 stage→chapter 映射（新版四阶段管线）。"""

from __future__ import annotations

from typing import Dict, List

PIPELINE_CHAPTERS: List[Dict] = [
    {
        "key": "text_prep",
        "label": "文本准备",
        "stages": ["uploading", "extract_text", "smart_segmentation"],
    },
    {
        "key": "deep_reading",
        "label": "深度阅读",
        "stages": ["sequential_reading", "arc_summary"],
    },
    {
        "key": "integration",
        "label": "全局整合",
        "stages": ["global_integration", "ontology"],
    },
    {
        "key": "agent_build",
        "label": "角色构建",
        "stages": ["agent_profiles"],
    },
    {
        "key": "global_link",
        "label": "数据打通",
        "stages": [
            "archive_sync",
            "graph_build",
            "index_rebuild",
            "completed",
            "failed",
        ],
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
