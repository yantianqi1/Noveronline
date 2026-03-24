"""Agent 持久记忆服务。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .agent_memory_writer_summary import build_writer_memory_summary
from .agent_memory_stores import EpisodicMemoryStore, LongTermMemoryStore
from .memory_subject_utils import memory_tokens, normalize_memory_subject

SESSION_LIMIT = 6
LONG_TERM_LIMIT = 6
PROMOTABLE_TYPES = {"goal", "preference", "promise", "relationship", "strategy"}


class AgentMemoryService:
    def __init__(
        self,
        episodic_store: Optional[EpisodicMemoryStore] = None,
        long_term_store: Optional[LongTermMemoryStore] = None,
    ):
        self.episodic_store = episodic_store or EpisodicMemoryStore()
        self.long_term_store = long_term_store or LongTermMemoryStore()

    def record_dialogue(self, container_dir: str, session, branch_id: str, agent: Dict[str, Any], message: str, result: Dict[str, Any], dialogue_id: str) -> None:
        reply = str(result.get("reply") or "").strip()
        memory_type = self._dialogue_type(message, reply)
        summary = f"对话提及“{message.strip()}”，回应重点：{reply[:60] or '暂无'}"
        detail = {"message": message, "reply": reply, "generator_mode": result.get("generator_mode", "template")}
        self._store_session_memory(
            container_dir,
            session.session_id,
            branch_id,
            agent,
            memory_type,
            summary,
            detail,
            "dialogue",
            dialogue_id,
            normalize_memory_subject(message),
            0.55,
        )

    def record_action_queued(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], action_item) -> None:
        detail = action_item.to_dict()
        self._store_session_memory(
            container_dir,
            session_id,
            branch_id,
            agent,
            "strategy",
            f"计划执行动作：{action_item.action}",
            detail,
            "action_queued",
            action_item.action_id,
            normalize_memory_subject(action_item.target or action_item.action),
            0.7,
        )

    def record_step(self, container_dir: str, session, branch, step_result: Dict[str, Any], registry) -> None:
        for action in step_result.get("consumed_actions", []):
            agent = registry.resolve_agent(branch, action.agent_id or action.actor)
            if not agent:
                continue
            summary = f"已执行动作：{action.action}"
            detail = action.to_dict()
            self._store_session_memory(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                "fact",
                summary,
                detail,
                "action_applied",
                action.action_id,
                normalize_memory_subject(action.target or action.action),
                0.82,
            )
            self._promote(
                agent,
                session.session_id,
                branch.branch_id,
                "strategy",
                f"曾执行策略：{action.action}",
                detail,
                "action_applied",
                action.action_id,
                normalize_memory_subject(action.target or action.action),
                0.78,
            )
        for relation in step_result.get("relation_changes", []):
            self._store_relation_memories(container_dir, session, branch, relation, registry)
        for change in step_result.get("state_changes", []):
            agent = registry.resolve_agent(branch, change.get("entity", ""))
            if not agent:
                continue
            self._store_session_memory(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                "fact",
                f"状态更新为 {change.get('status', '')}，原因：{change.get('reason', '')}",
                dict(change),
                "state_change",
                str(change.get("entity", "")),
                normalize_memory_subject(change.get("entity", "")),
                0.6,
            )

    def agent_memories(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], limit: int = 20) -> Dict[str, Any]:
        archive_id = agent.get("source_archive_id", "")
        return {
            "session_memories": self.episodic_store.list_memories(container_dir, session_id, branch_id, agent["agent_id"], limit),
            "long_term_memories": self.long_term_store.list_active_memories(archive_id, ("canon",), limit),
            "candidate_memories": self.long_term_store.list_active_memories(archive_id, ("candidate",), limit),
        }

    def build_context_bundle(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], message: str = "", limit: int = 20) -> Dict[str, Any]:
        memories = self.agent_memories(container_dir, session_id, branch_id, agent, limit)
        session_items = memories["session_memories"][:SESSION_LIMIT]
        long_term_items = self._rank_long_term(memories["long_term_memories"], message)[:LONG_TERM_LIMIT]
        return {
            "session_memories": session_items,
            "long_term_memories": long_term_items,
            "rendered_context": self._render_context(session_items, long_term_items),
            "debug_hits": self._debug_hits(session_items, long_term_items, message),
        }

    def build_writer_memory_summary(
        self,
        container_dir: str,
        session_id: str,
        branch_id: str,
        agent: Dict[str, Any],
        include_candidates: bool = False,
        limit: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        memories = self.agent_memories(container_dir, session_id, branch_id, agent, limit)
        return build_writer_memory_summary(
            memories["session_memories"],
            memories["long_term_memories"],
            memories["candidate_memories"],
            include_candidates=include_candidates,
        )

    def build_candidate_hints(self, container_dir: str, session_id: str, branch_id: str, agents: List[Dict[str, Any]], message: str = "") -> Dict[str, str]:
        hints = {}
        for agent in agents:
            bundle = self.build_context_bundle(container_dir, session_id, branch_id, agent, message, limit=4)
            lines = [item["summary"] for item in (bundle["session_memories"][:1] + bundle["long_term_memories"][:1])]
            if lines:
                hints[agent["agent_id"]] = "；".join(lines)
        return hints

    def _store_relation_memories(self, container_dir: str, session, branch, relation: Dict[str, Any], registry) -> None:
        source = str(relation.get("source") or "").strip()
        target = str(relation.get("target") or "").strip()
        if not source or not target:
            return
        summary = f"与{target if source else ''}的关系变化：{relation.get('change', 'stable')}，{relation.get('note', '')}".strip("，")
        source_agent = registry.resolve_agent(branch, source)
        target_agent = registry.resolve_agent(branch, target)
        for agent, counterpart in ((source_agent, target), (target_agent, source)):
            if not agent:
                continue
            detail = {**relation, "counterpart": counterpart}
            line = f"与{counterpart}的关系变化：{relation.get('change', 'stable')}，{relation.get('note', '')}".strip("，")
            self._store_session_memory(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                "relationship",
                line,
                detail,
                "relation_change",
                f"{source}->{target}",
                normalize_memory_subject(counterpart),
                0.74,
            )
            self._promote(agent, session.session_id, branch.branch_id, "relationship", line, detail, "relation_change", f"{source}->{target}", normalize_memory_subject(counterpart), 0.72)
        relation_agent = registry.resolve_agent(branch, f"{source}->{target}")
        if relation_agent:
            detail = dict(relation)
            self._store_session_memory(
                container_dir,
                session.session_id,
                branch.branch_id,
                relation_agent,
                "relationship",
                summary,
                detail,
                "relation_change",
                f"{source}->{target}",
                normalize_memory_subject(f"{source}_{target}"),
                0.76,
            )

    def _store_session_memory(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], memory_type: str, summary: str, detail: Dict[str, Any], source_kind: str, source_ref_id: str, normalized_subject: str, salience: float) -> None:
        self.episodic_store.insert(
            container_dir,
            session_id,
            branch_id,
            agent["agent_id"],
            agent.get("source_archive_id", ""),
            memory_type,
            summary,
            detail,
            source_kind,
            source_ref_id,
            normalized_subject,
            salience,
        )

    def _promote(self, agent: Dict[str, Any], session_id: str, branch_id: str, memory_type: str, summary: str, detail: Dict[str, Any], source_kind: str, source_ref_id: str, normalized_subject: str, salience: float) -> None:
        archive_id = str(agent.get("source_archive_id") or "").strip()
        if not archive_id or memory_type not in PROMOTABLE_TYPES:
            return
        self.long_term_store.append_candidate(
            archive_id=archive_id,
            agent_id=agent["agent_id"],
            memory_type=memory_type,
            summary=summary,
            detail=detail,
            source_kind=source_kind,
            source_ref_id=source_ref_id,
            normalized_subject=normalized_subject,
            salience=salience,
            source_session_id=session_id,
            source_branch_id=branch_id,
            evidence=[{"summary": summary}],
        )

    def _dialogue_type(self, message: str, reply: str) -> str:
        text = f"{message} {reply}"
        if any(keyword in text for keyword in ("答应", "承诺", "保证", "会先", "不会")):
            return "promise"
        if any(keyword in text for keyword in ("偏好", "喜欢", "讨厌", "更愿意", "倾向")):
            return "preference"
        if any(keyword in text for keyword in ("目标", "必须", "打算", "准备")):
            return "goal"
        if any(keyword in text for keyword in ("关系", "结盟", "合作", "敌意", "背叛")):
            return "relationship"
        return "fact"

    def _rank_long_term(self, items: List[Dict[str, Any]], message: str) -> List[Dict[str, Any]]:
        if not message.strip():
            return items
        ranked = []
        for item in items:
            score = float(item.get("salience") or 0.0) + self._overlap_score(message, item["summary"], item.get("normalized_subject", ""))
            ranked.append((score, item))
        return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)]

    def _render_context(self, session_items: List[Dict[str, Any]], long_term_items: List[Dict[str, Any]]) -> str:
        lines = []
        if session_items:
            lines.append("## 当前世界记忆")
            lines.extend(f"- {item['summary']}" for item in session_items[:3])
        if long_term_items:
            lines.append("## 长期记忆")
            lines.extend(f"- {item['summary']}" for item in long_term_items[:2])
        return "\n".join(lines).strip()

    def _debug_hits(self, session_items: List[Dict[str, Any]], long_term_items: List[Dict[str, Any]], message: str) -> List[Dict[str, Any]]:
        hits = []
        for item in session_items + long_term_items:
            hits.append(
                {
                    "memory_id": item["memory_id"],
                    "scope": item["scope"],
                    "memory_type": item["memory_type"],
                    "summary": item["summary"],
                    "score": float(item.get("salience") or 0.0) + self._overlap_score(message, item["summary"], item.get("normalized_subject", "")),
                }
            )
        return hits

    def _overlap_score(self, message: str, summary: str, subject: str) -> float:
        score = 0.0
        haystack = f"{summary} {subject}"
        for token in memory_tokens(message):
            if token and token in haystack:
                score += 0.2
        return score
