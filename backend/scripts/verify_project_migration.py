"""CLI for verifying one project's migration state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.config import Settings
from app.database import create_engine_from_settings, init_db
from app.services.migration_verifier import MigrationVerifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify legacy-to-unified migration state for one project.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--upload-root", default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--include-global",
        action="store_true",
        help="Also verify global legacy stores under <upload-root>/system/",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings(DATABASE_URL=args.database_url or Settings().DATABASE_URL)
    engine = create_engine_from_settings(settings)
    init_db(engine)

    upload_root = Path(args.upload_root or Settings().UPLOAD_FOLDER)
    verifier = MigrationVerifier(upload_root=upload_root, engine=engine)
    report = verifier.verify_project(args.project_id)
    if args.include_global:
        report["global"] = verifier.verify_global()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    verdicts = [report["overall_verdict"]]
    if args.include_global:
        verdicts.append(report["global"]["overall_verdict"])
    return 0 if "fail" not in verdicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
