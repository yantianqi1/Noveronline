"""LLM 业务模块注册表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class LlmModuleDefinition:
    module_key: str
    label: str
    description: str
    example_prompt: str = ""
    example_output: str = ""


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
    LlmModuleDefinition("worldline_character_proposal", "角色自主提案", "每个角色独立思考并提出本步行动提案（行动或观望）。天道模式下每步每角色调用一次。"),
    LlmModuleDefinition("worldline_director", "世界线导演（天道裁决）", "裁决角色提案：检查冲突和合理性，维持因果律，输出客观叙事。绑定后启用天道模式。"),
    LlmModuleDefinition("worldline_agent_action", "世界线 Agent 自动动作（传统）", "传统模式：单次 LLM 调用生成动作。绑定导演 Agent 后不再使用。"),
    LlmModuleDefinition("worldline_goal_evaluator", "世界线目标判定", "判断当前世界线是否达成创作者设定的自然语言目标。"),
    LlmModuleDefinition("novel_chapter_summarizer", "章节卡生成", "逐章生成结构化章节卡，用于 continuity 派生与全量历史召回。"),
    LlmModuleDefinition("writer_orchestrator", "写作编排调度", "编排层：解析写作意图，调用工具收集小说设定数据，组装写作指令。"),
    LlmModuleDefinition("writer_composer", "写作正文生成", "写作层：基于编排层组装的写作指令，生成高质量小说正文。"),
    LlmModuleDefinition(
        module_key="style_extractor",
        label="文风提取",
        description="从整本小说全文中提炼写作风格、作家风格特征，写入资产库以供写作 agent 调用。",
        example_prompt="阅读以下文本片段，提炼其写作风格特征 (叙事视角/句式/修辞/节奏/词汇偏好/对白风格)...",
        example_output="JSON: pov, sentence, rhetoric, pacing, vocabulary, dialogue, examples...",
    ),
    LlmModuleDefinition(
        module_key="sequential_reading",
        label="顺序深度阅读",
        description="顺序精读每个段落，提取角色、关系、剧情线等结构化信息。",
        example_prompt="阅读当前段并分析角色、关系与剧情发展...",
        example_output="JSON: character_updates, relationship_changes, plot_threads...",
    ),
    LlmModuleDefinition(
        module_key="writer_retrieval_planner",
        label="写作检索规划员",
        description="在写作 agent 启动前规划必要的工具检索清单，不调用工具，仅输出 JSON 计划。",
        example_prompt="给定 task_type 和 context，列出该调用哪些工具",
        example_output="JSON: {rationale, calls: [{tool, arguments, reason}]}",
    ),
    LlmModuleDefinition(
        module_key="asset_ingestion",
        label="资产入库 Agent",
        description="对用户粘贴的原始素材做类型识别、结构化抽取与摘要分类，形成可被检索的资产条目。",
        example_prompt="判定下列文本属于哪类资产并抽取关键字段...",
        example_output="JSON: asset_type, title, summary, category, tags, payload",
    ),
    LlmModuleDefinition(
        module_key="character_agent_profile",
        label="角色 Agent 档案生成",
        description="为每个重要角色生成可直接用于 Agent 对话的完整档案。",
        example_prompt="根据阅读笔记为指定角色生成 Agent 档案...",
        example_output="JSON: personality, speech, relationships, knowledge_boundary...",
    ),
)

STAGE_TO_MODULE_KEY = {
    "anchor_generation": "anchor_point_summary",
    "extract_local_facts": "local_block_facts",
    "entity_resolution": "entity_resolution",
    "contextual_block_analysis": "contextual_block_analysis",
    "chapter_card_generation": "novel_chapter_summarizer",
    "ontology": "story_ontology",
    # New pipeline stages
    "sequential_reading": "sequential_reading",
    "agent_profiles": "character_agent_profile",
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
