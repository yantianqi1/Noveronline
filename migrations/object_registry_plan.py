from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path

from migrations.checksums.manifest import build_checksum_manifest
from migrations.json_importers.asset_classification import classify_legacy_asset
from migrations.json_importers.legacy_inventory import scan_legacy_root


ARTIFACT_BUCKET = "mirofish-artifacts"


@dataclass(frozen=True)
class ObjectRegistryPlanEntry:
    owner_id: str
    relative_path: str
    registry_kind: str
    bucket: str
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True)
class ObjectRegistryPlan:
    entries: tuple[ObjectRegistryPlanEntry, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)


def _registry_kind(target: str) -> str | None:
    if target == "manuscripts+artifact_objects":
        return "manuscript_source"
    if "artifacts" in target:
        return "artifact_payload"
    return None


def _build_storage_key(owner_id: str, sha: str, filename: str) -> str:
    return f"legacy/{owner_id}/{sha[:16]}-{filename}"


def build_object_registry_plan(uploads_root: Path) -> ObjectRegistryPlan:
    inventory = scan_legacy_root(uploads_root)
    manifest = build_checksum_manifest(inventory)
    entries: list[ObjectRegistryPlanEntry] = []
    for item in manifest.entries:
        decision = classify_legacy_asset(item.relative_path)
        registry_kind = _registry_kind(decision.target)
        if registry_kind is None:
            continue
        filename = Path(item.relative_path).name
        entries.append(
            ObjectRegistryPlanEntry(
                owner_id=item.owner_id,
                relative_path=item.relative_path,
                registry_kind=registry_kind,
                bucket=ARTIFACT_BUCKET,
                storage_key=_build_storage_key(item.owner_id, item.sha256, filename),
                sha256=item.sha256,
                size_bytes=item.size_bytes,
                content_type=mimetypes.guess_type(filename)[0],
            )
        )
    return ObjectRegistryPlan(entries=tuple(entries))
