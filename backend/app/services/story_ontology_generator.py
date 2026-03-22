"""
小说世界本体生成器
将长篇小说文本和创作目标转换为适用于故事图谱的实体与关系 schema。
"""

from typing import Callable, Dict, Any, List, Optional

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
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

输出结构：
{
  "entity_types": [
    {
      "name": "PascalCase",
      "description": "英文简短描述",
      "attributes": [
        {
          "name": "snake_case",
          "type": "text",
          "description": "属性说明"
        }
      ],
      "examples": ["示例1", "示例2"]
    }
  ],
  "edge_types": [
    {
      "name": "UPPER_SNAKE_CASE",
      "description": "英文简短描述",
      "source_targets": [
        {"source": "源实体类型", "target": "目标实体类型"}
      ],
      "attributes": []
    }
  ],
  "analysis_summary": "中文总结",
  "story_focus": [
    "该小说最值得追踪的叙事主轴1",
    "该小说最值得追踪的叙事主轴2"
  ]
}

约束：
- entity_types 输出 6-10 个
- edge_types 输出 6-10 个
- 必须包含 Character / Organization / Faction / PlotEvent 这类叙事核心类型，名称可细化
- 如果文本里有 AI、系统、机械、数字意识，必须专门设计对应实体类型
- 不要把纯抽象概念当成唯一核心实体，抽象概念更适合变成属性、事件或关系背景
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
        client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
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

    def _offline_ontology(self, combined_text: str, analysis_goal: str) -> Dict[str, Any]:
        has_ai = any(keyword in combined_text for keyword in ["AI", "系统", "机械", "智能", "算法", "数字意识"])
        entity_types = [
            {
                "name": "Character",
                "description": "Named story character",
                "attributes": [
                    {"name": "importance_tier", "type": "text", "description": "Narrative importance"},
                    {"name": "identity_hint", "type": "text", "description": "Likely identity in story"},
                ],
                "examples": ["主角", "反派", "关键配角"],
            },
            {
                "name": "Organization",
                "description": "Faction, sect, company or institution",
                "attributes": [
                    {"name": "organization_type", "type": "text", "description": "Kind of organization"},
                ],
                "examples": ["宗门", "公司", "协会"],
            },
            {
                "name": "Faction",
                "description": "Competing force or camp",
                "attributes": [],
                "examples": ["正道阵营", "地下联盟"],
            },
            {
                "name": "PlotEvent",
                "description": "Important plot event",
                "attributes": [
                    {"name": "trigger", "type": "text", "description": "Event trigger"},
                ],
                "examples": ["宗门试炼", "政变", "失踪案"],
            },
            {
                "name": "Location",
                "description": "Important location",
                "attributes": [],
                "examples": ["都城", "山门", "研究所"],
            },
            {
                "name": "Artifact",
                "description": "Key object or clue",
                "attributes": [],
                "examples": ["玉简", "芯片", "密信"],
            },
            {
                "name": "RuleSystem",
                "description": "Magic, law or technical system",
                "attributes": [],
                "examples": ["修炼体系", "公司规则", "安全协议"],
            },
        ]
        if has_ai:
            entity_types.append(
                {
                    "name": "AIAgent",
                    "description": "AI, system or digital consciousness",
                    "attributes": [],
                    "examples": ["系统", "数字人格"],
                }
            )

        edge_types = [
            {
                "name": "KNOWS",
                "description": "Characters know each other",
                "source_targets": [{"source": "Character", "target": "Character"}],
                "attributes": [],
            },
            {
                "name": "BELONGS_TO",
                "description": "Entity belongs to organization",
                "source_targets": [{"source": "Character", "target": "Organization"}],
                "attributes": [],
            },
            {
                "name": "CONFLICTS_WITH",
                "description": "Conflict relationship",
                "source_targets": [{"source": "Character", "target": "Character"}],
                "attributes": [],
            },
            {
                "name": "ALLIED_WITH",
                "description": "Alliance relationship",
                "source_targets": [{"source": "Organization", "target": "Organization"}],
                "attributes": [],
            },
            {
                "name": "PARTICIPATES_IN",
                "description": "Actor involved in event",
                "source_targets": [{"source": "Character", "target": "PlotEvent"}],
                "attributes": [],
            },
            {
                "name": "TAKES_PLACE_IN",
                "description": "Event location",
                "source_targets": [{"source": "PlotEvent", "target": "Location"}],
                "attributes": [],
            },
            {
                "name": "SEEKS",
                "description": "Goal or object pursuit",
                "source_targets": [{"source": "Character", "target": "Artifact"}],
                "attributes": [],
            },
            {
                "name": "OBEYS_RULE",
                "description": "Entity under system rules",
                "source_targets": [{"source": "Character", "target": "RuleSystem"}],
                "attributes": [],
            },
        ]
        if has_ai:
            edge_types.append(
                {
                    "name": "INTERACTS_WITH_AI",
                    "description": "Human and AI relation",
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
