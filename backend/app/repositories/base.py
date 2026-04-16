"""Repository base classes for SQLAlchemy Core data access."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, Table, and_, delete, insert, select, update


class BaseRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.connect() as connection:
            yield connection
            connection.commit()

    @staticmethod
    def row_to_dict(row) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row._mapping)


class ProjectScopedRepository(BaseRepository):
    def __init__(self, engine: Engine, table: Table):
        super().__init__(engine)
        if "project_id" not in table.c:
            raise ValueError(f"{table.name} is not project scoped")
        self.table = table

    def project_condition(self, project_id: str):
        if not project_id:
            raise ValueError("project_id is required")
        return self.table.c.project_id == project_id

    def list_by_project(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        statement = select(self.table).where(self.project_condition(project_id)).limit(limit)
        with self.connect() as connection:
            return [dict(row._mapping) for row in connection.execute(statement).fetchall()]

    def get_one(self, project_id: str, **filters) -> dict[str, Any] | None:
        statement = select(self.table).where(self._where(project_id, filters)).limit(1)
        with self.connect() as connection:
            return self.row_to_dict(connection.execute(statement).fetchone())

    def upsert_by_keys(self, project_id: str, values: dict[str, Any], keys: tuple[str, ...]) -> None:
        payload = {"project_id": project_id, **values}
        filters = {key: payload[key] for key in keys}
        with self.connect() as connection:
            existing = connection.execute(
                select(self.table).where(self._where(project_id, filters)).limit(1)
            ).fetchone()
            connection.execute(self._upsert_statement(payload, filters, existing is not None))

    def delete_one(self, project_id: str, **filters) -> int:
        statement = delete(self.table).where(self._where(project_id, filters))
        with self.connect() as connection:
            result = connection.execute(statement)
            return result.rowcount or 0

    def exists(self, project_id: str, **filters) -> bool:
        return self.get_one(project_id, **filters) is not None

    def _where(self, project_id: str, filters: dict[str, Any]):
        clauses = [self.project_condition(project_id)]
        clauses.extend(self.table.c[key] == value for key, value in filters.items())
        return and_(*clauses)

    def _upsert_statement(self, payload: dict[str, Any], filters: dict[str, Any], exists: bool):
        if not exists:
            return insert(self.table).values(**payload)
        return update(self.table).where(self._where(payload["project_id"], filters)).values(**payload)
