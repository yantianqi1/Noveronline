from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from mirofish_agents.temporal.seed_workflow_monitor import SeedWorkflowStatusMonitor


@dataclass
class FakeDescription:
    status: Any


@dataclass
class FakeHandle:
    status: Any
    result_value: Any = None
    result_error: Exception | None = None
    describe_error: Exception | None = None
    described: bool = False
    result_called: bool = False

    async def describe(self) -> FakeDescription:
        self.described = True
        if self.describe_error is not None:
            raise self.describe_error
        return FakeDescription(status=self.status)

    async def result(self) -> Any:
        self.result_called = True
        if self.result_error is not None:
            raise self.result_error
        return self.result_value


@dataclass
class FakeClient:
    handles: dict[str, FakeHandle] = field(default_factory=dict)

    def get_workflow_handle(self, workflow_id: str, run_id: str | None = None) -> FakeHandle:
        return self.handles[workflow_id]


class FakeCursor:
    def __init__(self, rows: list[list[Any]], columns: list[str], updates: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._rows = rows
        self._columns = columns
        self._updates = updates
        self._fetch_index = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    @property
    def description(self) -> list[Any]:
        return [type("Column", (), {"name": column})() for column in self._columns]

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        if sql.lstrip().upper().startswith("UPDATE"):
            self._updates.append((sql, tuple(params or ())))
        self._fetch_index = 0

    def fetchall(self) -> list[list[Any]]:
        return self._rows


class FakeConnection:
    def __init__(self, rows: list[list[Any]], columns: list[str]) -> None:
        self._rows = rows
        self._columns = columns
        self.updates: list[tuple[str, tuple[Any, ...]]] = []
        self.committed = 0
        self.closed = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows, self._columns, self.updates)

    def commit(self) -> None:
        self.committed += 1

    def close(self) -> None:
        self.closed += 1


def _row(
    *,
    tenant_id: str = "t1",
    run_id: str = "r1",
    temporal_workflow_id: str = "seed_run_r1_retry_wf1",
    status: str = "running",
) -> dict[str, str]:
    return {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "project_id": "p1",
        "temporal_workflow_id": temporal_workflow_id,
        "temporal_run_id": "",
        "status": status,
    }


def _monitor(client: FakeClient, connection: FakeConnection) -> SeedWorkflowStatusMonitor:
    return SeedWorkflowStatusMonitor(
        client=client,  # type: ignore[arg-type]
        connect=lambda: connection,  # type: ignore[arg-type]
        interval_seconds=0.01,
    )


def _rows_as_cursor_rows(rows: list[dict[str, str]]) -> list[list[Any]]:
    columns = ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"]
    return [[r[column] for column in columns] for r in rows]


def test_monitor_skips_still_running_workflows() -> None:
    import asyncio

    from temporalio.api.enums.v1 import WorkflowExecutionStatus

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert connection.updates == []
    assert client.handles["seed_run_r1_retry_wf1"].described


def test_monitor_marks_failed_workflow_as_failed() -> None:
    import asyncio

    from temporalio.api.enums.v1 import WorkflowExecutionStatus

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_FAILED
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert len(connection.updates) == 1
    sql, params = connection.updates[0]
    assert "UPDATE workflow_runs" in sql
    assert params[0] == "failed"
    assert params[1] == "failed"  # progress CASE input
    assert params[2] == "WORKFLOW_FAILED"
    assert "t1" in params and "r1" in params


def test_monitor_marks_completed_workflow_as_completed() -> None:
    import asyncio

    from temporalio.api.enums.v1 import WorkflowExecutionStatus

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED,
                result_value={"status": "completed", "stage": "finalize"},
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert len(connection.updates) == 1
    assert connection.updates[0][1][0] == "completed"
    assert client.handles["seed_run_r1_retry_wf1"].result_called


def test_monitor_marks_completed_workflow_with_failed_payload_as_failed() -> None:
    import asyncio

    from temporalio.api.enums.v1 import WorkflowExecutionStatus

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED,
                result_value={"status": "failed", "error": {"code": "LLM_PROVIDER_ERROR"}},
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert len(connection.updates) == 1
    assert connection.updates[0][1][0] == "failed"
    assert connection.updates[0][1][2] == "WORKFLOW_FAILED"


def test_monitor_marks_cancelled_workflow_as_cancelled() -> None:
    import asyncio

    from temporalio.api.enums.v1 import WorkflowExecutionStatus

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert len(connection.updates) == 1
    assert connection.updates[0][1][0] == "cancelled"
    assert connection.updates[0][1][2] == "WORKFLOW_CANCELLED"


def test_monitor_leaves_row_alone_when_describe_fails() -> None:
    import asyncio

    rows = [_row(status="running")]
    client = FakeClient(
        handles={
            "seed_run_r1_retry_wf1": FakeHandle(
                status=None,
                describe_error=RuntimeError("workflow not found"),
            )
        }
    )
    connection = FakeConnection(_rows_as_cursor_rows(rows), ["tenant_id", "run_id", "project_id", "temporal_workflow_id", "temporal_run_id", "status"])
    monitor = _monitor(client, connection)

    asyncio.run(monitor._reconcile_once())

    assert connection.updates == []
