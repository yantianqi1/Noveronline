"""Persist seed_analysis payloads into structured novel tables."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from ..database import get_engine
from ..repositories.entity_repo import EntityRepository
from ..repositories.relationship_repo import RelationshipRepository
from ..tables.novel import entity_evidence


class SeedAnalysisPersister:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()
        self.entities = EntityRepository(self.engine)
        self.relationships = RelationshipRepository(self.engine)

    def persist(self, project_id: str, seed_analysis: dict[str, Any]) -> dict[str, int]:
        now = datetime.now(timezone.utc).isoformat()
        name_to_id: dict[str, str] = {}
        counts = {"entities": 0, "relationships": 0, "evidence": 0}

        for item in seed_analysis.get("characters", []) or []:
            entity_id = self._persist_entity(project_id, item, "character", now)
            if entity_id:
                name_to_id[str(item.get("name") or "")] = entity_id
                counts["entities"] += 1
                counts["evidence"] += self._persist_entity_evidence(
                    project_id, entity_id, "entity", item.get("evidence", []) or [], now
                )

        for item in seed_analysis.get("organizations", []) or []:
            entity_id = self._persist_entity(project_id, item, "organization", now)
            if entity_id:
                name_to_id[str(item.get("name") or "")] = entity_id
                counts["entities"] += 1
                counts["evidence"] += self._persist_entity_evidence(
                    project_id, entity_id, "entity", item.get("evidence", []) or [], now
                )

        for item in seed_analysis.get("relations", []) or []:
            if self._persist_relationship(project_id, item, name_to_id, now):
                counts["relationships"] += 1

        return counts

    def _persist_entity(
        self,
        project_id: str,
        item: dict[str, Any],
        entity_type: str,
        now: str,
    ) -> str:
        name = str(item.get("name") or "").strip()
        if not name:
            return ""
        existing = self.entities.get_entity_by_name(project_id, name)
        entity_id = (
            str(existing.get("entity_id"))
            if existing
            else self._stable_id("entity", project_id, entity_type, name)
        )
        payload = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "importance_tier": item.get("importance_tier") or "minor",
            "summary": item.get("profile_summary") or item.get("summary") or item.get("identity_hint") or "",
            "core_drive": item.get("core_drive") or "",
            "current_objective": item.get("current_objective") or "",
            "speech_style": item.get("speech_style") or "",
            "personality_traits_json": json.dumps(item.get("personality_traits", []) or [], ensure_ascii=False),
            "example_quotes_json": json.dumps(item.get("evidence", []) or [], ensure_ascii=False),
            "profile_json": json.dumps(item, ensure_ascii=False),
            "created_at": existing.get("created_at") if existing and existing.get("created_at") else now,
            "updated_at": now,
        }
        self.entities.upsert_entity(project_id, payload)
        for alias in item.get("aliases", []) or []:
            alias_text = str(alias or "").strip()
            if alias_text and alias_text != name:
                self.entities.upsert_alias(
                    project_id,
                    {"entity_id": entity_id, "alias": alias_text},
                )
        return entity_id

    def _persist_relationship(
        self,
        project_id: str,
        item: dict[str, Any],
        name_to_id: dict[str, str],
        now: str,
    ) -> bool:
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target:
            return False
        source_id = name_to_id.get(source) or self._resolve_or_create_entity(project_id, source, now)
        target_id = name_to_id.get(target) or self._resolve_or_create_entity(project_id, target, now)
        if not source_id or not target_id:
            return False
        relation_type = str(item.get("relation_type") or "related").strip() or "related"
        relation_id = self._stable_id("relation", project_id, source_id, target_id, relation_type)
        evidence = [str(value).strip() for value in item.get("evidence", []) or [] if str(value).strip()]
        payload = {
            "relation_id": relation_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "description": "；".join(evidence[:3]),
            "history": json.dumps(item.get("evolution_chain", []) or [], ensure_ascii=False),
            "updated_at": now,
        }
        self.relationships.upsert_relationship(project_id, payload)
        self._persist_entity_evidence(project_id, relation_id, "relationship", evidence, now)
        return True

    def _resolve_or_create_entity(self, project_id: str, name: str, now: str) -> str:
        existing = self.entities.get_entity_by_name(project_id, name)
        if existing:
            return str(existing.get("entity_id") or "")
        entity_id = self._stable_id("entity", project_id, "unknown", name)
        self.entities.upsert_entity(
            project_id,
            {
                "entity_id": entity_id,
                "name": name,
                "entity_type": "unknown",
                "importance_tier": "minor",
                "summary": "",
                "profile_json": "{}",
                "created_at": now,
                "updated_at": now,
            },
        )
        return entity_id

    def _persist_entity_evidence(
        self,
        project_id: str,
        owner_id: str,
        owner_type: str,
        snippets: list[Any],
        now: str,
    ) -> int:
        rows = []
        seen = set()
        for snippet in snippets:
            text = str(snippet or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            rows.append(
                {
                    "evidence_id": self._stable_id("evidence", project_id, owner_id, text),
                    "project_id": project_id,
                    "owner_id": owner_id,
                    "owner_type": owner_type,
                    "chapter_id": "",
                    "snippet": text,
                    "created_at": now,
                }
            )
        if not rows:
            return 0
        with self.engine.connect() as conn:
            for row in rows:
                existing = conn.execute(
                    entity_evidence.select()
                    .where(
                        (entity_evidence.c.project_id == project_id)
                        & (entity_evidence.c.evidence_id == row["evidence_id"])
                    )
                    .limit(1)
                ).fetchone()
                if not existing:
                    conn.execute(entity_evidence.insert().values(**row))
            conn.commit()
        return len(rows)

    def _stable_id(self, prefix: str, *parts: str) -> str:
        raw = "|".join(str(part) for part in parts)
        return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:16]}"
