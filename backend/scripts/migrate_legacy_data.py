"""Orchestrator for the multi-domain legacy-to-unified migration.

Walks every project directory under ``uploads/projects/`` and runs every
project-scoped domain migrator, then runs every global-scoped migrator
once against ``uploads/system/``. Delegates per-domain logic to the
``scripts.migrations`` sub-package.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.database import create_engine_from_settings, init_db

from .migrations import ALL_MIGRATORS, BaseDomainMigrator, MigrationContext


def migrate_legacy_data(
    upload_root: Path,
    database_url: str | None = None,
    *,
    dry_run: bool = False,
    replace_project: bool = True,
) -> dict[str, dict[str, int]]:
    """Run every registered domain migrator. Returns the aggregated report."""
    settings = Settings(DATABASE_URL=database_url or Settings().DATABASE_URL)
    engine = create_engine_from_settings(settings)
    init_db(engine)

    ctx = MigrationContext(
        upload_root=upload_root,
        engine=engine,
        dry_run=dry_run,
        replace_project=replace_project,
    )

    project_scoped = [m for m in ALL_MIGRATORS if m.is_project_scoped]
    global_scoped = [m for m in ALL_MIGRATORS if not m.is_project_scoped]

    for project_dir in _project_dirs(upload_root):
        ctx.project_id = project_dir.name
        for migrator in project_scoped:
            migrator.run(ctx)

    ctx.project_id = None
    for migrator in global_scoped:
        migrator.run(ctx)

    return ctx.report


def _project_dirs(upload_root: Path) -> list[Path]:
    projects_root = upload_root / "projects"
    if not projects_root.exists():
        return []
    return sorted(path for path in projects_root.iterdir() if path.is_dir())


def _aggregate_counts(report: dict[str, dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for counts in report.values():
        for table_name, count in counts.items():
            totals[table_name] = totals.get(table_name, 0) + count
    return totals


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate all legacy data silos into the unified database.")
    parser.add_argument("--upload-root", default="uploads")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing")
    parser.add_argument("--no-replace", action="store_true", help="Skip project-row replacement (no-op for now)")
    parser.add_argument("--json", action="store_true", help="Emit the full per-scope report as JSON")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = migrate_legacy_data(
        Path(args.upload_root),
        args.database_url,
        dry_run=args.dry_run,
        replace_project=not args.no_replace,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    for table_name, count in sorted(_aggregate_counts(report).items()):
        print(f"{table_name}: {count}")


__all__ = ["migrate_legacy_data"]


if __name__ == "__main__":
    main()
