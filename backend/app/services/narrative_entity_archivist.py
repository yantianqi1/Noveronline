"""
叙事实体档案生成器
把图谱实体转成适合小说推演的角色 / 势力 / 组织档案。
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .agent_template_registry import AgentTemplateRegistry
from .archive_candidate_builder import ArchiveCandidateBuilder
from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .zep_entity_reader import EntityNode


TEXT_DETAIL_DEFAULT = "图谱未提供"
LIST_DETAIL_DEFAULT = "图谱未提供"

ARCHIVE_SYSTEM_PROMPT = """你是一位小说角色圣经编辑、势力设定编辑和剧情结构分析师。

请根据单个实体的图谱信息，为它生成适合故事模拟与 Agent 推演的结构化档案。

硬性要求：
1. 只输出一个 JSON 对象，不要输出解释或 Markdown。
2. 每个字段都必须具体、可执行、可用于后续角色对话或自动动作。
3. 禁止空话或套话，例如“性格复杂”“关系紧张”“会随机应变”“势力庞大”。
4. 各字段不要重复改写同一句话；`entity_role`、`core_drive`、`hidden_tension`、`agent_behavior_hint` 必须各自承担不同信息。
5. 信息不足时，显式写“图谱未提供”“证据不足”或“暂不可判定”，不要留空。
6. 所有数组字段至少输出 1 项；无法判断时填入显式未知项。

通用字段必须始终输出：
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

如果推定 agent_kind=character，额外输出：
{
  "personality": "中文，稳定性格底色，不能重复 surface_mask",
  "skills": ["中文，关键能力或手段"],
  "loyalty": "中文，优先忠于谁/什么",
  "secrets": ["中文，隐藏事实、筹码或禁忌"],
  "long_term_goal": "中文，长期目标",
  "short_term_goal": "中文，当前阶段最优先目标"
}

如果推定 agent_kind=organization，额外输出：
{
  "resources": ["中文，核心资源、机构、资产或渠道"],
  "internal_factions": ["中文，内部派系或权力板块"],
  "territorial_control": "中文，势力控制范围",
  "public_stance": "中文，对外公开立场",
  "strategic_goal": "中文，组织级长期策略目标",
  "conflict_targets": ["中文，当前主要冲突对象"]
}

如果推定 agent_kind=relationship，额外输出：
{
  "history": "中文，关系历史或形成过程",
  "power_dynamic": "中文，谁更强势、谁握筹码",
  "trust_level": "中文，当前信任程度",
  "conflict_trigger": "中文，最可能引爆关系变化的触发点",
  "stability_forecast": "中文，未来短期稳定性判断",
  "last_action": "中文，最近一次影响关系走势的动作"
}
"""


@dataclass
class NarrativeEntityArchive:
    entity_uuid: str
    entity_name: str
    entity_type: str
    agent_kind: str
    importance_tier: str
    recommended_importance_tier: str
    selected_importance_tier: str
    template_key: str
    template_version: str
    template_sections: List[str]
    template_payload: Dict[str, Any]
    template_metadata: Dict[str, Any]
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
        template_registry: Optional[AgentTemplateRegistry] = None,
        candidate_builder: Optional[ArchiveCandidateBuilder] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()
        self.template_registry = template_registry or AgentTemplateRegistry()
        self.candidate_builder = candidate_builder or ArchiveCandidateBuilder(self.template_registry)

    def generate_archives_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        tier_overrides: Optional[Dict[str, str]] = None,
    ) -> List[NarrativeEntityArchive]:
        candidates = self.candidate_builder.build_from_entities(entities)
        entity_lookup = {item.uuid: item for item in entities}
        return self.generate_archives_from_candidates(candidates, use_llm=use_llm, tier_overrides=tier_overrides, entity_lookup=entity_lookup)

    def generate_archives_from_seed_analysis(
        self,
        seed_analysis: Dict[str, Any],
        tier_overrides: Optional[Dict[str, str]] = None,
    ) -> List[NarrativeEntityArchive]:
        candidates = self.candidate_builder.build_from_seed_analysis(seed_analysis)
        return self.generate_archives_from_candidates(candidates, use_llm=False, tier_overrides=tier_overrides)

    def generate_archives_from_candidates(
        self,
        candidates: List[Dict[str, Any]],
        use_llm: bool = True,
        tier_overrides: Optional[Dict[str, str]] = None,
        entity_lookup: Optional[Dict[str, EntityNode]] = None,
    ) -> List[NarrativeEntityArchive]:
        archives = []
        overrides = tier_overrides or {}
        entity_lookup = entity_lookup or {}
        for candidate in candidates:
            selected_tier = overrides.get(candidate["entity_uuid"], candidate.get("selected_importance_tier", "supporting"))
            recommended_tier = candidate.get("recommended_importance_tier", selected_tier)
            agent_kind = candidate.get("agent_kind", "generic")
            entity = entity_lookup.get(candidate["entity_uuid"])
            if agent_kind == "relationship":
                archives.append(self._build_relationship_archive(candidate, selected_tier, recommended_tier))
                continue
            if entity:
                archives.append(
                    self.generate_archive(
                        entity,
                        use_llm=use_llm,
                        selected_importance_tier=selected_tier,
                        recommended_importance_tier=recommended_tier,
                        agent_kind_override=agent_kind,
                    )
                )
                continue
            archives.append(self._build_candidate_archive(candidate, selected_tier, recommended_tier))
        return archives

    def generate_archive(
        self,
        entity: EntityNode,
        use_llm: bool = True,
        selected_importance_tier: str = "",
        recommended_importance_tier: str = "",
        agent_kind_override: str = "",
    ) -> NarrativeEntityArchive:
        entity_type = entity.get_entity_type() or "Unknown"
        agent_kind = agent_kind_override or self.candidate_builder._infer_agent_kind(entity_type)
        if not use_llm:
            return self._build_offline_archive(
                entity,
                entity_type,
                agent_kind,
                selected_importance_tier=selected_importance_tier,
                recommended_importance_tier=recommended_importance_tier,
            )

        user_message = f"""## 实体名
{entity.name}

## 实体类型
{entity_type}

## 推定 agent 类型
{agent_kind}

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
            max_tokens=1600,
        )
        result = normalize_json_object(result, "叙事实体档案生成")

        return self._compose_archive(
            entity_uuid=entity.uuid,
            entity_name=entity.name,
            entity_type=entity_type,
            agent_kind=agent_kind,
            importance_tier=selected_importance_tier or result.get("importance_tier", "supporting"),
            recommended_importance_tier=recommended_importance_tier or result.get("importance_tier", "supporting"),
            entity_role=result.get("entity_role", ""),
            core_drive=result.get("core_drive", ""),
            surface_mask=result.get("surface_mask", ""),
            hidden_tension=result.get("hidden_tension", ""),
            relationship_summary=result.get("relationship_summary", self._summarize_relationships(entity)),
            agent_behavior_hint=result.get("agent_behavior_hint", ""),
            human_ai_relation_tag=result.get("human_ai_relation_tag", self._infer_human_ai_tag(entity_type, entity)),
            notable_risks=result.get("notable_risks", []),
            source_payload=self._entity_source_payload(entity, agent_kind, result),
        )

    def _build_offline_archive(
        self,
        entity: EntityNode,
        entity_type: str,
        agent_kind: str,
        selected_importance_tier: str = "",
        recommended_importance_tier: str = "",
    ) -> NarrativeEntityArchive:
        selected = selected_importance_tier or entity.attributes.get("importance_tier", "supporting")
        recommended = recommended_importance_tier or entity.attributes.get("importance_tier", selected)
        return self._compose_archive(
            entity_uuid=entity.uuid,
            entity_name=entity.name,
            entity_type=entity_type,
            agent_kind=agent_kind,
            importance_tier=selected,
            recommended_importance_tier=recommended,
            entity_role=entity.summary or f"{entity.name} 是故事中的 {entity_type}",
            core_drive="推动自身目标并回应外部变量",
            surface_mask="表面立场有待进一步观察",
            hidden_tension="显式离线模式下未生成更深层隐秘动机",
            relationship_summary=self._summarize_relationships(entity),
            agent_behavior_hint="会围绕当前关系网络和目标持续行动",
            human_ai_relation_tag=self._infer_human_ai_tag(entity_type, entity),
            notable_risks=["信息误判", "关系激化"],
            source_payload=self._entity_source_payload(entity, agent_kind),
        )

    def _build_candidate_archive(
        self,
        candidate: Dict[str, Any],
        selected_importance_tier: str,
        recommended_importance_tier: str,
    ) -> NarrativeEntityArchive:
        source_payload = candidate.get("source_payload", {})
        entity_type = candidate.get("entity_type", "Unknown")
        name = candidate.get("display_name", "")
        agent_kind = candidate.get("agent_kind", "generic")
        return self._compose_archive(
            entity_uuid=candidate["entity_uuid"],
            entity_name=name,
            entity_type=entity_type,
            agent_kind=agent_kind,
            importance_tier=selected_importance_tier,
            recommended_importance_tier=recommended_importance_tier,
            entity_role=source_payload.get("identity_hint") or source_payload.get("organization_type") or source_payload.get("role") or entity_type,
            core_drive="推动自己在主线中的目标" if agent_kind == "character" else "维持当前立场",
            surface_mask=source_payload.get("identity_hint") or source_payload.get("organization_type") or entity_type,
            hidden_tension=candidate.get("summary", ""),
            relationship_summary=candidate.get("summary", ""),
            agent_behavior_hint="会围绕当前关系网络和目标持续行动",
            human_ai_relation_tag="none" if agent_kind == "organization" else "human",
            notable_risks=["信息误判"],
            source_payload=self._candidate_source_payload(agent_kind, source_payload),
            source_kind=candidate.get("source_kind", "candidate"),
        )

    def _build_relationship_archive(
        self,
        candidate: Dict[str, Any],
        selected_importance_tier: str,
        recommended_importance_tier: str,
    ) -> NarrativeEntityArchive:
        payload = candidate.get("source_payload", {})
        source = payload.get("source", "")
        target = payload.get("target", "")
        relation_type = payload.get("relation_type", "co_occurrence")
        summary = candidate.get("summary", "") or f"{source} 与 {target} 存在 {relation_type}"
        return self._compose_archive(
            entity_uuid=candidate["entity_uuid"],
            entity_name=candidate.get("display_name", ""),
            entity_type="Relationship",
            agent_kind="relationship",
            importance_tier=selected_importance_tier,
            recommended_importance_tier=recommended_importance_tier,
            entity_role="关系推动者",
            core_drive=f"推动“{source}”与“{target}”之间的关系继续演化",
            surface_mask=relation_type,
            hidden_tension=summary,
            relationship_summary=summary,
            agent_behavior_hint=f"会围绕 {source} 与 {target} 的关系变化采取动作",
            human_ai_relation_tag="none",
            notable_risks=["关系失衡", "信任崩塌"],
            source_payload=self._relationship_source_payload(payload, summary),
            source_kind=candidate.get("source_kind", "relationship"),
        )

    def _compose_archive(
        self,
        entity_uuid: str,
        entity_name: str,
        entity_type: str,
        agent_kind: str,
        importance_tier: str,
        recommended_importance_tier: str,
        entity_role: str,
        core_drive: str,
        surface_mask: str,
        hidden_tension: str,
        relationship_summary: str,
        agent_behavior_hint: str,
        human_ai_relation_tag: str,
        notable_risks: List[str],
        source_payload: Optional[Dict[str, Any]] = None,
        source_kind: str = "archive_generation",
    ) -> NarrativeEntityArchive:
        template = self.template_registry.describe(agent_kind, importance_tier)
        payload = self._template_payload(
            template["agent_kind"],
            template["template_sections"],
            {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "entity_role": entity_role,
                "core_drive": core_drive,
                "surface_mask": surface_mask,
                "hidden_tension": hidden_tension,
                "relationship_summary": relationship_summary,
                "agent_behavior_hint": agent_behavior_hint,
                "human_ai_relation_tag": human_ai_relation_tag,
                "notable_risks": notable_risks,
                "can_act_as_agent": True,
                **(source_payload or {}),
            },
        )
        metadata = {
            "version": template["template_version"],
            "recommended_importance_tier": self.template_registry.normalize_tier(recommended_importance_tier),
            "selected_importance_tier": template["importance_tier"],
            "user_override": self.template_registry.normalize_tier(recommended_importance_tier) != template["importance_tier"],
            "source": source_kind,
        }
        return NarrativeEntityArchive(
            entity_uuid=entity_uuid,
            entity_name=entity_name,
            entity_type=entity_type,
            agent_kind=template["agent_kind"],
            importance_tier=template["importance_tier"],
            recommended_importance_tier=metadata["recommended_importance_tier"],
            selected_importance_tier=template["importance_tier"],
            template_key=template["template_key"],
            template_version=template["template_version"],
            template_sections=list(template["template_sections"]),
            template_payload=payload,
            template_metadata=metadata,
            entity_role=entity_role,
            core_drive=core_drive,
            surface_mask=surface_mask,
            hidden_tension=hidden_tension,
            relationship_summary=relationship_summary,
            agent_behavior_hint=agent_behavior_hint,
            human_ai_relation_tag=human_ai_relation_tag,
            notable_risks=list(notable_risks),
            can_act_as_agent=True,
        )

    def _template_payload(self, agent_kind: str, sections: List[str], values: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for section in sections:
            if section == "identity":
                payload[section] = self._identity_section(agent_kind, values)
            elif section == "motivation":
                payload[section] = {"core_drive": values.get("core_drive", "")}
            elif section == "tension":
                payload[section] = {"hidden_tension": values.get("hidden_tension", "")}
            elif section == "relationship":
                payload[section] = self._relationship_section(agent_kind, values)
            elif section == "behavior":
                payload[section] = self._behavior_section(agent_kind, values)
            elif section == "state":
                payload[section] = self._state_section(values)
            elif section == "risk":
                payload[section] = {"notable_risks": list(values.get("notable_risks", []))}
            elif section == "private":
                payload[section] = self._private_section(agent_kind, values)
            elif section == "summary":
                payload[section] = {"summary": values.get("relationship_summary") or values.get("hidden_tension", "")}
        return payload

    def _identity_section(self, agent_kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        section = {
            "entity_name": values.get("entity_name", ""),
            "entity_type": values.get("entity_type", ""),
            "role": values.get("entity_role", ""),
        }
        if agent_kind == "character" and values.get("identity_hint"):
            section["identity_hint"] = values["identity_hint"]
        if agent_kind == "organization" and values.get("organization_type"):
            section["organization_type"] = values["organization_type"]
        if agent_kind == "relationship":
            section["source"] = values.get("source", "")
            section["target"] = values.get("target", "")
        return section

    def _relationship_section(self, agent_kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        section = {"summary": values.get("relationship_summary", "")}
        if agent_kind == "relationship":
            section.update({
                "source": values.get("source", ""),
                "target": values.get("target", ""),
                "change": values.get("relation_type", "co_occurrence"),
                "history": values.get("history", values.get("relationship_summary", "")),
                "power_dynamic": values.get("power_dynamic", ""),
                "trust_level": values.get("trust_level", ""),
                "conflict_trigger": values.get("conflict_trigger", ""),
                "stability_forecast": values.get("stability_forecast", ""),
                "last_action": values.get("last_action", ""),
            })
        return section

    def _behavior_section(self, agent_kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        section = {"agent_behavior_hint": values.get("agent_behavior_hint", "")}
        if agent_kind == "character":
            section.update({
                "personality": values.get("personality", ""),
                "skills": values.get("skills", []),
                "loyalty": values.get("loyalty", ""),
                "long_term_goal": values.get("long_term_goal", ""),
                "short_term_goal": values.get("short_term_goal", ""),
            })
        if agent_kind == "organization":
            section.update({
                "resources": values.get("resources", []),
                "internal_factions": values.get("internal_factions", []),
                "public_stance": values.get("public_stance", ""),
                "strategic_goal": values.get("strategic_goal", ""),
                "conflict_targets": values.get("conflict_targets", []),
            })
        return section

    def _state_section(self, values: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": values.get("status", "active"),
            "surface_mask": values.get("surface_mask", ""),
            "can_act_as_agent": bool(values.get("can_act_as_agent", True)),
        }

    def _private_section(self, agent_kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        section = {
            "surface_mask": values.get("surface_mask", ""),
            "human_ai_relation_tag": values.get("human_ai_relation_tag", "none"),
        }
        if agent_kind == "character":
            section["secrets"] = values.get("secrets", [])
        if agent_kind == "organization":
            section["territorial_control"] = values.get("territorial_control", "")
        return section

    def _entity_source_payload(
        self,
        entity: EntityNode,
        agent_kind: str,
        llm_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(entity.attributes or {})
        payload.update(self._detail_fields(agent_kind, llm_result or {}))
        return payload

    def _candidate_source_payload(self, agent_kind: str, source_payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(source_payload or {})
        payload.update(self._detail_fields(agent_kind, payload))
        return payload

    def _relationship_source_payload(self, source_payload: Dict[str, Any], summary: str) -> Dict[str, Any]:
        payload = dict(source_payload or {})
        payload.update({
            "history": self._detail_text(payload.get("history"), summary or TEXT_DETAIL_DEFAULT),
            "power_dynamic": self._detail_text(payload.get("power_dynamic"), "双方主导权仍在重新分配"),
            "trust_level": self._detail_text(payload.get("trust_level"), "证据不足"),
            "conflict_trigger": self._detail_text(payload.get("conflict_trigger"), "下一次关键利益冲突"),
            "stability_forecast": self._detail_text(payload.get("stability_forecast"), "短期内仍会继续偏移"),
            "last_action": self._detail_text(payload.get("last_action"), "图谱未提供最近动作"),
        })
        return payload

    def _detail_fields(self, agent_kind: str, source: Dict[str, Any]) -> Dict[str, Any]:
        if agent_kind == "character":
            return {
                "personality": self._detail_text(source.get("personality")),
                "skills": self._detail_list(source.get("skills")),
                "loyalty": self._detail_text(source.get("loyalty")),
                "secrets": self._detail_list(source.get("secrets")),
                "long_term_goal": self._detail_text(source.get("long_term_goal")),
                "short_term_goal": self._detail_text(source.get("short_term_goal")),
            }
        if agent_kind == "organization":
            return {
                "resources": self._detail_list(source.get("resources")),
                "internal_factions": self._detail_list(source.get("internal_factions")),
                "territorial_control": self._detail_text(source.get("territorial_control")),
                "public_stance": self._detail_text(source.get("public_stance")),
                "strategic_goal": self._detail_text(source.get("strategic_goal")),
                "conflict_targets": self._detail_list(source.get("conflict_targets")),
            }
        if agent_kind == "relationship":
            return {
                "history": self._detail_text(source.get("history")),
                "power_dynamic": self._detail_text(source.get("power_dynamic")),
                "trust_level": self._detail_text(source.get("trust_level")),
                "conflict_trigger": self._detail_text(source.get("conflict_trigger")),
                "stability_forecast": self._detail_text(source.get("stability_forecast")),
                "last_action": self._detail_text(source.get("last_action")),
            }
        return {}

    def _detail_text(self, value: Any, default: str = TEXT_DETAIL_DEFAULT) -> str:
        text = str(value or "").strip()
        return text or default

    def _detail_list(self, value: Any, default: str = LIST_DETAIL_DEFAULT) -> List[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or [default]
        text = str(value or "").strip()
        return [text] if text else [default]

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
