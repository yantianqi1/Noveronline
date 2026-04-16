"""Background task runtime tables."""

from __future__ import annotations

from .helpers import int_col, table, text_col

task_runs = table("task_runs", text_col("task_id", primary_key=True), text_col("task_type", nullable=False), text_col("status", nullable=False), text_col("created_at", nullable=False), text_col("updated_at", nullable=False), int_col("progress", nullable=False), text_col("message", nullable=False), text_col("result_json"), text_col("error"), text_col("metadata_json", nullable=False), text_col("progress_detail_json", nullable=False))
