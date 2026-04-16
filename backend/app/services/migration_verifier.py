"""Migration verification helpers for project-level legacy/unified consistency checks."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from ..tables import metadata


class MigrationVerifier:
    """Compare legacy per-project stores against the unified database."""

    DOMAIN_SOURCES = {
        "novel": "novel.sqlite3",
        "story_graph": "story_graph.sqlite3",
    }

    def __init__(self, *, upload_root: str | Path, engine: Engine):
        self.upload_root = Path(upload_root)
        self.engine = engine

    def verify_project(self, project_id: str) -> dict[str, Any]:
        project_dir = self.upload_root / "projects" / project_id
        legacy_sources = self._legacy_source_report(project_dir)
        domains = {
            domain_name: self._verify_domain(project_id, domain_name, project_dir / filename)
            for domain_name, filename in self.DOMAIN_SOURCES.items()
        }
        overall_verdict = self._overall_verdict(legacy_sources, domains)
        return {
            "project_id": project_id,
            "project_dir": str(project_dir),
            "legacy_sources": legacy_sources,
            "domains": domains,
            "overall_verdict": overall_verdict,
            "risk_level": self._risk_level(overall_verdict),
        }

    def _legacy_source_report(self, project_dir: Path) -> dict[str, dict[str, Any]]:
        report: dict[str, dict[str, Any]] = {
            "project_dir": {"exists": project_dir.exists(), "path": str(project_dir)},
            "project_meta": {"exists": (project_dir / "project.json").exists(), "path": str(project_dir / "project.json")},
            "extracted_text": {
                "exists": (project_dir / "extracted_text.txt").exists(),
                "path": str(project_dir / "extracted_text.txt"),
            },
            "novel_db": {"exists": (project_dir / "novel.sqlite3").exists(), "path": str(project_dir / "novel.sqlite3")},
            "story_graph_db": {
                "exists": (project_dir / "story_graph.sqlite3").exists(),
                "path": str(project_dir / "story_graph.sqlite3"),
            },
            "story_graph_json": {
                "exists": (project_dir / "story_graph.json").exists(),
                "path": str(project_dir / "story_graph.json"),
            },
        }
        return report

    def _verify_domain(self, project_id: str, domain_name: str, source_path: Path) -> dict[str, Any]:
        if not source_path.exists():
            return {
                "domain": domain_name,
                "source_path": str(source_path),
                "source_available": False,
                "status": "warn",
                "legacy_row_count": 0,
                "unified_row_count": 0,
                "missing_in_unified_count": 0,
                "unexpected_in_unified_count": 0,
                "mismatch_count": 0,
                "table_count": 0,
                "tables": [],
                "notes": ["legacy source missing"],
            }

        with sqlite3.connect(source_path) as connection:
            connection.row_factory = sqlite3.Row
            table_names = self._source_tables(connection)
            table_reports = [self._verify_table(project_id, connection, table_name) for table_name in table_names]

        legacy_row_count = sum(item["legacy_row_count"] for item in table_reports)
        unified_row_count = sum(item["unified_row_count"] for item in table_reports)
        missing_count = sum(item["missing_in_unified_count"] for item in table_reports)
        unexpected_count = sum(item["unexpected_in_unified_count"] for item in table_reports)
        mismatch_count = sum(item["mismatch_count"] for item in table_reports)
        status = "pass" if not (missing_count or unexpected_count or mismatch_count) else "fail"
        if not table_reports:
            status = "warn"
        return {
            "domain": domain_name,
            "source_path": str(source_path),
            "source_available": True,
            "status": status,
            "legacy_row_count": legacy_row_count,
            "unified_row_count": unified_row_count,
            "missing_in_unified_count": missing_count,
            "unexpected_in_unified_count": unexpected_count,
            "mismatch_count": mismatch_count,
            "table_count": len(table_reports),
            "tables": table_reports,
            "notes": [] if table_reports else ["no comparable project-scoped tables found"],
        }

    def _source_tables(self, connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        result: list[str] = []
        for row in rows:
            name = row[0]
            table = metadata.tables.get(name)
            if table is None or "project_id" not in table.c:
                continue
            result.append(name)
        return result

    def _verify_table(self, project_id: str, source_conn: sqlite3.Connection, table_name: str) -> dict[str, Any]:
        source_columns = self._source_columns(source_conn, table_name)
        unified_table = metadata.tables[table_name]
        compare_columns = [column for column in source_columns if column in unified_table.c and column != "project_id"]
        key_columns = self._key_columns(source_conn, table_name, unified_table)

        legacy_rows = [dict(row) for row in source_conn.execute(f"SELECT * FROM {table_name}").fetchall()]
        unified_rows = self._fetch_unified_rows(project_id, table_name)

        legacy_index = {self._row_key(row, key_columns): row for row in legacy_rows}
        unified_index = {self._row_key(row, key_columns): row for row in unified_rows}

        legacy_keys = set(legacy_index)
        unified_keys = set(unified_index)
        common_keys = legacy_keys & unified_keys
        missing_keys = sorted(legacy_keys - unified_keys)
        unexpected_keys = sorted(unified_keys - legacy_keys)

        field_mismatches = []
        for key in sorted(common_keys):
            legacy_payload = self._normalized_payload(legacy_index[key], compare_columns)
            unified_payload = self._normalized_payload(unified_index[key], compare_columns)
            if legacy_payload == unified_payload:
                continue
            differing_fields = [
                column for column in compare_columns if legacy_payload.get(column) != unified_payload.get(column)
            ]
            field_mismatches.append(
                {
                    "primary_key": dict(zip(key_columns, key)),
                    "differing_fields": differing_fields,
                    "legacy_hash": self._hash_payload(legacy_payload),
                    "unified_hash": self._hash_payload(unified_payload),
                }
            )

        return {
            "table": table_name,
            "primary_key_columns": key_columns,
            "compared_columns": compare_columns,
            "legacy_row_count": len(legacy_rows),
            "unified_row_count": len(unified_rows),
            "missing_in_unified_count": len(missing_keys),
            "unexpected_in_unified_count": len(unexpected_keys),
            "mismatch_count": len(field_mismatches),
            "missing_in_unified": [dict(zip(key_columns, key)) for key in missing_keys],
            "unexpected_in_unified": [dict(zip(key_columns, key)) for key in unexpected_keys],
            "field_mismatches": field_mismatches,
        }

    def _source_columns(self, source_conn: sqlite3.Connection, table_name: str) -> list[str]:
        rows = source_conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [row[1] for row in rows]

    def _key_columns(self, source_conn: sqlite3.Connection, table_name: str, unified_table) -> list[str]:
        pragma_rows = source_conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        source_keys = [row[1] for row in sorted(pragma_rows, key=lambda item: item[5]) if row_has_pk(row)]
        if source_keys:
            return [column for column in source_keys if column != "project_id"]
        unified_keys = [column.name for column in unified_table.primary_key.columns if column.name != "project_id"]
        if unified_keys:
            return unified_keys
        source_columns = self._source_columns(source_conn, table_name)
        return [column for column in source_columns if column != "project_id"]

    def _fetch_unified_rows(self, project_id: str, table_name: str) -> list[dict[str, Any]]:
        statement = text(f"SELECT * FROM {table_name} WHERE project_id = :project_id")
        with self.engine.connect() as connection:
            return [dict(row._mapping) for row in connection.execute(statement, {"project_id": project_id}).fetchall()]

    def _row_key(self, row: dict[str, Any], key_columns: list[str]) -> tuple[Any, ...]:
        return tuple(row.get(column) for column in key_columns)

    def _normalized_payload(self, row: dict[str, Any], compare_columns: list[str]) -> dict[str, Any]:
        return {column: row.get(column) for column in compare_columns}

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _overall_verdict(self, legacy_sources: dict[str, Any], domains: dict[str, Any]) -> str:
        statuses = [domain["status"] for domain in domains.values()]
        if any(status == "fail" for status in statuses):
            return "fail"
        if not legacy_sources["project_meta"]["exists"] or any(status == "warn" for status in statuses):
            return "warn"
        return "pass"

    def _risk_level(self, overall_verdict: str) -> str:
        return {
            "fail": "high",
            "warn": "medium",
            "pass": "low",
        }[overall_verdict]


def row_has_pk(row: sqlite3.Row) -> bool:
    return bool(row[5])


__all__ = ["MigrationVerifier"]
