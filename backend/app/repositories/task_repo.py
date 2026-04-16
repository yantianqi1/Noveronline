"""Task runtime repository."""

from __future__ import annotations

from sqlalchemy import Engine, insert, select, update

from app.tables.task import task_runs

from .base import BaseRepository


class TaskRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.table = task_runs

    def get_task(self, task_id: str) -> dict | None:
        statement = select(self.table).where(self.table.c.task_id == task_id).limit(1)
        with self.connect() as connection:
            return self.row_to_dict(connection.execute(statement).fetchone())

    def update_task(self, values: dict) -> None:
        with self.connect() as connection:
            exists = connection.execute(
                select(self.table).where(self.table.c.task_id == values["task_id"]).limit(1)
            ).fetchone()
            connection.execute(self._statement(values, exists is not None))

    def _statement(self, values: dict, exists: bool):
        if exists:
            return update(self.table).where(self.table.c.task_id == values["task_id"]).values(**values)
        return insert(self.table).values(**values)
