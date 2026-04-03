import re

from app.services.llm_router import LlmRouter


BLOCK_ID_PATTERN = re.compile(r"block_id:\s*(block_\d+)")
OWNED_CHAPTERS_PATTERN = re.compile(r"owned_chapters:\s*\[(.*?)\]")


class FakeSeedLlmClient:
    def __init__(self, module_key, state):
        self.module_key = module_key
        self.state = state

    def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
        user_message = messages[-1]["content"]
        if self.module_key == "anchor_point_summary":
            return self._anchor_payload()
        if self.module_key == "local_block_facts":
            return self._local_block_payload(user_message)
        if self.module_key == "contextual_block_analysis":
            return self._contextual_payload(user_message)
        if self.module_key == "entity_resolution":
            return self._entity_resolution_payload(user_message)
        if self.module_key == "novel_chapter_summarizer":
            return self._chapter_card_payload(user_message)
        if self.module_key == "story_ontology":
            return self._ontology_payload()
        if self.module_key == "sequential_reading" and "弧线摘要" in (messages[0].get("content", "") if messages else ""):
            return {"arc_summary": "弧线摘要：前几段的整合剧情发展。"}
        if self.module_key == "sequential_reading":
            return self._sequential_reading_payload(user_message)
        if self.module_key == "character_agent_profile":
            return self._character_profile_payload(user_message)
        raise AssertionError(f"unexpected module: {self.module_key}")

    def _anchor_payload(self):
        self.state["anchor_calls"] += 1
        index = self.state["anchor_calls"]
        return {
            "world_state": {
                "active_characters": [{"name": "沈夜", "status": "active", "last_action": f"推进到锚点{index}"}],
                "active_organizations": [{"name": "玄霄宗", "status": "震荡", "key_change": f"锚点{index}发生波动"}],
                "key_relationships": [{"source": "沈夜", "target": "玄霄宗", "state": "conflict", "since_chapter": 1}],
                "open_plot_threads": ["镜湖旧案", f"锚点线索{index}"],
                "recent_events_summary": f"锚点{index}记录了前序剧情变化。",
            }
        }

    def _local_block_payload(self, user_message):
        block_order = self._block_order(user_message)
        first_owned_chapter_id = self._first_owned_chapter_id(user_message, block_order)
        base = (block_order - 1) * 3
        local_entities = [
            {
                "name": "沈夜",
                "entity_type": "character",
                "aliases": ["夜哥"] if block_order == 1 else [],
                "summary": "持续追查镜湖旧案。",
                "importance_tier": "protagonist",
                "evidence": [f"{self._block_id(block_order)} 中沈夜继续推进调查。"],
            },
            {
                "name": f"角色{base + 1:03d}",
                "entity_type": "character",
                "aliases": [],
                "summary": f"角色{base + 1:03d} 提供线索。",
                "importance_tier": "supporting",
                "evidence": [f"角色{base + 1:03d} 在当前块中出场。"],
            },
            {
                "name": "夜哥" if block_order == 2 else f"角色{base + 2:03d}",
                "entity_type": "character",
                "aliases": [],
                "summary": "用于测试别名合并。",
                "importance_tier": "supporting",
                "evidence": [f"{self._block_id(block_order)} 中出现别名或新角色。"],
            },
            {
                "name": "玄霄宗",
                "entity_type": "organization",
                "aliases": [],
                "summary": "玄霄宗持续介入争斗。",
                "importance_tier": "major",
                "organization_type": "sect",
                "evidence": [f"玄霄宗 在 {self._block_id(block_order)} 中施加影响。"],
            },
        ]
        event_summary = f"{self._block_id(block_order)}：沈夜继续追查镜湖旧案。"
        if block_order == 1:
            event_summary += " 秦昭在混战中战死。"
            local_entities.append(
                {
                    "name": "秦昭",
                    "entity_type": "character",
                    "aliases": [],
                    "summary": "沈夜的同伴。",
                    "importance_tier": "major",
                    "evidence": ["秦昭在混战中战死。"],
                }
            )
            local_entities.extend(
                [
                    {
                        "name": "苏半夏",
                        "entity_type": "character",
                        "aliases": [],
                        "summary": "负责稳住局势。",
                        "importance_tier": "major",
                        "evidence": ["苏半夏负责稳定局势。"],
                    },
                    {
                        "name": "白泽司",
                        "entity_type": "organization",
                        "aliases": [],
                        "summary": "白泽司介入旧案调查。",
                        "importance_tier": "major",
                        "organization_type": "organization",
                        "evidence": ["白泽司正在追查镜湖旧案。"],
                    },
                    {
                        "name": "回声会",
                        "entity_type": "organization",
                        "aliases": [],
                        "summary": "回声会在暗处活动。",
                        "importance_tier": "major",
                        "organization_type": "organization",
                        "evidence": ["回声会暗中推进布局。"],
                    },
                ]
            )
        relationship_changes = [
            {
                "source": "沈夜",
                "target": "玄霄宗",
                "change": "conflict",
                "weight": 1,
                "evidence": [event_summary],
            }
        ]
        if block_order == 1:
            relationship_changes.extend(
                [
                    {
                        "source": "沈夜",
                        "target": "白泽司",
                        "change": "conflict",
                        "weight": 1,
                        "evidence": ["白泽司正在追查镜湖旧案。"],
                    },
                    {
                        "source": "沈夜",
                        "target": "回声会",
                        "change": "conflict",
                        "weight": 1,
                        "evidence": ["回声会暗中推进布局。"],
                    },
                ]
            )
        return {
            "local_events": [
                {
                    "event_id": f"{self._block_id(block_order)}_event_01",
                    "chapter_id": first_owned_chapter_id,
                    "summary": event_summary,
                    "characters": ["沈夜", local_entities[1]["name"]],
                    "organizations": ["玄霄宗"],
                    "evidence": [event_summary],
                }
            ],
            "local_entities": local_entities,
            "local_relationship_changes": relationship_changes,
            "local_threads": [
                {
                    "thread_key": "镜湖旧案",
                    "status": "open",
                    "summary": f"{self._block_id(block_order)} 持续推进镜湖旧案。",
                }
            ],
            "unresolved_refs": [],
            "local_summary": event_summary,
            "evidence_spans": [{"chapter_id": first_owned_chapter_id, "snippet": event_summary}],
            "world_rules": [],
        }

    def _contextual_payload(self, user_message):
        block_order = self._block_order(user_message)
        character_updates = [{"name": "沈夜", "state": "active", "evidence": [f"{self._block_id(block_order)} 中沈夜仍在行动。"]}]
        if block_order == 1:
            character_updates.append({"name": "秦昭", "state": "dead", "evidence": ["秦昭在混战中战死。"]})
        return {
            "plot_summary": f"{self._block_id(block_order)} 承接前情继续推进主线。",
            "character_state_updates": character_updates,
            "relationship_updates": [
                {"source": "沈夜", "target": "玄霄宗", "state": "conflict", "evidence": ["双方矛盾继续升级。"]}
            ],
            "thread_updates": [
                {"thread_key": "镜湖旧案", "status": "progressed", "summary": f"{self._block_id(block_order)} 进一步揭露线索。"}
            ],
            "block_end_state": {
                "focus_characters": ["沈夜"],
                "focus_organizations": ["玄霄宗"],
                "open_threads": ["镜湖旧案"],
                "summary": f"{self._block_id(block_order)} 结束时主线仍在推进。",
            },
        }

    def _entity_resolution_payload(self, user_message):
        if "沈夜" in user_message and "夜哥" in user_message:
            return {"merge": True, "canonical_name": "沈夜", "reason": "夜哥是沈夜的明确别名"}
        return {"merge": False, "canonical_name": "", "reason": "证据不足"}

    def _chapter_card_payload(self, user_message):
        chapter_match = re.search(r"chapter_id:\s*(chapter_\d+)", user_message)
        chapter_id = chapter_match.group(1) if chapter_match else "chapter_0001"
        chapter_order = int(chapter_id.rsplit("_", 1)[-1])
        return {
            "summary_text": f"第{chapter_order}章摘要：镜湖主线继续推进。",
            "start_anchor": f"第{chapter_order}章起点：承接前章压力。",
            "end_anchor": f"第{chapter_order}章尾声：新的冲突即将爆发。",
            "key_events": [
                {"summary": f"第{chapter_order}章事件：沈夜继续追查镜湖旧案。"},
                {"summary": f"第{chapter_order}章事件：玄霄宗的布局进一步收紧。"},
            ],
            "open_threads": [
                {"thread_key": "镜湖旧案", "summary": f"第{chapter_order}章后镜湖旧案仍未终结。"},
            ],
            "character_state_updates": [
                {"name": "沈夜", "state": "active", "summary": "持续推进调查。"},
            ],
            "relationship_updates": [
                {"source": "沈夜", "target": "玄霄宗", "state": "conflict", "summary": "双方矛盾继续升级。"},
            ],
            "timeline_note": f"第{chapter_order}章发生在同一夜晚。",
            "key_entities": [
                {"name": "沈夜", "entity_type": "character"},
                {"name": "玄霄宗", "entity_type": "organization"},
            ],
        }

    def _ontology_payload(self):
        return {
            "entity_types": [
                {"name": "Character", "description": "Named character", "attributes": [], "examples": ["沈夜"]},
                {"name": "Organization", "description": "Faction or sect", "attributes": [], "examples": ["玄霄宗"]},
                {"name": "Faction", "description": "Camp", "attributes": [], "examples": ["白泽司"]},
                {"name": "PlotEvent", "description": "Plot event", "attributes": [], "examples": ["镜湖异动"]},
                {"name": "Location", "description": "Location", "attributes": [], "examples": ["镜湖谷"]},
                {"name": "Artifact", "description": "Artifact", "attributes": [], "examples": ["密信"]},
            ],
            "edge_types": [
                {"name": "CONFLICTS_WITH", "description": "Conflict", "source_targets": [{"source": "Character", "target": "Organization"}], "attributes": []},
                {"name": "KNOWS", "description": "Know", "source_targets": [{"source": "Character", "target": "Character"}], "attributes": []},
                {"name": "PARTICIPATES_IN", "description": "Participates", "source_targets": [{"source": "Character", "target": "PlotEvent"}], "attributes": []},
                {"name": "BELONGS_TO", "description": "Belongs", "source_targets": [{"source": "Character", "target": "Organization"}], "attributes": []},
                {"name": "LOCATED_IN", "description": "Located", "source_targets": [{"source": "PlotEvent", "target": "Location"}], "attributes": []},
                {"name": "SEEKS", "description": "Seeks", "source_targets": [{"source": "Character", "target": "Artifact"}], "attributes": []},
            ],
            "analysis_summary": "假 LLM 已生成稳定的小说本体。",
            "story_focus": ["镜湖旧案", "宗门博弈"],
        }

    def _sequential_reading_payload(self, user_message):
        return {
            "segment_summary": "段落摘要：沈夜继续追查镜湖旧案。",
            "character_updates": [
                {
                    "name": "沈夜", "aliases": ["夜哥"], "is_new": True, "status": "active",
                    "identity": "调查者", "personality_traits": ["坚毅"],
                    "speech_style": "简练犀利", "goals": "追查镜湖旧案",
                    "key_actions": ["进入镜湖谷"], "knowledge_gained": ["发现密道"],
                    "quote_examples": ["真相不会自己浮出水面。"],
                },
                {
                    "name": "秦昭", "aliases": [], "is_new": True, "status": "active",
                    "identity": "同伴", "personality_traits": ["忠诚"],
                    "speech_style": "温和", "goals": "保护沈夜",
                    "key_actions": ["掩护撤退"], "knowledge_gained": [],
                    "quote_examples": [],
                },
                {
                    "name": "苏半夏", "aliases": [], "is_new": True, "status": "active",
                    "identity": "稳局者", "personality_traits": ["冷静"],
                    "speech_style": "沉稳", "goals": "稳住局势",
                    "key_actions": ["安排防线"], "knowledge_gained": [],
                    "quote_examples": [],
                },
            ],
            "relationship_changes": [
                {
                    "source": "沈夜", "target": "玄霄宗",
                    "previous_state": "紧张", "new_state": "冲突",
                    "trigger": "宗门施压", "evidence": "对峙升级",
                },
            ],
            "plot_threads": [
                {"thread": "镜湖旧案", "status": "opened", "detail": "线索浮现"},
            ],
            "world_building": [
                {"fact": "五大宗门体系", "evidence": "开篇设定"},
            ],
            "consistency_notes": [],
            "narrative_phase": "development",
        }

    def _character_profile_payload(self, user_message):
        name = "沈夜"
        if "秦昭" in user_message:
            name = "秦昭"
        elif "苏半夏" in user_message:
            name = "苏半夏"
        return {
            "basic_info": {"name": name, "aliases": [], "identity": "角色", "status": "alive"},
            "personality": {"core_traits": ["坚毅"], "values": [], "fears": [], "decision_pattern": ""},
            "speech": {"style": "简练", "verbal_habits": [], "tone_range": "", "example_quotes": []},
            "relationships": [],
            "capabilities": {"skills": [], "limitations": [], "resources": []},
            "knowledge_boundary": {"knows": [], "does_not_know": [], "believes_wrongly": []},
            "motivation": {"ultimate_goal": "", "current_objective": "", "internal_conflict": ""},
        }

    def _block_order(self, text):
        match = BLOCK_ID_PATTERN.search(text)
        if not match:
            return 1
        return int(match.group(1).rsplit("_", 1)[-1])

    def _first_owned_chapter_id(self, text, block_order):
        match = OWNED_CHAPTERS_PATTERN.search(text)
        if not match:
            return f"chapter_{((block_order - 1) * 10) + 1:04d}"
        chapter_ids = re.findall(r"chapter_\d+", match.group(1))
        if not chapter_ids:
            return f"chapter_{((block_order - 1) * 10) + 1:04d}"
        return chapter_ids[0]

    def _block_id(self, block_order):
        return f"block_{block_order:04d}"


def install_fake_seed_llm(monkeypatch):
    state = {"anchor_calls": 0}

    def fake_build_client(self, module_key):
        return FakeSeedLlmClient(module_key, state)

    monkeypatch.setattr(LlmRouter, "build_client", fake_build_client)
    return state
