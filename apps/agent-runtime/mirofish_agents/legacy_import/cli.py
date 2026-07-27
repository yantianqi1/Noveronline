"""Legacy-import CLI argument parser.

Originally lived in the standalone scripts/legacy_import.py entry point; that
script was retired but the parser contract is still the testable definition of
the legacy-import CLI flags (see tests/test_legacy_import.py). Kept here so
the test suite imports it without resurrecting a dead script directory.
"""
from __future__ import annotations

import argparse


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
