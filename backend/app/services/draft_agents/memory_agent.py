"""记忆收集 Agent — 从档案库和世界线运行时收集 POV 相关记忆。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...models.project import ProjectManager

logger = logging.getLogger(__name__)


class MemoryAgent:
    """收集 POV 角色在当前范围内的运行时记忆与档案信息。"""

    def collect(
        self,
        project_id: str,
        pov_character: str,
        scope_type: str = "project_chapter",
        session_id: str = "",
        branch_id: str = "main",
    ) -> Dict[str, Any]:
        """
        收集记忆信息。

        世界线分支模式: 从 worldline engine 的 memory_service 获取运行时记忆。
        原著章节模式: 从 seed_analysis.json 和 story_memory.json 中提取角色相关信息。

        Returns:
            memory_bundle 字典，包含 character_profile, memories, relationships 等。
        """
        bundle: Dict[str, Any] = {
            "character_profile": {},
            "memories": [],
            "relationships": [],
            "rendered_context": "",
        }

        if scope_type == "worldline_branch" and session_id:
            bundle = self._collect_worldline_memory(project_id, pov_character, session_id, branch_id, bundle)
        else:
            bundle = self._collect_project_memory(project_id, pov_character, bundle)

        bundle["rendered_context"] = self._render_memory_context(bundle)
        logger.info(
            "MemoryAgent: 收集完成 — memories=%d, relationships=%d",
            len(bundle["memories"]),
            len(bundle["relationships"]),
        )
        return bundle

    def _collect_worldline_memory(
        self,
        project_id: str,
        pov_character: str,
        session_id: str,
        branch_id: str,
        bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从世界线引擎中收集运行时记忆。"""
        try:
            from ..worldline_engine_factory import build_worldline_engine
            from ..worldline_single_world import current_world, resolve_branch_id

            engine = build_worldline_engine()
            session = engine.get_session(session_id, project_id=project_id)
            if not session:
                logger.warning("MemoryAgent: 世界线会话不存在 — session_id=%s", session_id)
                return bundle

            resolve_branch_id(branch_id)
            branch = current_world(session)
            _, container_dir = engine.store.resolve_container(
                session.project_id or project_id,
                session.graph_id,
                session_scope=session.session_scope,
            )
            agent = engine.runtime_service.resolve_agent(
                container_dir, session, branch.branch_id, pov_character
            )
            if not agent:
                logger.warning("MemoryAgent: 世界线中不存在 POV 角色 — %s", pov_character)
                return bundle

            memory_summary = engine.memory_service.build_writer_memory_summary(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                include_candidates=False,
            )

            for bucket_key in ("recent_commitments", "active_strategies", "relationship_tensions", "identity_constraints"):
                for item in memory_summary.get(bucket_key, []):
                    bundle["memories"].append({
                        "type": item.get("memory_type", bucket_key),
                        "summary": item.get("summary", ""),
                        "salience": item.get("salience", 0.5),
                    })

            bundle["character_profile"] = {
                "name": pov_character,
                "status": agent.get("state", {}).get("status", "active"),
                "drive": agent.get("state", {}).get("drive") or agent.get("state", {}).get("core_drive", ""),
                "tension": agent.get("state", {}).get("tension") or agent.get("state", {}).get("hidden_tension", ""),
            }

            for relation in branch.relationship_states[-6:]:
                if pov_character in {relation.get("source", ""), relation.get("target", "")}:
                    bundle["relationships"].append({
                        "source": relation.get("source", ""),
                        "target": relation.get("target", ""),
                        "note": relation.get("note") or relation.get("change", ""),
                    })

        except Exception as exc:
            logger.warning("MemoryAgent: 世界线记忆收集失败 — %s", exc)

        return bundle

    def _collect_project_memory(
        self,
        project_id: str,
        pov_character: str,
        bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从项目产物中收集记忆信息。"""
        try:
            seed_analysis = ProjectManager.load_project_json(project_id, "seed_analysis.json") or {}
            story_memory = ProjectManager.load_project_json(project_id, "story_memory.json") or {}

            # 从 seed_analysis 提取角色画像
            pov_char_data = None
            for character in seed_analysis.get("characters", []):
                if character.get("name") == pov_character:
                    pov_char_data = character
                    bundle["character_profile"] = {
                        "name": pov_character,
                        "role": character.get("role", ""),
                        "traits": character.get("traits", []),
                        "description": character.get("description", ""),
                    }
                    break

            # 从 story_memory 提取关系
            for relation in story_memory.get("relationship_ledger", []):
                if pov_character in {relation.get("source", ""), relation.get("target", "")}:
                    bundle["relationships"].append({
                        "source": relation.get("source", ""),
                        "target": relation.get("target", ""),
                        "note": relation.get("type", ""),
                    })

            # 从 story_memory 提取事件
            for event in story_memory.get("event_timeline", [])[-6:]:
                if pov_character in event.get("characters", []):
                    bundle["memories"].append({
                        "type": "event",
                        "summary": event.get("summary", ""),
                        "salience": 0.7,
                    })

            # ─── 降级：若 story_memory 无数据，从 seed_analysis 补充 ───
            if not bundle["memories"] and not bundle["relationships"]:
                self._fallback_from_seed(seed_analysis, pov_character, pov_char_data, bundle)

        except Exception as exc:
            logger.warning("MemoryAgent: 项目记忆收集失败 — %s", exc)

        return bundle

    def _fallback_from_seed(
        self,
        seed_analysis: Dict[str, Any],
        pov_character: str,
        pov_char_data: Optional[Dict[str, Any]],
        bundle: Dict[str, Any],
    ) -> None:
        """当 story_memory 无数据时，从 seed_analysis 补充记忆和关系。"""
        # 从角色数据中提取关系
        if pov_char_data:
            for rel in pov_char_data.get("relationships", []):
                target = rel.get("target", "") or rel.get("name", "")
                if target:
                    bundle["relationships"].append({
                        "source": pov_character,
                        "target": target,
                        "note": rel.get("type", "") or rel.get("description", ""),
                    })
            # 从性格特征中生成记忆条目
            description = pov_char_data.get("description", "")
            if description:
                bundle["memories"].append({
                    "type": "character_profile",
                    "summary": description[:200],
                    "salience": 0.6,
                })
            for trait in pov_char_data.get("traits", [])[:3]:
                if isinstance(trait, str) and trait.strip():
                    bundle["memories"].append({
                        "type": "trait",
                        "summary": f"性格特点：{trait}",
                        "salience": 0.5,
                    })

        # 从 seed_analysis 的全局关系中补充
        for rel in seed_analysis.get("relationships", []):
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            if pov_character in {src, tgt} and not any(
                r.get("source") == src and r.get("target") == tgt
                for r in bundle["relationships"]
            ):
                bundle["relationships"].append({
                    "source": src,
                    "target": tgt,
                    "note": rel.get("type", "") or rel.get("description", ""),
                })

        # 从 seed_analysis 的关键事件中提取
        for event in seed_analysis.get("key_events", [])[-6:]:
            participants = event.get("characters", []) or event.get("participants", [])
            if pov_character in participants:
                bundle["memories"].append({
                    "type": "seed_event",
                    "summary": event.get("summary", "") or event.get("description", ""),
                    "salience": 0.6,
                })

        if bundle["memories"] or bundle["relationships"]:
            logger.info(
                "MemoryAgent: 从 seed_analysis 降级补充 — memories=%d, relationships=%d",
                len(bundle["memories"]),
                len(bundle["relationships"]),
            )

    def _render_memory_context(self, bundle: Dict[str, Any]) -> str:
        """将记忆 bundle 渲染为可放入 prompt 的文本。"""
        lines: List[str] = []

        profile = bundle.get("character_profile", {})
        if profile.get("name"):
            profile_line = f"POV 角色：{profile['name']}"
            if profile.get("drive"):
                profile_line += f"，目标：{profile['drive']}"
            if profile.get("tension"):
                profile_line += f"，内在张力：{profile['tension']}"
            if profile.get("role"):
                profile_line += f"，身份：{profile['role']}"
            lines.append(profile_line)

        if bundle.get("relationships"):
            lines.append("关键关系：")
            for rel in bundle["relationships"][:4]:
                lines.append(f"- {rel['source']} 与 {rel['target']}：{rel.get('note', '关系变化中')}")

        if bundle.get("memories"):
            lines.append("近期记忆：")
            sorted_memories = sorted(bundle["memories"], key=lambda x: -x.get("salience", 0.0))
            for mem in sorted_memories[:6]:
                lines.append(f"- [{mem.get('type', 'fact')}] {mem['summary']}")

        return "\n".join(lines) if lines else "暂无角色记忆信息。"
