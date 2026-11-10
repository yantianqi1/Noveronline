"""Asset library repository.

Operates on: ``assets``, ``asset_links``.

Replaces the old ``assets/assets_storage.py`` connect-only layer.  Uses
BaseRepository (not ProjectScopedRepository) because the ``assets`` table
uses ``scope`` + optional ``project_id`` rather than a mandatory project_id
column.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, delete, false, insert, or_, select, update

from app.tables.assets import asset_links, assets

from .base import BaseRepository


class AssetRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # assets - read
    # ------------------------------------------------------------------

    def list_assets(
        self,
        *,
        scope: str | None = None,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = select(assets)
        clauses = []
        if scope is not None:
            clauses.append(assets.c.scope == scope)
        if project_id is not None:
            clauses.append(assets.c.project_id == project_id)
        if asset_type is not None:
            clauses.append(assets.c.asset_type == asset_type)
        if category is not None:
            clauses.append(assets.c.category == category)
        if enabled_only:
            clauses.append(assets.c.enabled == 1)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(
            assets.c.pinned.desc(),
            assets.c.updated_at.desc(),
        ).limit(limit).offset(offset)
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    @staticmethod
    def _scope_clause(scope: str | None, project_id: str | None):
        if scope is None:
            return None
        if scope == "global":
            return and_(assets.c.scope == "global", assets.c.project_id.is_(None))
        if scope == "project" and project_id:
            return and_(assets.c.scope == "project", assets.c.project_id == project_id)
        return false()

    def get_asset(
        self,
        asset_id: str,
        *,
        scope: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        clauses = [assets.c.asset_id == asset_id]
        scope_clause = self._scope_clause(scope, project_id)
        if scope_clause is not None:
            clauses.append(scope_clause)
        stmt = select(assets).where(and_(*clauses))
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def get_project_id(self, asset_id: str) -> str | None:
        """Resolve the owning project for a project-scoped asset.

        This returns only scope metadata. Callers must still perform the
        actual read through ``get_asset(..., scope="project", project_id=...)``.
        """
        stmt = select(assets.c.project_id).where(
            and_(
                assets.c.asset_id == asset_id,
                assets.c.scope == "project",
                assets.c.project_id.is_not(None),
            ),
        )
        with self.connect() as conn:
            row = conn.execute(stmt).fetchone()
        return str(row[0]) if row and row[0] else None

    def list_by_scope(
        self,
        scope: str,
        *,
        project_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Convenience wrapper: filter by scope (and optional project_id)."""
        return self.list_assets(scope=scope, project_id=project_id, limit=limit)

    # ------------------------------------------------------------------
    # assets - write
    # ------------------------------------------------------------------

    def create_asset(self, values: dict[str, Any]) -> None:
        """INSERT a new asset row.  ``values`` must include ``asset_id``."""
        with self.connect() as conn:
            conn.execute(insert(assets).values(**values))

    def update_asset(self, asset_id: str, *, scope: str, project_id: str | None = None, **kwargs: Any) -> int:
        """UPDATE specific columns for an asset.

        Only the keyword arguments provided are written; unknown keys are
        silently ignored so callers do not need to pre-filter.
        """
        allowed = {c.name for c in assets.columns} - {"asset_id"}
        payload = {k: v for k, v in kwargs.items() if k in allowed}
        if not payload:
            return 0
        scope_clause = self._scope_clause(scope, project_id)
        with self.connect() as conn:
            result = conn.execute(
                update(assets).where(
                    and_(assets.c.asset_id == asset_id, scope_clause),
                ).values(**payload),
            )
            return result.rowcount or 0

    def delete_asset(self, asset_id: str, *, scope: str, project_id: str | None = None) -> int:
        """Delete an asset and all its links (both directions)."""
        with self.connect() as conn:
            result = conn.execute(delete(assets).where(and_(
                assets.c.asset_id == asset_id,
                self._scope_clause(scope, project_id),
            )))
            if not result.rowcount:
                return 0
            conn.execute(delete(asset_links).where(
                or_(
                    asset_links.c.src_asset_id == asset_id,
                    asset_links.c.dst_asset_id == asset_id,
                ),
            ))
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # assets - search
    # ------------------------------------------------------------------

    def search_assets(
        self,
        query: str,
        *,
        scope: str | None = None,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """LIKE search on title, summary, content."""
        keyword = f"%{query}%"
        like_clause = or_(
            assets.c.title.like(keyword),
            assets.c.summary.like(keyword),
            assets.c.content.like(keyword),
        )
        conditions: list[Any] = [like_clause]
        if scope is not None:
            conditions.append(assets.c.scope == scope)
        if project_id is not None:
            conditions.append(assets.c.project_id == project_id)
        if asset_type is not None:
            conditions.append(assets.c.asset_type == asset_type)
        if category is not None:
            conditions.append(assets.c.category == category)
        if enabled_only:
            conditions.append(assets.c.enabled == 1)
        stmt = (
            select(assets)
            .where(and_(*conditions))
            .order_by(assets.c.updated_at.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # assets - batch ops
    # ------------------------------------------------------------------

    def batch_set_enabled(
        self,
        asset_ids: list[str],
        enabled: bool,
        *,
        updated_at: str,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        if not asset_ids:
            return 0
        with self.connect() as conn:
            result = conn.execute(
                update(assets)
                .where(and_(
                    assets.c.asset_id.in_(asset_ids),
                    self._scope_clause(scope, project_id),
                ))
                .values(enabled=1 if enabled else 0, updated_at=updated_at),
            )
            return result.rowcount or 0

    def batch_set_category(
        self,
        asset_ids: list[str],
        category: str,
        *,
        updated_at: str,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        if not asset_ids:
            return 0
        with self.connect() as conn:
            result = conn.execute(
                update(assets)
                .where(and_(
                    assets.c.asset_id.in_(asset_ids),
                    self._scope_clause(scope, project_id),
                ))
                .values(category=category or "", updated_at=updated_at),
            )
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # asset_links
    # ------------------------------------------------------------------

    def upsert_link(self, values: dict[str, Any]) -> None:
        """INSERT OR IGNORE a link row (composite PK: src, dst, relation)."""
        with self.connect() as conn:
            existing = conn.execute(
                select(asset_links).where(
                    and_(
                        asset_links.c.src_asset_id == values["src_asset_id"],
                        asset_links.c.dst_asset_id == values["dst_asset_id"],
                        asset_links.c.relation == values["relation"],
                    ),
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(asset_links).values(**values))

    def list_links(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all outgoing links from *asset_id*."""
        stmt = select(asset_links).where(and_(
            asset_links.c.src_asset_id == asset_id,
            asset_links.c.project_id == (project_id if scope == "project" else None),
        ))
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def delete_links_for_asset(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        """Delete links for an asset inside the requested scope."""
        with self.connect() as conn:
            result = conn.execute(
                delete(asset_links).where(
                    and_(
                        or_(
                            asset_links.c.src_asset_id == asset_id,
                            asset_links.c.dst_asset_id == asset_id,
                        ),
                        asset_links.c.project_id == (
                            project_id if scope == "project" else None
                        ),
                    ),
                ),
            )
            return result.rowcount or 0
