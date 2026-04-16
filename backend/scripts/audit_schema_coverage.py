"""Audit unified schema coverage against legacy SQLite stores and JSON artifacts."""

from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import IO, Iterable

SQLITE_GLOBS = ("*.sqlite3", "*.sqlite", "*.db")
DEFAULT_JSON_ARTIFACT_RULES: dict[str, dict[str, dict[str, list[str]]]] = {
    "seed_analysis.json": {
        "tables": {
            "entities": ["entity_id", "name", "entity_type"],
            "relationships": ["relation_id", "source_id", "target_id", "relation_type"],
            "plot_threads": ["thread_id", "thread_key", "status"],
            "world_rule_evidence": ["evidence_id", "fact_text"],
            "consistency_notes": ["note_id", "note_text"],
        }
    },
    "narrative_archives.json": {
        "tables": {
            "archive_library": ["archive_id", "entity_uuid", "entity_name", "entity_type"],
        }
    },
    "reading_notes.json": {
        "tables": {
            "assets": ["asset_id", "scope", "asset_type", "title", "payload_json"],
        }
    },
    "ontology.json": {
        "tables": {
            "assets": ["asset_id", "scope", "asset_type", "title", "payload_json"],
        }
    },
    "story_memory.json": {
        "tables": {
            "agent_memory": ["memory_id", "entity_id", "memory_type", "summary"],
        }
    },
    "chapter_segments.json": {
        "tables": {
            "chapter_content": ["chapter_id", "chapter_order", "title", "content"],
            "chapter_meta": ["chapter_id", "summary"],
        }
    },
    "agent_profiles.json": {
        "tables": {
            "archive_library": ["archive_id", "entity_uuid", "entity_name", "entity_type"],
        }
    },
}


def audit_schema_coverage(
    upload_root: str | Path,
    *,
    json_artifact_rules: dict[str, dict[str, dict[str, list[str]]]] | None = None,
) -> dict[str, object]:
    unified_schema = _unified_schema()
    legacy_tables = _discover_legacy_sqlite_tables(Path(upload_root))
    json_artifact_rules = json_artifact_rules or DEFAULT_JSON_ARTIFACT_RULES
    json_expectations = _discover_json_expectations(Path(upload_root), json_artifact_rules)

    missing_tables = sorted(table for table in json_expectations if table not in unified_schema)

    missing_columns: dict[str, list[str]] = {}
    for table_name, legacy_columns in legacy_tables.items():
        if table_name not in unified_schema:
            continue
        uncovered = sorted(column for column in legacy_columns if column not in unified_schema[table_name])
        if uncovered:
            missing_columns[table_name] = uncovered

    for table_name, expected_columns in json_expectations.items():
        if table_name not in unified_schema:
            continue
        uncovered = set(missing_columns.get(table_name, []))
        uncovered.update(column for column in expected_columns if column not in unified_schema[table_name])
        if uncovered:
            missing_columns[table_name] = sorted(uncovered)

    covered_unified_tables = {
        table_name for table_name in legacy_tables if table_name in unified_schema
    }
    covered_unified_tables.update(
        table_name for table_name in json_expectations if table_name in unified_schema
    )

    return {
        "missing_tables": missing_tables,
        "missing_columns": {table: missing_columns[table] for table in sorted(missing_columns)},
        "legacy_only_tables": sorted(table for table in legacy_tables if table not in unified_schema),
        "unified_only_tables": sorted(table for table in unified_schema if table not in covered_unified_tables),
    }


def main(
    argv: list[str] | None = None,
    *,
    stdout: IO[str] | None = None,
    json_artifact_rules: dict[str, dict[str, dict[str, list[str]]]] | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-root", default="uploads")
    args = parser.parse_args(argv)

    report = audit_schema_coverage(args.upload_root, json_artifact_rules=json_artifact_rules)
    output = stdout or sys.stdout
    json.dump(report, output, ensure_ascii=False, sort_keys=True)
    output.write("\n")
    return 0


def _unified_schema() -> dict[str, set[str]]:
    try:
        from app.tables import metadata  # type: ignore
    except ModuleNotFoundError:
        return _parse_table_sources(_tables_dir())
    return {table_name: {column.name for column in table.columns} for table_name, table in metadata.tables.items()}


def _tables_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "tables"


def _parse_table_sources(tables_dir: Path) -> dict[str, set[str]]:
    schema: dict[str, set[str]] = {}
    for path in sorted(tables_dir.glob("*.py")):
        if path.name in {"__init__.py", "base.py", "helpers.py"}:
            continue
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            table_call = node.value
            if not isinstance(table_call, ast.Call) or _call_name(table_call.func) != "table":
                continue
            if not table_call.args or not isinstance(table_call.args[0], ast.Constant) or not isinstance(table_call.args[0].value, str):
                continue
            table_name = table_call.args[0].value
            columns: set[str] = set()
            for arg in table_call.args[1:]:
                if not isinstance(arg, ast.Call):
                    continue
                func_name = _call_name(arg.func)
                if func_name in {"text_col", "int_col", "float_col"}:
                    if arg.args and isinstance(arg.args[0], ast.Constant) and isinstance(arg.args[0].value, str):
                        columns.add(arg.args[0].value)
                elif func_name == "project_id":
                    columns.add("project_id")
            schema[table_name] = columns
    return schema


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _discover_legacy_sqlite_tables(upload_root: Path) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = defaultdict(set)
    for sqlite_path in _iter_sqlite_paths(upload_root):
        with sqlite3.connect(sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            for table_name in _list_sqlite_tables(connection):
                tables[table_name].update(_table_columns(connection, table_name))
    return dict(tables)


def _discover_json_expectations(
    upload_root: Path,
    json_artifact_rules: dict[str, dict[str, dict[str, list[str]]]],
) -> dict[str, set[str]]:
    expected: dict[str, set[str]] = defaultdict(set)
    for artifact_name, rule in json_artifact_rules.items():
        for artifact_path in upload_root.rglob(artifact_name):
            if not artifact_path.is_file():
                continue
            tables = rule.get("tables", {})
            for table_name, columns in tables.items():
                expected[table_name].update(columns)
    return dict(expected)


def _iter_sqlite_paths(upload_root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in SQLITE_GLOBS:
        for path in upload_root.rglob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _list_sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return sorted(row["name"] for row in rows)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return sorted(row["name"] for row in rows)


if __name__ == "__main__":
    raise SystemExit(main())
