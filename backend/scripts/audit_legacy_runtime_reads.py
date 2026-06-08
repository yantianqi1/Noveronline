"""Guard runtime code against new legacy source reads.

The migration plan still has a few documented compatibility and migration
paths, but new runtime code should not add fresh JSON/SQLite source-of-truth
reads. This scanner is intentionally conservative and path allowlisted: any
new file that introduces a marker must be reviewed explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO

FORBIDDEN_MARKERS = (
    "ProjectManager.load_project_json(",
    "ProjectManager.save_project_json(",
    "ReadingNotesManager.load(",
    "sqlite_master",
    "sqlite3.connect(",
    "project.json",
    "extracted_text.txt",
    "novel.sqlite3",
    "story_graph.sqlite3",
    "archive_library.sqlite3",
    "assets_library.sqlite3",
    "project_assets.sqlite3",
    "llm_facility.sqlite3",
    "task_runtime.sqlite3",
    "worldlines/runtime.sqlite3",
    "global_search.sqlite3",
)

DEFAULT_ALLOWED_PATHS = {
    "backend/app/services/migration_verifier.py",
}


def audit_legacy_runtime_reads(
    repo_root: str | Path,
    *,
    allowed_paths: set[str] | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    allowed = DEFAULT_ALLOWED_PATHS if allowed_paths is None else allowed_paths
    app_root = root / "backend" / "app"

    violations: list[dict[str, object]] = []
    scanned_files = 0
    for path in sorted(app_root.rglob("*.py")):
        scanned_files += 1
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for marker in FORBIDDEN_MARKERS:
                if marker in line:
                    violations.append(
                        {
                            "path": relative,
                            "line": line_number,
                            "marker": marker,
                            "allowed": relative in allowed,
                        }
                    )

    return {
        "allowed_paths": sorted(allowed),
        "scanned_files": scanned_files,
        "violations": violations,
        "unauthorized_violations": [
            violation for violation in violations if not violation["allowed"]
        ],
    }


def main(argv: list[str] | None = None, *, stdout: IO[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    report = audit_legacy_runtime_reads(repo_root)
    output = stdout or sys.stdout
    json.dump(report, output, ensure_ascii=False, sort_keys=True)
    output.write("\n")
    return 1 if report["unauthorized_violations"] else 0


def _default_repo_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "backend" / "app").exists():
        return cwd
    if cwd.name == "backend" and (cwd / "app").exists():
        return cwd.parent
    return cwd


if __name__ == "__main__":
    raise SystemExit(main())
