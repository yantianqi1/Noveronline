"""
小说世界本体生成器
将长篇小说文本和创作目标转换为适用于故事图谱的实体与关系 schema。
"""

from typing import Callable, Dict, Any, List, Optional

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .seed_stage_fallback_support import attach_rule_fallback, should_use_rule_fallback, summarize_stage_failure
from .story_ontology_line_protocol import StoryOntologyLineProtocolExecutor
from .story_context_source_builder import build_story_context_source


STORY_ONTOLOGY_SYSTEM_PROMPT = """你是一位专业的小说结构分析师、世界观建模师和叙事图谱设计专家。

你的任务是分析给定的小说文本、设定和创作目标，设计一个适合“故事演化模拟”的本体。

你必须输出严格有效的 JSON，不要输出任何额外说明。

## 系统目标

这个系统不是做舆情分析，而是做：
- 角色关系演化
- 组织 / 阵营 / 势力博弈
- 剧情分支推演
- 人机关系演化
- 平行世界变量注入

## 实体类型设计原则

优先覆盖以下对象：
- 有名字的人物
- AI / 系统 / 机械生命 / 数字意识
- 组织、宗门、公司、团体、势力、流派
- 地点、重要物件、规则系统
- 情节事件、冲突、目标、关系弧线

设计要求：
- entity_types 的 attributes 必须是该类型在"剧情推演"中需要追踪的动态变量，不要列出静态描述性属性
- edge_types 必须能表达"随剧情变化而改变"的动态关系，避免纯静态分类关系
- 每个 entity_type 至少包含 2 个 attributes
- 每个 attribute 必须有具体的 type（text / number / enum / boolean）

输出结构：
{
  "entity_types": [
    {
      "name": "PascalCase命名",
      "description": "中文简短描述，说明这个类型在故事推演中的作用",
      "attributes": [
        {
          "name": "snake_case",
          "type": "text 或 number 或 enum 或 boolean",
          "description": "中文，说明这个属性如何影响剧情推演"
        }
      ],
      "examples": ["来自原文的具体实例名1", "来自原文的具体实例名2"]
    }
  ],
  "edge_types": [
    {
      "name": "UPPER_SNAKE_CASE",
      "description": "中文简短描述",
      "source_targets": [
        {"source": "源实体类型名", "target": "目标实体类型名"}
      ],
      "attributes": []
    }
  ],
  "analysis_summary": "中文，100-200字，总结这部小说的核心叙事结构和适合追踪的演化维度",
  "story_focus": [
    "具体可追踪的叙事主轴，格式：[追踪对象] 的 [变化维度]"
  ]
}

约束：
- entity_types 输出 6-10 个
- edge_types 输出 6-10 个
- 必须包含 Character / Organization / Faction / PlotEvent 这类叙事核心类型，名称可细化
- 如果文本里有 AI、系统、机械、数字意识，必须专门设计对应实体类型
- 不要把纯抽象概念当成唯一核心实体，抽象概念更适合变成属性、事件或关系背景
- examples 必须来自给定的小说材料，不要编造不存在的名字

## 输出示范（仅供参考格式，实际输出应基于给定的小说材料）
{
  "entity_types": [
    {
      "name": "Character",
      "description": "故事中的命名角色，追踪其战力、立场和关键抉择",
      "attributes": [
        {"name": "combat_level", "type": "text", "description": "角色当前战力等级，影响冲突胜负推演"},
        {"name": "faction_loyalty", "type": "enum", "description": "对所属势力的忠诚度：loyal/wavering/defected，影响阵营博弈"},
        {"name": "hidden_identity", "type": "text", "description": "角色的隐藏身份或秘密，可能引发剧情反转"}
      ],
      "examples": ["沈渊", "柳如烟"]
    },
    {
      "name": "PlotEvent",
      "description": "推动剧情的关键事件，追踪其触发条件和连锁反应",
      "attributes": [
        {"name": "trigger", "type": "text", "description": "事件触发条件"},
        {"name": "impact_scope", "type": "enum", "description": "影响范围：personal/faction/world，用于评估事件传播"}
      ],
      "examples": ["玄天塔试炼", "暗影组织伏击"]
    }
  ],
  "edge_types": [
    {
      "name": "ALLEGIANCE",
      "description": "角色对组织/阵营的效忠关系，可随剧情变化",
      "source_targets": [{"source": "Character", "target": "Organization"}],
      "attributes": [
        {"name": "loyalty_level", "type": "enum", "description": "忠诚度: loyal/strained/broken"},
        {"name": "since_event", "type": "text", "description": "建立或最近变化的触发事件"}
      ]
    },
    {
      "name": "CONFLICTS_WITH",
      "description": "角色或组织间的敌对关系，追踪冲突来源和强度",
      "source_targets": [{"source": "Character", "target": "Character"}, {"source": "Organization", "target": "Organization"}],
      "attributes": [
        {"name": "conflict_origin", "type": "text", "description": "冲突起因"}
      ]
    }
  ],
  "analysis_summary": "这部仙侠小说核心围绕沈渊的成长与上古禁术的代价展开，涉及苍澜宗内部权力斗争和暗影组织的渗透。适合追踪的演化维度包括：角色实力的非线性成长、组织间的博弈均衡、以及禁术使用对角色命运的长期影响。",
  "story_focus": [
    "沈渊的禁术实力成长与身体代价之间的平衡",
    "苍澜宗内部长老会的路线分裂走向",
    "柳如烟的隐藏身份揭露后对主角团关系的冲击"
  ]
}
"""


class StoryOntologyGenerator:
    """小说专用 ontology 生成器"""

    MAX_TEXT_LENGTH_FOR_LLM = 60000
    MODULE_KEY = "story_ontology"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()

    def generate(
        self,
        document_texts: List[str],
        analysis_goal: str,
        additional_context: Optional[str] = None,
        use_llm: bool = True,
        chapter_continuity: Optional[Dict[str, Any]] = None,
        story_memory: Optional[Dict[str, Any]] = None,
        block_analyses: Optional[List[Dict[str, Any]]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        combined_text = "\n\n---\n\n".join(document_texts)
        llm_source = build_story_context_source(
            max_length=self.MAX_TEXT_LENGTH_FOR_LLM,
            combined_text=combined_text,
            chapter_continuity=chapter_continuity,
            story_memory=story_memory,
            block_analyses=block_analyses,
        )

        user_message = f"""## 小说材料
{llm_source}

## 分析目标
{analysis_goal}
"""

        if additional_context:
            user_message += f"\n## 额外说明\n{additional_context}\n"

        messages = [
            {"role": "system", "content": STORY_ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        if not use_llm:
            if progress_callback:
                progress_callback("offline", {"summary_length": len(llm_source)})
            return self._offline_ontology(combined_text, analysis_goal)
        if progress_callback:
            progress_callback("start", {"summary_length": len(llm_source)})
        try:
            client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
            if hasattr(client, "chat"):
                payload = StoryOntologyLineProtocolExecutor(client).generate(user_message)
                if progress_callback:
                    progress_callback(
                        "complete",
                        {
                            "entity_type_count": len(payload.get("entity_types", [])),
                            "edge_type_count": len(payload.get("edge_types", [])),
                        },
                    )
                return payload
            payload = client.chat_json_value(messages=messages, temperature=0.3, max_tokens=4096)
            payload = normalize_json_object(payload, "小说本体生成")
            if progress_callback:
                progress_callback(
                    "complete",
                    {
                        "entity_type_count": len(payload.get("entity_types", [])),
                        "edge_type_count": len(payload.get("edge_types", [])),
                    },
                )
            return payload
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            payload = attach_rule_fallback(
                self._offline_ontology(combined_text, analysis_goal),
                exc,
                mode="offline_fallback",
            )
            if progress_callback:
                progress_callback(
                    "complete",
                    {
                        "entity_type_count": len(payload.get("entity_types", [])),
                        "edge_type_count": len(payload.get("edge_types", [])),
                    },
                )
            return payload

    def _offline_ontology(self, combined_text: str, analysis_goal: str) -> Dict[str, Any]:
        has_ai = any(keyword in combined_text for keyword in ["AI", "系统", "机械", "智能", "算法", "数字意识"])
        entity_types = [
            {
                "name": "Character",
                "description": "故事中的命名角色，追踪其行为、状态和关键抉择",
                "attributes": [
                    {"name": "importance_tier", "type": "text", "description": "角色在叙事中的重要性层级"},
                    {"name": "identity_hint", "type": "text", "description": "角色在故事中可能的身份线索"},
                ],
                "examples": ["主角", "反派", "关键配角"],
            },
            {
                "name": "Organization",
                "description": "宗门、公司、团体等组织实体，追踪其内部变化和外部博弈",
                "attributes": [
                    {"name": "organization_type", "type": "text", "description": "组织的具体类型分类"},
                ],
                "examples": ["宗门", "公司", "协会"],
            },
            {
                "name": "Faction",
                "description": "对立或竞争的势力阵营，追踪其立场和博弈态势",
                "attributes": [],
                "examples": ["正道阵营", "地下联盟"],
            },
            {
                "name": "PlotEvent",
                "description": "推动剧情的关键事件，追踪其触发条件和连锁反应",
                "attributes": [
                    {"name": "trigger", "type": "text", "description": "事件触发条件"},
                ],
                "examples": ["宗门试炼", "政变", "失踪案"],
            },
            {
                "name": "Location",
                "description": "故事中的重要地点，影响角色行动和事件发生",
                "attributes": [],
                "examples": ["都城", "山门", "研究所"],
            },
            {
                "name": "Artifact",
                "description": "关键物品或线索，可能影响剧情走向",
                "attributes": [],
                "examples": ["玉简", "芯片", "密信"],
            },
            {
                "name": "RuleSystem",
                "description": "修炼体系、法律或技术系统等规则框架",
                "attributes": [],
                "examples": ["修炼体系", "公司规则", "安全协议"],
            },
        ]
        if has_ai:
            entity_types.append(
                {
                    "name": "AIAgent",
                    "description": "AI、系统或数字意识实体，追踪其与人类的交互和自主行为",
                    "attributes": [],
                    "examples": ["系统", "数字人格"],
                }
            )

        edge_types = [
            {
                "name": "KNOWS",
                "description": "角色之间的认识关系",
                "source_targets": [{"source": "Character", "target": "Character"}],
                "attributes": [],
            },
            {
                "name": "BELONGS_TO",
                "description": "角色隶属于组织的从属关系",
                "source_targets": [{"source": "Character", "target": "Organization"}],
                "attributes": [],
            },
            {
                "name": "CONFLICTS_WITH",
                "description": "角色或组织间的敌对冲突关系",
                "source_targets": [{"source": "Character", "target": "Character"}],
                "attributes": [],
            },
            {
                "name": "ALLIED_WITH",
                "description": "组织间的同盟合作关系",
                "source_targets": [{"source": "Organization", "target": "Organization"}],
                "attributes": [],
            },
            {
                "name": "PARTICIPATES_IN",
                "description": "角色参与事件的关联关系",
                "source_targets": [{"source": "Character", "target": "PlotEvent"}],
                "attributes": [],
            },
            {
                "name": "TAKES_PLACE_IN",
                "description": "事件发生的地点关联",
                "source_targets": [{"source": "PlotEvent", "target": "Location"}],
                "attributes": [],
            },
            {
                "name": "SEEKS",
                "description": "角色追寻目标或物品的关系",
                "source_targets": [{"source": "Character", "target": "Artifact"}],
                "attributes": [],
            },
            {
                "name": "OBEYS_RULE",
                "description": "角色受规则体系约束的关系",
                "source_targets": [{"source": "Character", "target": "RuleSystem"}],
                "attributes": [],
            },
        ]
        if has_ai:
            edge_types.append(
                {
                    "name": "INTERACTS_WITH_AI",
                    "description": "人类与AI实体的交互关系",
                    "source_targets": [{"source": "Character", "target": "AIAgent"}],
                    "attributes": [],
                }
            )

        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "analysis_summary": "当前使用显式离线 ontology，可先进行角色/组织/关系提取与世界线推演。",
            "story_focus": [
                analysis_goal or "观察角色关系如何在变量注入后演化",
                "追踪组织博弈与关键事件联动",
            ],
        }
