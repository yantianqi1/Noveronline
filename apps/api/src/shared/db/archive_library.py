from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "entities",
    metadata,
    Column("entity_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("entity_uuid", String(128), nullable=True),
    Column("entity_kind", String(64), nullable=False),
    Column("canonical_name", String(255), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("summary", Text, nullable=False, default=""),
    *timestamp_columns(),
)

Table(
    "archives",
    metadata,
    Column("archive_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("entity_id", String(64), ForeignKey("entities.entity_id"), nullable=False),
    Column("archive_type", String(64), nullable=False),
    Column("agent_kind", String(64), nullable=False),
    Column("importance_tier", String(64), nullable=False),
    Column("selected_importance_tier", String(64), nullable=False),
    Column("template_key", String(128), nullable=False),
    Column("template_version", String(64), nullable=False),
    *timestamp_columns(),
)

Table(
    "memories",
    metadata,
    Column("memory_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("archive_id", String(64), ForeignKey("archives.archive_id"), nullable=False),
    Column("memory_type", String(64), nullable=False),
    Column("memory_layer", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("normalized_subject", String(255), nullable=False),
    Column("summary", Text, nullable=False),
    *timestamp_columns(),
)

Table(
    "memory_events",
    metadata,
    Column("memory_event_id", String(64), primary_key=True),
    Column("memory_id", String(64), ForeignKey("memories.memory_id"), nullable=False),
    Column("archive_id", String(64), ForeignKey("archives.archive_id"), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("actor_type", String(64), nullable=False),
    Column("actor_ref", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
