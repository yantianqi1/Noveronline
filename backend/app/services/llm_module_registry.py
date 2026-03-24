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
    LlmModuleDefinition("worldline_agent_dialogue", "世界线 Agent 对话", "为世界线角色或组织生成显式请求的对话回复。"),
    LlmModuleDefinition("worldline_agent_action", "世界线 Agent 自动动作", "为世界线自动演化生成每轮优先动作。"),
    LlmModuleDefinition("worldline_goal_evaluator", "世界线目标判定", "判断当前世界线是否达成创作者设定的自然语言目标。"),
)

STAGE_TO_MODULE_KEY = {
    "anchor_generation": "anchor_point_summary",
    "extract_local_facts": "local_block_facts",
    "entity_resolution": "entity_resolution",
    "contextual_block_analysis": "contextual_block_analysis",
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
