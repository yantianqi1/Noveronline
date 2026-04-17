"""Migrate the global ``archive_library.sqlite3`` silo."""

from __future__ import annotations

from .base import BaseDomainMigrator, MigrationContext, copy_sqlite_into_unified


class ArchiveLibraryDomainMigrator(BaseDomainMigrator):
    domain_name = "archive_library"
    is_project_scoped = False

    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        source_path = ctx.upload_root / "system" / "archive_library.sqlite3"
        return copy_sqlite_into_unified(
            source_path=source_path,
            engine=ctx.engine,
            project_id=None,
            dry_run=ctx.dry_run,
        )


__all__ = ["ArchiveLibraryDomainMigrator"]
