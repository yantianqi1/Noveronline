"""
叙事实体档案生成器
把图谱实体转成适合小说推演的角色 / 势力 / 组织档案。
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .zep_entity_reader import EntityNode


ARCHIVE_SYSTEM_PROMPT = """你是一位小说角色圣经编辑、势力设定编辑和剧情结构分析师。

请根据单个实体的图谱信息，为它生成适合故事模拟的档案。

输出严格 JSON，格式如下：
{
  "importance_tier": "protagonist|major|supporting|minor",
  "entity_role": "中文，说明该角色/势力在故事中的功能定位",
  "core_drive": "中文，核心欲望 / 目标 / 立场",
  "surface_mask": "中文，表面形象或对外姿态",
  "hidden_tension": "中文，隐藏矛盾、秘密或潜在转折点",
  "relationship_summary": "中文，总结该实体与其他角色/组织的关键关系",
  "agent_behavior_hint": "中文，说明如果作为 agent，它会如何行动",
  "human_ai_relation_tag": "human|ai|hybrid|system|none",
  "notable_risks": ["风险1", "风险2"]
}
"""


@dataclass
class NarrativeEntityArchive:
    entity_uuid: str
    entity_name: str
    entity_type: str
    importance_tier: str
    entity_role: str
    core_drive: str
    surface_mask: str
    hidden_tension: str
    relationship_summary: str
    agent_behavior_hint: str
    human_ai_relation_tag: str
    notable_risks: List[str]
    can_act_as_agent: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NarrativeEntityArchivist:
    """为图谱实体生成小说档案。"""

    MODULE_KEY = "narrative_archives"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()

    def generate_archives_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
    ) -> List[NarrativeEntityArchive]:
        archives: List[NarrativeEntityArchive] = []
        for entity in entities:
            archives.append(self.generate_archive(entity, use_llm=use_llm))
        return archives

    def generate_archives_from_seed_analysis(self, seed_analysis: Dict[str, Any]) -> List[NarrativeEntityArchive]:
        relation_map: Dict[str, List[str]] = {}
        for relation in seed_analysis.get("relations", []):
            source = relation.get("source", "")
            target = relation.get("target", "")
            if source and target:
                relation_map.setdefault(source, []).append(target)
                relation_map.setdefault(target, []).append(source)

        archives: List[NarrativeEntityArchive] = []
        for item in seed_analysis.get("characters", []):
            name = item.get("name", "")
            archives.append(
                NarrativeEntityArchive(
                    entity_uuid=f"seed_character_{name}",
                    entity_name=name,
                    entity_type="Character",
                    importance_tier=item.get("importance_tier", "supporting"),
                    entity_role=item.get("identity_hint", "故事角色"),
                    core_drive="推动自己在主线中的目标",
                    surface_mask=item.get("identity_hint", "未明确"),
                    hidden_tension="可能被关系网络或隐藏信息反噬",
                    relationship_summary=self._seed_relation_summary(name, relation_map),
                    agent_behavior_hint="会根据当前局势、关系压力和个人目标行动",
                    human_ai_relation_tag="human",
                    notable_risks=["线索暴露", "立场误判"],
                )
            )

        for item in seed_analysis.get("organizations", []):
            name = item.get("name", "")
            archives.append(
                NarrativeEntityArchive(
                    entity_uuid=f"seed_org_{name}",
                    entity_name=name,
                    entity_type="Organization",
                    importance_tier=item.get("importance_tier", "major"),
                    entity_role=item.get("organization_type", "势力"),
                    core_drive="维持组织利益与权力秩序",
                    surface_mask=item.get("organization_type", "组织"),
                    hidden_tension="内部派系与外部压力可能引发失衡",
                    relationship_summary=self._seed_relation_summary(name, relation_map),
                    agent_behavior_hint="优先维护组织安全、资源与名义合法性",
                    human_ai_relation_tag="none",
                    notable_risks=["权力真空", "联盟破裂"],
                )
            )

        return archives

    def generate_archive(self, entity: EntityNode, use_llm: bool = True) -> NarrativeEntityArchive:
        entity_type = entity.get_entity_type() or "Unknown"
        if not use_llm:
            return self._build_offline_archive(entity, entity_type)

        user_message = f"""## 实体名
{entity.name}

## 实体类型
{entity_type}

## 实体摘要
{entity.summary}

## 属性
{entity.attributes}

## 相关节点
{entity.related_nodes[:15]}

## 相关边
{entity.related_edges[:20]}
"""

        client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
        result = client.chat_json_value(
            messages=[
                {"role": "system", "content": ARCHIVE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            max_tokens=1200,
        )
        result = normalize_json_object(result, "叙事实体档案生成")

        return NarrativeEntityArchive(
            entity_uuid=entity.uuid,
            entity_name=entity.name,
            entity_type=entity_type,
            importance_tier=result.get("importance_tier", "supporting"),
            entity_role=result.get("entity_role", ""),
            core_drive=result.get("core_drive", ""),
            surface_mask=result.get("surface_mask", ""),
            hidden_tension=result.get("hidden_tension", ""),
            relationship_summary=result.get("relationship_summary", self._summarize_relationships(entity)),
            agent_behavior_hint=result.get("agent_behavior_hint", ""),
            human_ai_relation_tag=result.get("human_ai_relation_tag", self._infer_human_ai_tag(entity_type, entity)),
            notable_risks=result.get("notable_risks", []),
        )

    def _build_offline_archive(self, entity: EntityNode, entity_type: str) -> NarrativeEntityArchive:
        return NarrativeEntityArchive(
            entity_uuid=entity.uuid,
            entity_name=entity.name,
            entity_type=entity_type,
            importance_tier="supporting",
            entity_role=entity.summary[:120] or f"{entity.name} 是故事中的 {entity_type}",
            core_drive="推动自身目标并回应外部变量",
            surface_mask="表面立场有待进一步观察",
            hidden_tension="显式离线模式下未生成更深层隐秘动机",
            relationship_summary=self._summarize_relationships(entity),
            agent_behavior_hint="会围绕当前关系网络和目标持续行动",
            human_ai_relation_tag=self._infer_human_ai_tag(entity_type, entity),
            notable_risks=["信息误判", "关系激化"],
        )

    def _summarize_relationships(self, entity: EntityNode) -> str:
        if not entity.related_nodes:
            return "图谱中暂无足够关系信息"
        related_names = [n.get("name", "") for n in entity.related_nodes[:8] if n.get("name")]
        return "关键关联对象：" + "、".join(related_names) if related_names else "图谱中暂无足够关系信息"

    def _infer_human_ai_tag(self, entity_type: str, entity: EntityNode) -> str:
        lowered = (entity_type or "").lower()
        text = f"{entity.name} {entity.summary} {entity.attributes}".lower()
        if any(k in lowered for k in ["organization", "faction", "group", "sect", "company", "guild", "宗门", "组织", "势力"]):
            return "none"
        if any(k in lowered or k in text for k in ["ai", "robot", "system", "digital", "android", "机械", "系统", "智能"]):
            return "ai"
        if "hybrid" in lowered:
            return "hybrid"
        return "human"

    def _seed_relation_summary(self, name: str, relation_map: Dict[str, List[str]]) -> str:
        related = relation_map.get(name, [])
        if not related:
            return "离线种子分析中暂未提取到稳定关系"
        return "关键关联对象：" + "、".join(related[:6])
