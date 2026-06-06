from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from migrations.json_importers.legacy_inventory import LegacyInventoryReport, LegacyProjectInventory


@dataclass(frozen=True)
class ChecksumEntry:
    scope: str
    owner_id: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ChecksumManifest:
    entries: tuple[ChecksumEntry, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)


def _digest_file(path: Path, uploads_root: Path, scope: str, owner_id: str) -> ChecksumEntry:
    payload = path.read_bytes()
    return ChecksumEntry(
        scope=scope,
        owner_id=owner_id,
        relative_path=path.relative_to(uploads_root).as_posix(),
        sha256=sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _project_files(project: LegacyProjectInventory) -> tuple[Path, ...]:
    assets = [
        project.project_file,
        project.worldline_prepare_db,
        project.worldline_runtime_db,
        *project.manuscript_files,
        *project.top_level_json_files,
        *project.top_level_sqlite_files,
        *project.worldline_session_files,
    ]
    unique: dict[str, Path] = {}
    for path in assets:
        if path is not None:
            unique[path.as_posix()] = path
    return tuple(sorted(unique.values(), key=lambda item: item.as_posix()))


def _system_files(report: LegacyInventoryReport) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                *report.system_sqlite_files,
                *report.system_worldline_prepare_files,
                *report.system_worldline_runtime_files,
                *report.system_worldline_session_files,
            ),
            key=lambda item: item.as_posix(),
        )
    )


def build_checksum_manifest(report: LegacyInventoryReport) -> ChecksumManifest:
    entries = [
        _digest_file(path, report.uploads_root, "system", "system")
        for path in _system_files(report)
    ]
    for project in report.projects:
        entries.extend(
            _digest_file(path, report.uploads_root, "project", project.project_id)
            for path in _project_files(project)
        )
    return ChecksumManifest(
        entries=tuple(
            sorted(
                entries,
                key=lambda entry: (entry.scope, entry.owner_id, entry.relative_path),
            )
        )
    )
