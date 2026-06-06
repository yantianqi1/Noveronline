import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_task_runtime_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table task_runs (
          task_id text primary key,
          task_type text not null,
          status text not null,
          created_at text not null,
          updated_at text not null,
          progress integer not null,
          message text,
          result_json text,
          metadata_json text not null,
          progress_detail_json text not null,
          error text
        )
        """
    )
    connection.execute(
        """
        insert into task_runs (task_id, task_type, status, created_at, updated_at, progress, message, result_json, metadata_json, progress_detail_json, error)
        values (
          'task_1',
          'seed_extract',
          'completed',
          '2026-04-11T00:00:00',
          '2026-04-11T00:01:00',
          100,
          'done',
          '{"ok": true}',
          '{"project_id": "proj_demo"}',
          '{"active_stage":"segment_chapters","timeline":[{"id":"evt_1","timestamp":"2026-04-11T00:00:00","stage":"extract_text","status":"completed","title":"提取完成","detail":"读取文本"},{"id":"evt_2","timestamp":"2026-04-11T00:01:00","stage":"segment_chapters","status":"completed","title":"切分完成","detail":"完成切分"}]}',
          null
        )
        """
    )
    connection.commit()
    connection.close()


def create_chapter_meta_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table chapter_meta (
          project_id text not null,
          chapter_order integer not null,
          chapter_id text not null,
          title text not null,
          summary_text text not null,
          timeline_note text,
          created_at text not null,
          updated_at text not null
        )
        """
    )
    connection.execute(
        """
        create table chapter_history_item (
          project_id text not null,
          chapter_order integer not null,
          chapter_id text not null,
          item_type text not null,
          subject_key text,
          summary_text text not null,
          created_at text not null,
          updated_at text not null
        )
        """
    )
    connection.execute(
        """
        insert into chapter_meta (project_id, chapter_order, chapter_id, title, summary_text, timeline_note, created_at, updated_at)
        values ('proj_demo', 1, 'chapter_0001', '第一章', '摘要', '夜间', '2026-04-11T00:00:00', '2026-04-11T00:00:00')
        """
    )
    connection.execute(
        """
        insert into chapter_history_item (project_id, chapter_order, chapter_id, item_type, subject_key, summary_text, created_at, updated_at)
        values ('proj_demo', 1, 'chapter_0001', 'event', 'subject_1', '历史项', '2026-04-11T00:00:00', '2026-04-11T00:00:00')
        """
    )
    connection.commit()
    connection.close()


def test_import_only_imports_task_runtime_and_chapter_meta(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"系统导入项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )
    create_task_runtime_db(uploads / "system" / "task_runtime.sqlite3")
    create_chapter_meta_db(uploads / "system" / "chapter_meta.sqlite3")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert "system/task_runtime.sqlite3 -> workflow_runs+workflow_steps" not in report.blocked_targets
    assert "system/chapter_meta.sqlite3 -> chapters+chapter_history_items" not in report.blocked_targets

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        workflow_runs = connection.execute(select(report.metadata.tables["workflow_runs"])).all()
        workflow_steps = connection.execute(select(report.metadata.tables["workflow_steps"])).all()
        workflow_events = connection.execute(select(report.metadata.tables["workflow_events"])).all()
        chapters = connection.execute(select(report.metadata.tables["chapters"])).all()
        history_items = connection.execute(select(report.metadata.tables["chapter_history_items"])).all()

    assert len(workflow_runs) == 1
    assert workflow_runs[0].legacy_task_id == "task_1"
    assert workflow_runs[0].project_id == "proj_demo"
    assert len(workflow_steps) == 2
    assert {row.stage for row in workflow_steps} == {"extract_text", "segment_chapters"}
    assert len(workflow_events) == 2
    assert workflow_events[0].event_type == "operation.started"
    assert len(chapters) == 1
    assert chapters[0].chapter_id == "chapter_0001"
    assert len(history_items) == 1
