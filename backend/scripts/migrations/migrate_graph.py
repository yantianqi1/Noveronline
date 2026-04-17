"""Migrate legacy ``story_graph.sqlite3`` into unified graph tables."""

from __future__ import annotations

from .base import BaseDomainMigrator, MigrationContext, copy_sqlite_into_unified


class GraphDomainMigrator(BaseDomainMigrator):
    domain_name = "story_graph"
    is_project_scoped = True

    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        if not ctx.project_id:
            return {}
        source_path = ctx.upload_root / "projects" / ctx.project_id / "story_graph.sqlite3"
        return copy_sqlite_into_unified(
            source_path=source_path,
            engine=ctx.engine,
            project_id=ctx.project_id,
            dry_run=ctx.dry_run,
        )


__all__ = ["GraphDomainMigrator"]
