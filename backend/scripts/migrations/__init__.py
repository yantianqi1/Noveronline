"""Multi-domain legacy-to-unified migration framework.

Each concrete ``BaseDomainMigrator`` subclass migrates one legacy silo
(SQLite silo or per-project JSON blob) into the unified database. The
orchestrator in ``scripts.migrate_legacy_data`` walks projects and runs
every registered migrator against them.
"""

from __future__ import annotations

from .base import (
    BaseDomainMigrator,
    MigrationContext,
    copy_sqlite_into_unified,
)
from .migrate_archive import ArchiveLibraryDomainMigrator
from .migrate_assets import (
    GlobalAssetsDomainMigrator,
    ProjectAssetsDomainMigrator,
)
from .migrate_graph import GraphDomainMigrator
from .migrate_llm_facility import LlmFacilityDomainMigrator
from .migrate_novel import NovelDomainMigrator
from .migrate_seed_json import SeedJsonDomainMigrator
from .migrate_worldline import WorldlineRuntimeDomainMigrator

ALL_MIGRATORS: list[BaseDomainMigrator] = [
    NovelDomainMigrator(),
    GraphDomainMigrator(),
    ProjectAssetsDomainMigrator(),
    WorldlineRuntimeDomainMigrator(),
    SeedJsonDomainMigrator(),
    LlmFacilityDomainMigrator(),
    ArchiveLibraryDomainMigrator(),
    GlobalAssetsDomainMigrator(),
]

__all__ = [
    "ALL_MIGRATORS",
    "ArchiveLibraryDomainMigrator",
    "BaseDomainMigrator",
    "GlobalAssetsDomainMigrator",
    "GraphDomainMigrator",
    "LlmFacilityDomainMigrator",
    "MigrationContext",
    "NovelDomainMigrator",
    "ProjectAssetsDomainMigrator",
    "SeedJsonDomainMigrator",
    "WorldlineRuntimeDomainMigrator",
    "copy_sqlite_into_unified",
]
