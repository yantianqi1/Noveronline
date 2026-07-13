from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from mirofish_agents.legacy_import.service import LegacyImportService, write_report
from mirofish_agents.legacy_import.objects import object_lifecycle_from_env


LEGACY_IMPORT_TASK_QUEUE = "legacy-import"


def _service(payload: dict[str, Any]) -> LegacyImportService:
    target_dsn = os.environ.get("LEGACY_IMPORT_DATABASE_URL", "").strip()
    if not target_dsn:
        raise RuntimeError("LEGACY_IMPORT_DATABASE_URL is required")
    scoped_payload = _authorized_payload_paths(
        payload, os.environ.get("LEGACY_IMPORT_SOURCE_ROOT", "").strip()
    )
    return LegacyImportService(
        source_path=scoped_payload["source_path"],
        artifact_root=scoped_payload.get("artifact_root"),
        import_id=payload["import_id"],
        tenant_id=payload["tenant_id"],
        project_id=payload["project_id"],
        actor_user_id=payload["actor_user_id"],
        source_project_id=payload["source_project_id"],
        target_dsn=target_dsn,
        object_lifecycle=object_lifecycle_from_env(target_dsn),
    )


def _authorized_payload_paths(payload: dict[str, Any], source_root: str) -> dict[str, Any]:
    if not source_root:
        raise RuntimeError("LEGACY_IMPORT_SOURCE_ROOT is required")
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise RuntimeError("legacy import source root is unavailable")
    scoped = dict(payload)
    scoped["source_path"] = str(
        _path_under_source_root(root, payload.get("source_path"), expect_directory=False)
    )
    artifact_root = payload.get("artifact_root")
    if artifact_root not in (None, ""):
        scoped["artifact_root"] = str(
            _path_under_source_root(root, artifact_root, expect_directory=True)
        )
    return scoped


def _path_under_source_root(
    root: Path, raw_value: Any, *, expect_directory: bool
) -> Path:
    value = str(raw_value or "").strip()
    if not value:
        raise RuntimeError("legacy import source path is required")
    supplied = Path(value)
    lexical = supplied if supplied.is_absolute() else root / supplied
    normalized = Path(os.path.abspath(lexical))
    try:
        relative = normalized.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("legacy import source path is outside the authorized root") from exc
    for index in range(1, len(relative.parts) + 1):
        if (root / Path(*relative.parts[:index])).is_symlink():
            raise RuntimeError("legacy import source symlinks are unsupported")
    candidate = normalized.resolve()
    valid = candidate.is_dir() if expect_directory else candidate.is_file()
    if not valid:
        raise RuntimeError("legacy import source path is unavailable")
    return candidate


@activity.defn
def legacy_import_plan_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return _service(payload).plan_report()


@activity.defn
def legacy_import_apply_activity(payload: dict[str, Any]) -> dict[str, Any]:
    service = _service(payload)
    report = service.apply(
        execute=True,
        heartbeat=activity.heartbeat,
        expected_source_fingerprint=str(payload.get("expected_source_fingerprint") or ""),
        expected_plan_hash=str(payload.get("expected_plan_hash") or ""),
    )
    write_report(report, payload.get("report_output"))
    return report


@activity.defn
def legacy_import_verify_activity(payload: dict[str, Any]) -> dict[str, Any]:
    service = _service(payload)
    report = service.verify(
        expected_source_fingerprint=str(payload.get("expected_source_fingerprint") or ""),
        expected_plan_hash=str(payload.get("expected_plan_hash") or ""),
    )
    write_report(report, payload.get("report_output"))
    return report


@workflow.defn
class LegacyImportWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=5)
        plan = await workflow.execute_activity(
            legacy_import_plan_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )
        if plan["status"] == "failed":
            return _terminal(plan)
        execution_payload = {
            **payload,
            "expected_source_fingerprint": plan["source_fingerprint"],
            "expected_plan_hash": plan["plan_hash"],
        }
        applied = await workflow.execute_activity(
            legacy_import_apply_activity,
            execution_payload,
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )
        if applied["status"] == "failed":
            return _terminal(applied)
        verified = await workflow.execute_activity(
            legacy_import_verify_activity,
            execution_payload,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )
        return _terminal(verified)


def _terminal(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report["status"],
        "family_counts": report["family_counts"],
        "report_digest": report["report_digest"],
    }


def worker_spec() -> dict[str, Any]:
    return {
        "task_queue": LEGACY_IMPORT_TASK_QUEUE,
        "workflows": [LegacyImportWorkflow.__name__],
        "activities": [
            legacy_import_plan_activity.__name__,
            legacy_import_apply_activity.__name__,
            legacy_import_verify_activity.__name__,
        ],
    }
