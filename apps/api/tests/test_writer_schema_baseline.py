import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shared.db.base import metadata


def test_writer_tables_are_registered():
    expected_tables = {
        "chapters",
        "chapter_history_items",
        "draft_runs",
        "draft_run_steps",
        "draft_revisions",
        "draft_reviews",
        "finalized_chapters",
    }

    assert expected_tables.issubset(set(metadata.tables))


def test_writer_key_columns_exist():
    chapters = metadata.tables["chapters"]
    chapter_history_items = metadata.tables["chapter_history_items"]
    draft_runs = metadata.tables["draft_runs"]
    draft_revisions = metadata.tables["draft_revisions"]
    draft_reviews = metadata.tables["draft_reviews"]
    finalized_chapters = metadata.tables["finalized_chapters"]

    assert {"chapter_id", "project_id", "chapter_order", "title", "summary_text"}.issubset(chapters.columns.keys())
    assert {"chapter_history_item_id", "project_id", "chapter_id", "item_type", "summary_text"}.issubset(
        chapter_history_items.columns.keys()
    )
    assert {"draft_run_id", "project_id", "session_id", "chapter_order", "chapter_id", "status"}.issubset(
        draft_runs.columns.keys()
    )
    assert {"draft_revision_id", "draft_run_id", "revision_no", "body_artifact_id"}.issubset(
        draft_revisions.columns.keys()
    )
    assert {"draft_review_id", "draft_run_id", "revision_no", "passed", "score"}.issubset(
        draft_reviews.columns.keys()
    )
    assert {"finalized_chapter_id", "project_id", "chapter_order", "chapter_id", "body_artifact_id"}.issubset(
        finalized_chapters.columns.keys()
    )
