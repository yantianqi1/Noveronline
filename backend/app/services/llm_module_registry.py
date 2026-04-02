"""LLM 业务模块注册表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class LlmModuleDefinition:
    module_key: str
    label: str
    description: str


MODULE_DEFINITIONS = (
    LlmModuleDefinition("story_ontology", "种子本体生成", "为小说种子生成实体、关系与叙事主轴本体。"),
    LlmModuleDefinition("local_block_facts", "块内局部事实提取", "提取每个分析块内可证实的事件、实体与关系变化。"),
    LlmModuleDefinition("contextual_block_analysis", "前情快照剧情分析", "结合前情快照分析剧情块的状态变化与线程推进。"),
    LlmModuleDefinition("anchor_point_summary", "剧情锚点摘要", "在并发提取前生成区间级世界状态锚点。"),
    LlmModuleDefinition("entity_resolution", "实体消歧", "在全局故事记忆上判断相似实体是否应合并。"),
    LlmModuleDefinition("narrative_archives", "角色势力档案生成", "把实体转换为可用于推演的角色与组织档案。"),
    LlmModuleDefinition("parallel_world_config", "世界线起始配置生成", "根据变量与角色网络生成当前世界的起始设定草案。"),
    LlmModuleDefinition("worldline_agent_prepare", "世界线 Agent 整备", "为推演前的角色、组织与关系生成完整 dossier。"),
    LlmModuleDefinition("worldline_agent_dialogue", "世界线 Agent 对话", "为世界线角色或组织生成显式请求的对话回复。"),
    LlmModuleDefinition("worldline_agent_action", "世界线 Agent 自动动作", "为世界线自动演化生成每轮优先动作。"),
    LlmModuleDefinition("worldline_goal_evaluator", "世界线目标判定", "判断当前世界线是否达成创作者设定的自然语言目标。"),
    LlmModuleDefinition("novel_draft_writer", "小说正文创作", "基于上下文包和创作者指令，流式生成小说正文。"),
    LlmModuleDefinition("novel_draft_reviewer", "正文一致性审校", "检查生成的正文是否与已知设定、人物状态一致。"),
    LlmModuleDefinition("novel_chapter_summarizer", "章节卡生成", "逐章生成结构化章节卡，用于 continuity 派生与全量历史召回。"),
    LlmModuleDefinition("writer_orchestrator", "写作编排调度", "编排层：解析写作意图，调用工具收集小说设定数据，组装写作指令。"),
    LlmModuleDefinition("writer_composer", "写作正文生成", "写作层：基于编排层组装的写作指令，生成高质量小说正文。"),
    LlmModuleDefinition("writer_reviewer", "写作一致性审校", "后处理：检查生成正文与已知设定的一致性。"),
)

STAGE_TO_MODULE_KEY = {
    "anchor_generation": "anchor_point_summary",
    "extract_local_facts": "local_block_facts",
    "entity_resolution": "entity_resolution",
    "contextual_block_analysis": "contextual_block_analysis",
    "chapter_card_generation": "novel_chapter_summarizer",
    "ontology": "story_ontology",
}

MODULE_BY_KEY: Dict[str, LlmModuleDefinition] = {
    definition.module_key: definition for definition in MODULE_DEFINITIONS
}


def list_llm_modules() -> List[dict]:
    return [asdict(definition) for definition in MODULE_DEFINITIONS]


def get_llm_module(module_key: str) -> LlmModuleDefinition:
    module = MODULE_BY_KEY.get(module_key)
    if not module:
        raise ValueError(f"未知的 LLM 模块: {module_key}")
    return module
