#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from mirofish_agents.legacy_import.service import LegacyImportService, write_report
from mirofish_agents.legacy_import.objects import object_lifecycle_from_env
from mirofish_agents.legacy_import.source import LegacySource


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Inspect and explicitly import a legacy MiroFish project")
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--source", required=True)
    inspect.add_argument("--artifact-root")
    inspect.add_argument("--report-output")
    for name in ("plan", "apply", "verify", "rollback", "reconcile-version"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--artifact-root")
        command.add_argument("--import-id", required=True)
        command.add_argument("--tenant-id", required=True)
        command.add_argument("--project-id", required=True)
        command.add_argument("--actor-user-id", required=True)
        command.add_argument("--source-project-id", required=True)
        command.add_argument("--report-output")
        if name in {"apply", "verify", "rollback", "reconcile-version"}:
            command.add_argument("--target", required=True, help="PostgreSQL app-role DSN")
        if name in {"apply", "verify", "rollback", "reconcile-version"}:
            command.add_argument("--expected-source-fingerprint", required=True)
            command.add_argument("--expected-plan-hash", required=True)
        if name in {"apply", "rollback", "reconcile-version"}:
            command.add_argument("--execute", action="store_true", help="authorize target writes")
        if name == "reconcile-version":
            command.add_argument("--object-id", required=True)
            command.add_argument("--version-id", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "inspect":
        inspection = LegacySource(args.source, args.artifact_root).inspect()
        from mirofish_agents.legacy_import.models import stable_hash

        report: dict[str, Any] = {
            "schema_version": 1,
            "operation": "inspect",
            "status": "complete",
            **inspection.public_dict(),
            "duration_ms": 0,
        }
        report["report_digest"] = stable_hash(report)
    else:
        target_dsn = getattr(args, "target", None)
        service = LegacyImportService(
            source_path=args.source,
            artifact_root=args.artifact_root,
            import_id=args.import_id,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            actor_user_id=args.actor_user_id,
            source_project_id=args.source_project_id,
            target_dsn=target_dsn,
            object_lifecycle=(
                object_lifecycle_from_env(target_dsn)
                if target_dsn is not None
                and args.command in {"apply", "verify", "rollback", "reconcile-version"}
                else None
            ),
        )
        if args.command == "plan":
            report = service.plan_report()
        elif args.command == "apply":
            report = service.apply(
                execute=args.execute,
                expected_source_fingerprint=args.expected_source_fingerprint,
                expected_plan_hash=args.expected_plan_hash,
            )
        elif args.command == "verify":
            report = service.verify(
                expected_source_fingerprint=args.expected_source_fingerprint,
                expected_plan_hash=args.expected_plan_hash,
            )
        elif args.command == "rollback":
            report = service.rollback(
                execute=args.execute,
                expected_source_fingerprint=args.expected_source_fingerprint,
                expected_plan_hash=args.expected_plan_hash,
            )
        else:
            report = service.reconcile_object_version(
                object_id=args.object_id,
                version_id=args.version_id,
                execute=args.execute,
                expected_source_fingerprint=args.expected_source_fingerprint,
                expected_plan_hash=args.expected_plan_hash,
            )
    write_report(report, getattr(args, "report_output", None))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
