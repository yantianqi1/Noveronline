"""LLM facility repository.

Operates on GLOBAL tables (no project_id): llm_channels, llm_models,
llm_module_bindings.  Replaces the old ``llm_storage.py`` connect-only layer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.llm import llm_channels, llm_models, llm_module_bindings

from .base import BaseRepository


class LlmRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def list_channels(self) -> list[dict[str, Any]]:
        stmt = select(llm_channels).order_by(
            llm_channels.c.created_at.desc(),
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_channel(self, channel_key: str) -> dict[str, Any] | None:
        stmt = select(llm_channels).where(
            llm_channels.c.channel_key == channel_key,
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def upsert_channel(self, values: dict[str, Any]) -> None:
        """INSERT OR REPLACE a channel row.

        ``values`` must include ``channel_key`` and all NOT NULL columns.
        """
        channel_key = values["channel_key"]
        with self.connect() as conn:
            existing = conn.execute(
                select(llm_channels).where(
                    llm_channels.c.channel_key == channel_key,
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(llm_channels).values(**values))
            else:
                conn.execute(
                    update(llm_channels)
                    .where(llm_channels.c.channel_key == channel_key)
                    .values(**values),
                )

    def delete_channel(self, channel_key: str) -> int:
        """Delete a channel and cascade-delete its models and bindings."""
        with self.connect() as conn:
            conn.execute(
                delete(llm_models).where(llm_models.c.channel_key == channel_key),
            )
            conn.execute(
                delete(llm_module_bindings).where(
                    llm_module_bindings.c.channel_key == channel_key,
                ),
            )
            result = conn.execute(
                delete(llm_channels).where(
                    llm_channels.c.channel_key == channel_key,
                ),
            )
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def list_models(self, channel_key: str | None = None) -> list[dict[str, Any]]:
        stmt = select(llm_models).order_by(llm_models.c.model_id.asc())
        if channel_key is not None:
            stmt = stmt.where(llm_models.c.channel_key == channel_key)
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_model(self, channel_key: str, model_id: str) -> dict[str, Any] | None:
        stmt = select(llm_models).where(
            and_(
                llm_models.c.channel_key == channel_key,
                llm_models.c.model_id == model_id,
            ),
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def sync_models(self, channel_key: str, models: list[dict[str, Any]]) -> None:
        """Replace all models for *channel_key* with *models*.

        Each dict in *models* must contain at least ``model_id``,
        ``fetched_at``, and ``raw_payload``.
        """
        with self.connect() as conn:
            conn.execute(
                delete(llm_models).where(llm_models.c.channel_key == channel_key),
            )
            for m in models:
                conn.execute(
                    insert(llm_models).values(channel_key=channel_key, **m),
                )

    # ------------------------------------------------------------------
    # Module bindings
    # ------------------------------------------------------------------

    def list_bindings(self) -> list[dict[str, Any]]:
        stmt = select(llm_module_bindings)
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_binding(self, module_key: str) -> dict[str, Any] | None:
        stmt = select(llm_module_bindings).where(
            llm_module_bindings.c.module_key == module_key,
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def upsert_binding(self, values: dict[str, Any]) -> None:
        """INSERT OR REPLACE a module binding.

        ``values`` must include ``module_key``.
        """
        module_key = values["module_key"]
        with self.connect() as conn:
            existing = conn.execute(
                select(llm_module_bindings).where(
                    llm_module_bindings.c.module_key == module_key,
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(llm_module_bindings).values(**values))
            else:
                conn.execute(
                    update(llm_module_bindings)
                    .where(llm_module_bindings.c.module_key == module_key)
                    .values(**values),
                )

    def delete_binding(self, module_key: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(llm_module_bindings).where(
                    llm_module_bindings.c.module_key == module_key,
                ),
            )
            return result.rowcount or 0
