from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .completion import has_unresolved_families, unresolved_reason_codes
from .models import make_report, stable_hash
from .objects import (
    LegacyObjectConflict,
    LegacyObjectLifecycle,
    ObjectOperationResult,
    plan_legacy_objects,
)
from .planner import LegacyImportPlanner
from .source import LegacySource
from .target import PostgresImportTarget


class LegacyImportService:
    def __init__(
        self,
        *,
        source_path: str,
        artifact_root: str | None,
        import_id: str,
        tenant_id: str,
        project_id: str,
        actor_user_id: str,
        source_project_id: str,
        target_dsn: str | None = None,
        object_lifecycle: LegacyObjectLifecycle | None = None,
    ) -> None:
        self.source = LegacySource(source_path, artifact_root)
        self.import_id = import_id
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.actor_user_id = actor_user_id
        self.source_project_id = source_project_id
        self.target_dsn = target_dsn
        self.object_lifecycle = object_lifecycle

    def inspect(self) -> dict[str, Any]:
        started = time.monotonic()
        inspection = self.source.inspect()
        report = {
            "schema_version": 1,
            "operation": "inspect",
            "status": "complete",
            **inspection.public_dict(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        report["report_digest"] = stable_hash(report)
        return report

    def plan(self) -> Any:
        plan, _ = self._snapshot()
        return plan

    def _snapshot(self) -> tuple[Any, list[Any]]:
        plan = LegacyImportPlanner(
            self.source,
            import_id=self.import_id,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            actor_user_id=self.actor_user_id,
            source_project_id=self.source_project_id,
        ).build()
        objects = self._planned_objects()
        if self.source.inspect().fingerprint != plan.source.fingerprint:
            raise RuntimeError("SOURCE_CHANGED_DURING_PLAN")
        source_family = plan.families["source"]
        source_family.deferred_count = 0
        source_family.unsupported_count = sum(item.payload is None for item in objects)
        source_family.reason_codes = [
            code
            for code in source_family.reason_codes
            if code != "OBJECT_STORAGE_DESTINATION_REQUIRED"
        ]
        if source_family.unsupported_count:
            source_family.reason_codes.append("APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED")
        project_family = plan.families["project"]
        if "SOURCE_PROJECT_METADATA_ABSENT" in project_family.reason_codes:
            project_family.deferred_count = max(1, project_family.deferred_count)
        return plan, objects

    def plan_report(
        self, plan: Any | None = None, objects: list[Any] | None = None
    ) -> dict[str, Any]:
        started = time.monotonic()
        if plan is None or objects is None:
            plan, objects = self._snapshot()
        counts = {
            name: {
                "planned": len(family.records),
                "imported": 0,
                "unchanged": family.source_count if name == "project" else 0,
                "deferred": family.deferred_count,
                "unsupported": family.unsupported_count,
                "conflict": 0,
                "rolled_back": 0,
            }
            for name, family in plan.families.items()
        }
        unresolved = unresolved_reason_codes(plan.families)
        status = "partial" if has_unresolved_families(plan.families) else "complete"
        report = make_report(
            operation="plan",
            import_id=plan.import_id,
            status=status,
            source_fingerprint=plan.source.fingerprint,
            plan_hash=plan.plan_hash,
            family_counts=counts,
            family_reasons={
                name: sorted(set(family.reason_codes))
                for name, family in plan.families.items()
                if family.reason_codes
            },
            blockers=unresolved,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        report["object_counts"] = {
            "planned": len(objects),
            "uploadable": sum(item.payload is not None for item in objects),
            "metadata_only": sum(item.payload is None for item in objects),
        }
        report["object_reasons"] = sorted(
            {item.unsupported_reason for item in objects if item.unsupported_reason}
        )
        report.pop("report_digest", None)
        report["report_digest"] = stable_hash(report)
        return report

    def apply(
        self,
        *,
        execute: bool = False,
        heartbeat: Any | None = None,
        expected_source_fingerprint: str | None = None,
        expected_plan_hash: str | None = None,
    ) -> dict[str, Any]:
        if not execute:
            report = self.plan_report()
            report["operation"] = "apply"
            report["status"] = "partial"
            report["blockers"] = sorted(set(report["blockers"] + ["EXECUTION_NOT_REQUESTED"]))
            report.pop("report_digest", None)
            report["report_digest"] = stable_hash(report)
            return report
        plan, objects = self._snapshot()
        binding_failure = self._binding_failure_report(
            plan,
            objects,
            "apply",
            expected_source_fingerprint,
            expected_plan_hash,
        )
        if binding_failure is not None:
            return binding_failure
        missing_lifecycle = self._missing_lifecycle_report("apply", plan, objects)
        if missing_lifecycle is not None:
            return missing_lifecycle
        target = self._target(heartbeat)
        preflight_blocker = target.preflight(plan)
        if preflight_blocker is not None:
            report = self.plan_report(plan, objects)
            report["operation"] = "apply"
            report["status"] = "failed"
            report["blockers"] = sorted(
                set(report.get("blockers", []) + [preflight_blocker])
            )
            report.pop("report_digest", None)
            report["report_digest"] = stable_hash(report)
            return report
        object_result = self._run_objects("apply", objects)
        if object_result is not None and object_result.status == "failed":
            report = self.plan_report(plan, objects)
            report["operation"] = "apply"
            report["status"] = "failed"
            return self._merge_object_result(report, object_result)
        report = target.apply(plan)
        report = self._reconcile_target_completion(report, plan)
        if report["status"] == "failed" and object_result is not None:
            orphaned = self.object_lifecycle.orphan(
                objects,
                only_object_ids=set(object_result.staged_object_ids),
            )
            return self._merge_object_result(report, orphaned)
        return self._merge_object_result(report, object_result)

    def verify(
        self,
        *,
        expected_source_fingerprint: str | None = None,
        expected_plan_hash: str | None = None,
    ) -> dict[str, Any]:
        plan, objects = self._snapshot()
        binding_failure = self._binding_failure_report(
            plan,
            objects,
            "verify",
            expected_source_fingerprint,
            expected_plan_hash,
        )
        if binding_failure is not None:
            return binding_failure
        missing_lifecycle = self._missing_lifecycle_report("verify", plan, objects)
        if missing_lifecycle is not None:
            return missing_lifecycle
        report = self._reconcile_target_completion(self._target().verify(plan), plan)
        return self._merge_object_result(report, self._run_objects("verify", objects))

    def rollback(
        self,
        *,
        execute: bool = False,
        expected_source_fingerprint: str | None = None,
        expected_plan_hash: str | None = None,
    ) -> dict[str, Any]:
        if not execute:
            report = self.plan_report()
            report["operation"] = "rollback"
            report["status"] = "partial"
            report["blockers"] = sorted(set(report["blockers"] + ["EXECUTION_NOT_REQUESTED"]))
            report.pop("report_digest", None)
            report["report_digest"] = stable_hash(report)
            return report
        plan, objects = self._snapshot()
        binding_failure = self._binding_failure_report(
            plan,
            objects,
            "rollback",
            expected_source_fingerprint,
            expected_plan_hash,
        )
        if binding_failure is not None:
            return binding_failure
        missing_lifecycle = self._missing_lifecycle_report("rollback", plan, objects)
        if missing_lifecycle is not None:
            return missing_lifecycle
        report = self._target().rollback(plan)
        if report["status"] == "failed":
            return report
        return self._merge_object_result(report, self._run_objects("rollback", objects))

    def reconcile_object_version(
        self,
        *,
        object_id: str,
        version_id: str,
        execute: bool = False,
        expected_source_fingerprint: str | None = None,
        expected_plan_hash: str | None = None,
    ) -> dict[str, Any]:
        plan, objects = self._snapshot()
        report = self.plan_report(plan, objects)
        report["operation"] = "reconcile-version"
        if not execute:
            report["status"] = "partial"
            report["blockers"] = sorted(
                set(report.get("blockers", []) + ["EXECUTION_NOT_REQUESTED"])
            )
            report.pop("report_digest", None)
            report["report_digest"] = stable_hash(report)
            return report
        binding_failure = self._binding_failure_report(
            plan,
            objects,
            "reconcile-version",
            expected_source_fingerprint,
            expected_plan_hash,
        )
        if binding_failure is not None:
            return binding_failure
        missing_lifecycle = self._missing_lifecycle_report(
            "reconcile-version", plan, objects
        )
        if missing_lifecycle is not None:
            return missing_lifecycle
        result = self.object_lifecycle.reconcile_version(
            objects,
            object_id=object_id,
            version_id=version_id,
        )
        report["status"] = result.status
        return self._merge_object_result(report, result)

    def _target(self, heartbeat: Any | None = None) -> PostgresImportTarget:
        if not self.target_dsn:
            raise ValueError("target DSN is required for this operation")
        return PostgresImportTarget.from_dsn(self.target_dsn, heartbeat)

    def _run_objects(
        self, operation: str, items: list[Any]
    ) -> ObjectOperationResult | None:
        if self.object_lifecycle is None:
            return None
        try:
            handler = getattr(self.object_lifecycle, operation)
            return handler(items)
        except LegacyObjectConflict as exc:
            return ObjectOperationResult(
                "failed",
                {
                    "planned": 0,
                    "imported": 0,
                    "unchanged": 0,
                    "conflict": 1,
                    "rolled_back": 0,
                    "orphaned": 0,
                },
                (exc.code,),
            )
        except Exception:
            return ObjectOperationResult(
                "failed",
                {
                    "planned": 0,
                    "imported": 0,
                    "unchanged": 0,
                    "conflict": 1,
                    "rolled_back": 0,
                    "orphaned": 0,
                },
                ("LEGACY_OBJECT_PLAN_FAILED",),
            )

    def _planned_objects(self) -> list[Any]:
        return plan_legacy_objects(
            self.source,
            import_id=self.import_id,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_project_id=self.source_project_id,
        )

    def _missing_lifecycle_report(
        self, operation: str, plan: Any, objects: list[Any]
    ) -> dict[str, Any] | None:
        if self.object_lifecycle is not None or not objects:
            return None
        report = self.plan_report(plan, objects)
        report["operation"] = operation
        report["status"] = "failed"
        report["blockers"] = sorted(
            set(report.get("blockers", []) + ["LEGACY_OBJECT_LIFECYCLE_REQUIRED"])
        )
        report.pop("report_digest", None)
        report["report_digest"] = stable_hash(report)
        return report

    def _binding_failure_report(
        self,
        plan: Any,
        objects: list[Any],
        operation: str,
        expected_source_fingerprint: str | None,
        expected_plan_hash: str | None,
    ) -> dict[str, Any] | None:
        if not expected_source_fingerprint or not expected_plan_hash:
            code = "LEGACY_IMPORT_PLAN_BINDING_REQUIRED"
        elif (
            plan.source.fingerprint != expected_source_fingerprint
            or plan.plan_hash != expected_plan_hash
        ):
            code = "LEGACY_IMPORT_PLAN_CHANGED"
        else:
            return None
        report = self.plan_report(plan, objects)
        report["operation"] = operation
        report["status"] = "failed"
        report["blockers"] = sorted(set(report.get("blockers", []) + [code]))
        report.pop("report_digest", None)
        report["report_digest"] = stable_hash(report)
        return report

    @staticmethod
    def _reconcile_target_completion(report: dict[str, Any], plan: Any) -> dict[str, Any]:
        family_reasons = {
            reason for family in plan.families.values() for reason in family.reason_codes
        }
        runtime_blockers = set(report.get("blockers", [])) - family_reasons
        blockers = sorted(runtime_blockers | set(unresolved_reason_codes(plan.families)))
        reconciled = dict(report)
        reconciled["blockers"] = blockers
        if reconciled["status"] != "failed":
            reconciled["status"] = (
                "partial" if blockers or has_unresolved_families(plan.families) else "complete"
            )
        reconciled.pop("report_digest", None)
        reconciled["report_digest"] = stable_hash(reconciled)
        return reconciled

    @staticmethod
    def _merge_object_result(
        report: dict[str, Any], result: ObjectOperationResult | None
    ) -> dict[str, Any]:
        if result is None:
            return report
        merged = dict(report)
        merged["object_counts"] = dict(sorted(result.counts.items()))
        merged["blockers"] = sorted(set(merged.get("blockers", []) + list(result.blockers)))
        merged["object_reasons"] = sorted(
            set(merged.get("object_reasons", []) + list(result.reasons))
        )
        if result.status == "failed":
            merged["status"] = "failed"
        elif result.status == "partial" and merged["status"] == "complete":
            merged["status"] = "partial"
        merged.pop("report_digest", None)
        merged["report_digest"] = stable_hash(merged)
        return merged


def write_report(report: dict[str, Any], output: str | Path | None) -> None:
    if output is None:
        return
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
