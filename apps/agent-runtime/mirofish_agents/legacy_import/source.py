from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .models import SourceInspection, stable_hash


BUSINESS_TABLES = (
    "project_meta",
    "project_artifacts",
    "archive_sources",
    "entities",
    "entity_aliases",
    "entity_evidence",
    "entity_labels",
    "relationship_events",
    "character_events",
    "relationships",
    "assets",
    "archive_library",
    "archive_agent_memory",
    "archive_agent_memory_events",
    "graph_meta",
    "graph_nodes",
    "graph_aliases",
    "graph_node_labels",
    "graph_edges",
    "graph_evidence",
    "worldline_sessions",
    "worldline_branches",
    "agent_registry",
    "agent_state_snapshots",
    "agent_states",
    "agent_action_log",
    "agent_dialogue_log",
    "agent_episodic_memory",
    "agent_memory",
    "relation_state_log",
    "prepare_runs",
    "prepared_agent_dossiers",
    "writer_runs",
    "writer_drafts",
    "writer_run_events",
    "writer_draft_events",
    "book_plans",
    "outline_versions",
    "scenes",
    "dedup_index",
    "chapter_content",
    "chapter_meta",
)


class LegacySource:
    def __init__(self, sqlite_path: str | Path, artifact_root: str | Path | None = None) -> None:
        self.sqlite_path = _resolved_without_symlinks(sqlite_path, "source database")
        self.artifact_root = (
            _resolved_without_symlinks(artifact_root, "artifact root")
            if artifact_root
            else None
        )

    def connect(self) -> sqlite3.Connection:
        if not self.sqlite_path.is_file():
            raise FileNotFoundError("legacy SQLite source does not exist")
        uri = f"file:{quote(str(self.sqlite_path))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def inspect(self) -> SourceInspection:
        with self.connect() as connection:
            available = self._available_tables(connection)
            schema_rows = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            table_counts = {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in BUSINESS_TABLES
                if table in available
            }
        artifact_counts, artifact_hash = self._inspect_artifacts()
        database_hash = stable_hash(
            [
                (candidate.name, self._hash_file(candidate))
                for candidate in (self.sqlite_path, Path(f"{self.sqlite_path}-wal"))
                if candidate.is_file()
            ]
        )
        schema_hash = stable_hash([(row["name"], row["sql"]) for row in schema_rows])
        fingerprint = stable_hash(
            {
                "database_sha256": database_hash,
                "schema_hash": schema_hash,
                "artifact_hash": artifact_hash,
            }
        )
        return SourceInspection(
            fingerprint=fingerprint,
            schema_hash=schema_hash,
            table_counts=table_counts,
            artifact_counts=artifact_counts,
            artifact_hash=artifact_hash,
        )

    def rows(self, table: str, source_project_id: str | None = None) -> list[dict[str, Any]]:
        if table not in BUSINESS_TABLES:
            raise ValueError("table is not in the legacy import allowlist")
        with self.connect() as connection:
            if table not in self._available_tables(connection):
                return []
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if source_project_id is not None and "project_id" in columns:
                result = connection.execute(
                    f'SELECT * FROM "{table}" WHERE project_id = ? ORDER BY rowid',
                    (source_project_id,),
                ).fetchall()
            else:
                result = connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
        return [dict(row) for row in result]

    def project_ids(self) -> list[str]:
        with self.connect() as connection:
            available = self._available_tables(connection)
            if "project_meta" not in available:
                return []
            return [str(row[0]) for row in connection.execute("SELECT project_id FROM project_meta ORDER BY project_id")]

    @staticmethod
    def json_value(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def _available_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    def _inspect_artifacts(self) -> tuple[dict[str, int], str]:
        if self.artifact_root is None or not self.artifact_root.exists():
            return {}, stable_hash([])
        root = self.artifact_root.resolve()
        files: list[Path] = []
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if any((root / relative_parent).is_symlink() for relative_parent in _prefixes(relative)):
                raise RuntimeError("LEGACY_ARTIFACT_SYMLINK_UNSUPPORTED")
            resolved = path.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise RuntimeError("LEGACY_ARTIFACT_PATH_OUTSIDE_ROOT") from exc
            if resolved.is_file():
                files.append(resolved)
        files.sort()
        entries: list[tuple[str, int, str]] = []
        counts: dict[str, int] = {}
        for path in files:
            suffix = path.suffix.lower() or "[no-extension]"
            counts[suffix] = counts.get(suffix, 0) + 1
            entries.append((str(path.relative_to(self.artifact_root)), path.stat().st_size, self._hash_file(path)))
        return counts, stable_hash(entries)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def _prefixes(path: Path) -> list[Path]:
    parts = path.parts
    return [Path(*parts[:index]) for index in range(1, len(parts) + 1)]


def _resolved_without_symlinks(value: str | Path, label: str) -> Path:
    supplied = Path(value).expanduser()
    absolute = Path(os.path.abspath(supplied))
    anchor = Path(absolute.anchor)
    relative = absolute.relative_to(anchor)
    for prefix in _prefixes(relative):
        if (anchor / prefix).is_symlink():
            raise RuntimeError(f"legacy {label} symlinks are unsupported")
    return absolute.resolve()


def first_nonempty(row: dict[str, Any], names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return default
