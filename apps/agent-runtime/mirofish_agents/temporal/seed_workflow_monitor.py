from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

from temporalio.api.enums.v1 import WorkflowExecutionStatus
from temporalio.client import Client, WorkflowFailureError


_SEED_RUN_ROWS_SQL = """
SELECT tenant_id::text, run_id::text, project_id::text,
       temporal_workflow_id, temporal_run_id, status
FROM workflow_runs
WHERE workflow_type = 'seed_pipeline'
  AND status IN ('queued', 'running')
  AND temporal_workflow_id <> ''
ORDER BY updated_at ASC
LIMIT 100
"""


class SeedWorkflowStatusMonitor:
    """Reconcile seed pipeline run rows with the real Temporal workflow state.

    A seed activity that is force-killed (heartbeat or start-to-close timeout,
    worker crash, worker restart) never gets the chance to write its terminal
    status, so ``workflow_runs`` can stay ``running`` forever while the Temporal
    workflow is already closed. That wedges the Overview UI and blocks retries
    (retry admission only accepts failed/cancelled rows).

    This monitor polls Temporal for closed seed workflows and marks the matching
    rows with their truthful terminal state so a run never silently wedges
    again. Runs inside the seed-heavy worker; a single instance is enough and
    the UPDATE is idempotent (only touches queued/running rows).
    """

    def __init__(
        self,
        *,
        client: Client,
        connect: Callable[[], Any],
        interval_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._connect = connect
        self._interval_seconds = interval_seconds

    @classmethod
    def from_env(
        cls,
        *,
        client: Client,
        database_url: str | None = None,
    ) -> "SeedWorkflowStatusMonitor | None":
        database_url = (database_url or os.environ.get("DATABASE_URL", "")).strip()
        if not database_url:
            return None
        try:
            import psycopg
        except ImportError:  # pragma: no cover - depends on runtime packaging
            return None
        return cls(client=client, connect=lambda: psycopg.connect(database_url))

    async def run_forever(self) -> None:
        while True:
            try:
                await self._reconcile_once()
            except Exception:
                # A failed poll must never take down the worker; retry next tick.
                pass
            await asyncio.sleep(self._interval_seconds)

    async def _reconcile_once(self) -> None:
        for row in self._load_rows():
            await self._reconcile_row(row)

    def _load_rows(self) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SEED_RUN_ROWS_SQL)
                columns = [column.name for column in (cursor.description or [])]
                return [dict(zip(columns, values)) for values in cursor.fetchall()]
        finally:
            connection.close()

    async def _reconcile_row(self, row: dict[str, Any]) -> None:
        workflow_id = str(row.get("temporal_workflow_id") or "").strip()
        if not workflow_id:
            return
        run_id = str(row.get("temporal_run_id") or "").strip() or None
        handle = self._client.get_workflow_handle(workflow_id, run_id=run_id)
        try:
            description = await handle.describe()
        except Exception:
            # NotFound or RPC flake: leave the row alone, retry next tick.
            return
        status = description.status
        if status in (
            WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING,
            WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_UNSPECIFIED,
        ):
            return
        terminal_status, error_code, error_message = _terminal_state_for(status)
        if terminal_status == "completed":
            try:
                result = await handle.result()
            except WorkflowFailureError:
                terminal_status = "failed"
                error_code = "WORKFLOW_FAILED"
                error_message = "seed workflow failed on the server"
            except Exception:
                terminal_status = "failed"
                error_code = "WORKFLOW_RESULT_UNAVAILABLE"
                error_message = "seed workflow result was unavailable"
            else:
                if not isinstance(result, dict) or result.get("status") != "completed":
                    terminal_status = "failed"
                    error_code = "WORKFLOW_FAILED"
                    error_message = "seed workflow closed without a completed stage result"
        self._update_row(row, terminal_status, error_code, error_message)

    def _update_row(
        self,
        row: dict[str, Any],
        status: str,
        error_code: str,
        error_message: str,
    ) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE workflow_runs
                       SET status = %s,
                           progress = CASE WHEN %s IN ('completed', 'failed') THEN 100 ELSE progress END,
                           error_code = %s,
                           error_message = %s,
                           updated_at = now()
                       WHERE tenant_id = %s::uuid
                         AND run_id = %s::uuid
                         AND workflow_type = 'seed_pipeline'
                         AND status IN ('queued', 'running')""",
                    (
                        status,
                        status,
                        error_code,
                        error_message,
                        row.get("tenant_id"),
                        row.get("run_id"),
                    ),
                )
            connection.commit()
        finally:
            connection.close()


def _terminal_state_for(status: WorkflowExecutionStatus) -> tuple[str, str, str]:
    if status == WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_COMPLETED:
        return "completed", "", ""
    if status in (
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_CANCELED,
        WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_TERMINATED,
    ):
        return "cancelled", "WORKFLOW_CANCELLED", "seed workflow was cancelled"
    # FAILED / TIMED_OUT / any other closed state.
    return "failed", "WORKFLOW_FAILED", "seed workflow failed on the server"
