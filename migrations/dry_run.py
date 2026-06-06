from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys

from migrations.checksums.manifest import build_checksum_manifest
from migrations.json_importers.asset_classification import classify_legacy_asset
from migrations.json_importers.legacy_inventory import scan_legacy_root


@dataclass(frozen=True)
class DryRunSummary:
    uploads_root: str
    project_count: int
    entry_count: int
    classification_counts: dict[str, int]
    zero_byte_assets: tuple[str, ...]
    anomalies: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def build_dry_run_summary(uploads_root: Path) -> DryRunSummary:
    inventory = scan_legacy_root(uploads_root)
    manifest = build_checksum_manifest(inventory)

    counts: Counter[str] = Counter()
    zero_byte_assets: list[str] = []
    for entry in manifest.entries:
        decision = classify_legacy_asset(entry.relative_path)
        counts[f"{decision.action}:{decision.target}"] += 1
        if entry.size_bytes == 0:
            zero_byte_assets.append(entry.relative_path)

    return DryRunSummary(
        uploads_root=uploads_root.as_posix(),
        project_count=inventory.project_count,
        entry_count=manifest.entry_count,
        classification_counts=dict(sorted(counts.items())),
        zero_byte_assets=tuple(sorted(zero_byte_assets)),
        anomalies=inventory.anomalies,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        raise SystemExit("usage: python -m migrations.dry_run <uploads_root>")
    summary = build_dry_run_summary(Path(args[0]))
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
