"""Persist agent_profiles payloads into structured entity fields."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from ..database import get_engine
from ..repositories.entity_repo import EntityRepository


_EMPTY_MARKERS = {"", "暂无记录", "unknown", "None", "null"}


class AgentProfilePersister:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()
        self.entities = EntityRepository(self.engine)

    def persist(self, project_id: str, agent_profiles: dict[str, Any]) -> dict[str, int]:
        if not isinstance(agent_profiles, dict):
            raise ValueError("agent_profiles payload 格式异常，无法结构化落库。")
        profiles = agent_profiles.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("agent_profiles.profiles 格式异常，无法结构化落库。")

        now = datetime.now(timezone.utc).isoformat()
        counts = {"profiles": 0, "aliases": 0}
        for profile_key, profile in profiles.items():
            if not isinstance(profile, dict):
                raise ValueError(f"角色档案 {profile_key} 格式异常，无法结构化落库。")
            name = self._profile_name(str(profile_key), profile)
            if not name:
                continue
            entity_id = self._persist_profile(project_id, name, profile, now)
            if not entity_id:
                continue
            counts["profiles"] += 1
            counts["aliases"] += self._persist_aliases(project_id, entity_id, name, profile)
        return counts

    def _persist_profile(
        self,
        project_id: str,
        name: str,
        profile: dict[str, Any],
        now: str,
    ) -> str:
        existing = self.entities.get_entity_by_name(project_id, name)
        entity_id = (
            str(existing.get("entity_id"))
            if existing
            else self._stable_id("entity", project_id, "character", name)
        )
        payload = {
            "entity_id": entity_id,
            "profile_json": json.dumps(profile, ensure_ascii=False),
            "updated_at": now,
        }
        if not existing:
            payload.update(
                {
                    "name": name,
                    "entity_type": "character",
                    "importance_tier": "minor",
                    "summary": self._text(profile.get("basic_info", {}).get("identity")) or "",
                    "created_at": now,
                }
            )
        payload.update(self._mapped_profile_fields(profile))
        self.entities.upsert_entity(project_id, payload)
        return entity_id

    def _mapped_profile_fields(self, profile: dict[str, Any]) -> dict[str, Any]:
        personality = self._dict(profile.get("personality"))
        speech = self._dict(profile.get("speech"))
        capabilities = self._dict(profile.get("capabilities"))
        knowledge = self._dict(profile.get("knowledge_boundary"))
        motivation = self._dict(profile.get("motivation"))

        fields: dict[str, Any] = {
            "personality_traits_json": self._json_list(personality.get("core_traits")),
            "verbal_habits_json": self._json_list(speech.get("verbal_habits")),
            "example_quotes_json": self._json_list(speech.get("example_quotes")),
            "skills_json": self._json_list(capabilities.get("skills")),
            "limitations_json": self._json_list(capabilities.get("limitations")),
            "knowledge_boundary_json": json.dumps(knowledge, ensure_ascii=False),
        }

        for column, value in (
            ("speech_style", self._text(speech.get("style"))),
            ("values_text", self._joined_text(personality.get("values"))),
            ("fears_text", self._joined_text(personality.get("fears"))),
            ("decision_pattern", self._text(personality.get("decision_pattern"))),
            ("resources_text", self._joined_text(capabilities.get("resources"))),
            ("ultimate_goal", self._text(motivation.get("ultimate_goal"))),
            ("current_objective", self._text(motivation.get("current_objective"))),
            ("hidden_tension", self._text(motivation.get("internal_conflict"))),
        ):
            if value is not None:
                fields[column] = value

        return fields

    def _persist_aliases(
        self,
        project_id: str,
        entity_id: str,
        name: str,
        profile: dict[str, Any],
    ) -> int:
        aliases = self._list(profile.get("basic_info", {}).get("aliases"))
        count = 0
        for alias in aliases:
            alias_text = self._text(alias)
            if not alias_text or alias_text == name:
                continue
            self.entities.upsert_alias(
                project_id,
                {"entity_id": entity_id, "alias": alias_text},
            )
            count += 1
        return count

    def _profile_name(self, fallback: str, profile: dict[str, Any]) -> str:
        basic = self._dict(profile.get("basic_info"))
        return self._text(basic.get("name")) or self._text(fallback) or ""

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _json_list(self, value: Any) -> str:
        return json.dumps(self._list(value), ensure_ascii=False)

    def _list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return [item for item in value if self._text(item) is not None]
        if isinstance(value, tuple):
            return [item for item in value if self._text(item) is not None]
        text = self._text(value)
        return [text] if text is not None else []

    def _joined_text(self, value: Any) -> str | None:
        if isinstance(value, list | tuple):
            parts = [text for item in value if (text := self._text(item)) is not None]
            return "；".join(parts) if parts else None
        return self._text(value)

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text in _EMPTY_MARKERS:
            return None
        return text

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        raw = "|".join(str(part) for part in parts)
        return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:16]}"
