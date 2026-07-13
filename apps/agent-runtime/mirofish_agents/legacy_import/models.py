from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal


FamilyStatus = Literal[
    "imported", "unchanged", "deferred", "unsupported", "conflict", "failed", "rolled_back"
]
ReportStatus = Literal["complete", "partial", "failed"]


FAMILY_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "project": (),
    "source": ("project",),
    "entities": ("project",),
    "aliases": ("entities",),
    "evidence": ("entities", "source"),
    "relationships": ("entities",),
    "assets": ("project",),
    "archive": ("assets",),
    "graph": ("entities", "relationships"),
    "worldline": ("assets", "graph"),
    "writer": ("assets",),
    "manuscript": ("writer",),
}

REQUIRED_FAMILIES = frozenset({"project", "entities", "relationships", "assets"})


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SourceInspection:
    fingerprint: str
    schema_hash: str
    table_counts: dict[str, int]
    artifact_counts: dict[str, int]
    artifact_hash: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "schema_hash": self.schema_hash,
            "table_counts": self.table_counts,
            "artifact_counts": self.artifact_counts,
            "artifact_hash": self.artifact_hash,
        }


@dataclass(frozen=True)
class PlannedRecord:
    family: str
    table: str
    key_column: str
    key: str
    values: dict[str, Any]
    compare_columns: tuple[str, ...]

    @property
    def row_hash(self) -> str:
        return stable_hash({name: self.values.get(name) for name in self.compare_columns})


@dataclass
class FamilyPlan:
    family: str
    source_count: int = 0
    records: list[PlannedRecord] = field(default_factory=list)
    deferred_count: int = 0
    unsupported_count: int = 0
    reason_codes: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "required": self.family in REQUIRED_FAMILIES,
            "dependencies": list(FAMILY_DEPENDENCIES[self.family]),
            "planned": len(self.records),
            "deferred": self.deferred_count,
            "unsupported": self.unsupported_count,
            "reason_codes": sorted(set(self.reason_codes)),
        }


@dataclass
class ImportPlan:
    import_id: str
    tenant_id: str
    project_id: str
    actor_user_id: str
    source_project_id: str
    source: SourceInspection
    families: dict[str, FamilyPlan]

    @property
    def plan_hash(self) -> str:
        public = {
            "import_id": self.import_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "source_project_id_hash": stable_hash(self.source_project_id),
            "source_fingerprint": self.source.fingerprint,
            "families": {name: family.public_dict() for name, family in self.families.items()},
            "row_hashes": [record.row_hash for record in self.records],
        }
        return stable_hash(public)

    @property
    def records(self) -> list[PlannedRecord]:
        return [record for family in self.families.values() for record in family.records]

    def public_dict(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "source_fingerprint": self.source.fingerprint,
            "plan_hash": self.plan_hash,
            "families": {name: family.public_dict() for name, family in self.families.items()},
        }


def make_report(
    *,
    operation: str,
    import_id: str,
    status: ReportStatus,
    source_fingerprint: str,
    plan_hash: str,
    family_counts: dict[str, dict[str, int]],
    family_reasons: dict[str, list[str]] | None = None,
    blockers: list[str] | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "operation": operation,
        "import_id": import_id,
        "status": status,
        "source_fingerprint": source_fingerprint,
        "plan_hash": plan_hash,
        "family_counts": family_counts,
        "family_reasons": family_reasons or {},
        "blockers": sorted(set(blockers or [])),
        "duration_ms": max(0, duration_ms),
    }
    report["report_digest"] = stable_hash(report)
    return report
