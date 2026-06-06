from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LegacyProjectInventory:
    project_id: str
    root: Path
    project_file: Path | None
    manuscript_files: tuple[Path, ...]
    top_level_json_files: tuple[Path, ...]
    top_level_sqlite_files: tuple[Path, ...]
    worldline_prepare_db: Path | None
    worldline_runtime_db: Path | None
    worldline_session_files: tuple[Path, ...]


@dataclass(frozen=True)
class LegacyInventoryReport:
    uploads_root: Path
    system_sqlite_files: tuple[Path, ...]
    system_worldline_prepare_files: tuple[Path, ...]
    system_worldline_runtime_files: tuple[Path, ...]
    system_worldline_session_files: tuple[Path, ...]
    projects: tuple[LegacyProjectInventory, ...]
    anomalies: tuple[str, ...]

    @property
    def project_count(self) -> int:
        return len(self.projects)

    @property
    def system_sqlite_names(self) -> tuple[str, ...]:
        return tuple(path.name for path in self.system_sqlite_files)


def _sorted_files(paths: list[Path]) -> tuple[Path, ...]:
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def _scan_project(project_dir: Path) -> tuple[LegacyProjectInventory, tuple[str, ...]]:
    project_file = project_dir / "project.json"
    worldlines_dir = project_dir / "worldlines"
    anomalies: list[str] = []
    if not project_file.exists():
        anomalies.append(f"{project_dir.name}: missing project.json")

    inventory = LegacyProjectInventory(
        project_id=project_dir.name,
        root=project_dir,
        project_file=project_file if project_file.exists() else None,
        manuscript_files=_sorted_files(list((project_dir / "files").glob("*"))),
        top_level_json_files=_sorted_files(list(project_dir.glob("*.json"))),
        top_level_sqlite_files=_sorted_files(list(project_dir.glob("*.sqlite3"))),
        worldline_prepare_db=(worldlines_dir / "prepare.sqlite3") if (worldlines_dir / "prepare.sqlite3").exists() else None,
        worldline_runtime_db=(worldlines_dir / "runtime.sqlite3") if (worldlines_dir / "runtime.sqlite3").exists() else None,
        worldline_session_files=_sorted_files(list(worldlines_dir.glob("sessions/*/session.json"))),
    )
    return inventory, tuple(anomalies)


def scan_legacy_root(uploads_root: Path) -> LegacyInventoryReport:
    projects_root = uploads_root / "projects"
    system_root = uploads_root / "system"
    project_dirs = sorted(
        [path for path in projects_root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
    ) if projects_root.exists() else []

    projects: list[LegacyProjectInventory] = []
    anomalies: list[str] = []
    for project_dir in project_dirs:
        project, project_anomalies = _scan_project(project_dir)
        projects.append(project)
        anomalies.extend(project_anomalies)

    worldline_prepare_files = ()
    worldline_runtime_files = ()
    worldline_session_files = ()
    if system_root.exists():
        worldline_prepare_files = _sorted_files(
            list(system_root.glob("global_worldlines/graphs/*/worldlines/prepare.sqlite3"))
        )
        worldline_runtime_files = _sorted_files(
            list(system_root.glob("global_worldlines/graphs/*/worldlines/runtime.sqlite3"))
        )
        worldline_session_files = _sorted_files(
            list(system_root.glob("global_worldlines/graphs/*/worldlines/sessions/*/session.json"))
        )

    return LegacyInventoryReport(
        uploads_root=uploads_root,
        system_sqlite_files=_sorted_files(list(system_root.glob("*.sqlite3"))) if system_root.exists() else (),
        system_worldline_prepare_files=worldline_prepare_files,
        system_worldline_runtime_files=worldline_runtime_files,
        system_worldline_session_files=worldline_session_files,
        projects=tuple(projects),
        anomalies=tuple(anomalies),
    )
