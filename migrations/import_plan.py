from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
import json
from pathlib import Path
import sys

from migrations.checksums.manifest import build_checksum_manifest
from migrations.json_importers.asset_classification import classify_legacy_asset
from migrations.json_importers.legacy_inventory import scan_legacy_root
from migrations.object_registry_plan import build_object_registry_plan


@dataclass(frozen=True)
class ImportPlanEntry:
    relative_path: str
    action: str
    target: str
    execution_mode: str
    object_storage_key: str | None


@dataclass(frozen=True)
class ImportPlan:
    entries: tuple[ImportPlanEntry, ...]
    skipped_rebuild_refs: tuple[str, ...]
    anomalies: tuple[str, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["entry_count"] = self.entry_count
        return payload


def _execution_mode(target: str) -> str:
    if target == "manuscripts+artifact_objects" or "artifacts" in target:
        return "object_then_db"
    return "direct_db"


def build_import_plan(uploads_root: Path) -> ImportPlan:
    inventory = scan_legacy_root(uploads_root)
    manifest = build_checksum_manifest(inventory)
    object_plan = build_object_registry_plan(uploads_root)
    object_key_by_path = {entry.relative_path: entry.storage_key for entry in object_plan.entries}

    entries: list[ImportPlanEntry] = []
    skipped_rebuild_refs: list[str] = []
    for item in manifest.entries:
        decision = classify_legacy_asset(item.relative_path)
        if decision.action == "projection_rebuild_reference":
            skipped_rebuild_refs.append(item.relative_path)
            continue
        if decision.action == "anomaly":
            continue
        entries.append(
            ImportPlanEntry(
                relative_path=item.relative_path,
                action=decision.action,
                target=decision.target,
                execution_mode=_execution_mode(decision.target),
                object_storage_key=object_key_by_path.get(item.relative_path),
            )
        )

    return ImportPlan(
        entries=tuple(entries),
        skipped_rebuild_refs=tuple(sorted(skipped_rebuild_refs)),
        anomalies=inventory.anomalies,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        raise SystemExit("usage: python -m migrations.import_plan <uploads_root>")
    plan = build_import_plan(Path(args[0]))
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
