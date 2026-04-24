"""Canonical ``asset_type`` values for the unified assets table.

Consolidates strings that were previously hardcoded across
``manuscript_adapter``, ``style_extractor``, ``writer_agent`` tools,
``ingestion_agent``, and ``narrative_entity_service``. Application
code should import ``AssetType`` and reference members instead of
duplicating the raw strings.

Split into two disjoint sets:

- ``INGESTIBLE_TYPES`` — types an end user may submit via
  ``IngestionAgent``. Exposed in the ingestion prompt so the LLM
  picks from a finite list.
- ``SYSTEM_TYPES`` — types emitted by internal writers
  (manuscript committer, forbidden-lexicon collector,
  narrative-entity archivist). Never suggested to the LLM.

The ``assets.asset_type`` column remains a plain TEXT without a
CHECK constraint because:

  1. Tests exercise generic CRUD with ad-hoc types like ``style``,
     ``reference``, ``codex`` — enforcing a closed set at the DB
     layer would break them.
  2. New types should be addable by editing this module alone,
     without an alembic migration every time the product evolves.

Callers that need strict validation (e.g. ``IngestionAgent`` vetting
LLM output) check membership explicitly against ``INGESTIBLE_TYPES``.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class AssetType(str, Enum):
    WRITING_STYLE = "writing_style"
    AUTHOR_STYLE = "author_style"
    CHARACTER_ARCHETYPE = "character_archetype"
    WORLDVIEW = "worldview"
    WORLD_RULE = "world_rule"
    PLOT_TEMPLATE = "plot_template"
    PROMPT_TEMPLATE = "prompt_template"
    NOTE = "note"
    MANUSCRIPT_BLOCK = "manuscript_block"
    FORBIDDEN_LEXICON = "forbidden_lexicon"
    # P5 merge: entity archives (ex-``archive_library``) live as assets
    # with this asset_type. Archive-specific columns on the ``assets``
    # table (entity_name, core_drive, template_*, …) are populated only
    # for these rows.
    ARCHIVE_ENTITY = "archive_entity"


INGESTIBLE_TYPES: Final[tuple[str, ...]] = (
    AssetType.WRITING_STYLE.value,
    AssetType.WORLDVIEW.value,
    AssetType.CHARACTER_ARCHETYPE.value,
    AssetType.WORLD_RULE.value,
    AssetType.PLOT_TEMPLATE.value,
    AssetType.PROMPT_TEMPLATE.value,
    AssetType.NOTE.value,
)

SYSTEM_TYPES: Final[frozenset[str]] = frozenset(
    {
        AssetType.MANUSCRIPT_BLOCK.value,
        AssetType.FORBIDDEN_LEXICON.value,
        AssetType.AUTHOR_STYLE.value,
        AssetType.ARCHIVE_ENTITY.value,
    }
)
