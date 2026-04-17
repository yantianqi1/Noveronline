"""Migrate legacy assets silos (per-project + global)."""

from __future__ import annotations

from .base import BaseDomainMigrator, MigrationContext, copy_sqlite_into_unified


class ProjectAssetsDomainMigrator(BaseDomainMigrator):
    domain_name = "project_assets"
    is_project_scoped = True

    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        if not ctx.project_id:
            return {}
        source_path = ctx.upload_root / "projects" / ctx.project_id / "project_assets.sqlite3"
        return copy_sqlite_into_unified(
            source_path=source_path,
            engine=ctx.engine,
            project_id=ctx.project_id,
            dry_run=ctx.dry_run,
        )


class GlobalAssetsDomainMigrator(BaseDomainMigrator):
    domain_name = "assets_library"
    is_project_scoped = False

    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        source_path = ctx.upload_root / "system" / "assets_library.sqlite3"
        return copy_sqlite_into_unified(
            source_path=source_path,
            engine=ctx.engine,
            project_id=None,
            dry_run=ctx.dry_run,
        )


__all__ = [
    "GlobalAssetsDomainMigrator",
    "ProjectAssetsDomainMigrator",
]
