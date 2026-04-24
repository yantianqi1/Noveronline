"""W-1 D1 tests: BookPlanService.get_plan_status + ChapterService sync hooks.

Covers:
- get_plan_status aggregates chapter word counts + derived fields
- get_active_plan returns most recently updated active plan (status filter)
- ChapterService.create_chapter appends chapter_id to active plan
- ChapterService.delete_chapter removes chapter_id from all plans
- _skip_plan_sync kwarg bypasses the hook
- Multiple plans: remove_chapter_id cleans up all of them
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def service_env(tmp_path):
    """Fresh per-test DB + ChapterService + BookPlanService.

    Relies on conftest._test_paths to point DATABASE_URL at a fresh tmp file
    and _unified_db_bootstrap to reset db_mod._engine between tests.
    """
    from app.database import get_engine, init_db

    engine = get_engine()
    init_db(engine)

    from app.services.writer_agent.book_plan_service import BookPlanService
    from app.services.writer_agent.chapter_service import ChapterService

    return {
        "engine": engine,
        "chapter_service": ChapterService(),
        "plan_service": BookPlanService(),
        "project_id": "proj_w1",
    }


# ----------------------------------------------------------------------
# get_active_plan
# ----------------------------------------------------------------------


def test_get_active_plan_returns_none_when_no_plans(service_env):
    plan = service_env["plan_service"].get_active_plan(service_env["project_id"])
    assert plan is None


def test_get_active_plan_skips_completed(service_env):
    svc = service_env["plan_service"]
    pid = service_env["project_id"]

    p1 = svc.create_plan(pid, title="完结的", chapter_count=3, per_chapter_word_target=3000)
    svc.set_status(p1["plan_id"], "completed")

    assert svc.get_active_plan(pid) is None


def test_get_active_plan_picks_most_recent(service_env):
    svc = service_env["plan_service"]
    pid = service_env["project_id"]

    p1 = svc.create_plan(pid, title="旧计划", chapter_count=3, per_chapter_word_target=3000)
    p2 = svc.create_plan(pid, title="新计划", chapter_count=3, per_chapter_word_target=3000)
    # Both default to status=draft → both active; get_active_plan picks the newest by updated_at
    active = svc.get_active_plan(pid)
    assert active is not None
    assert active["plan_id"] in {p1["plan_id"], p2["plan_id"]}
    # The newer plan should win (created after → updated_at newer)
    assert active["plan_id"] == p2["plan_id"]


# ----------------------------------------------------------------------
# ChapterService sync hook: create_chapter
# ----------------------------------------------------------------------


def test_create_chapter_appends_to_active_plan(service_env):
    plan_svc = service_env["plan_service"]
    chap_svc = service_env["chapter_service"]
    pid = service_env["project_id"]

    plan = plan_svc.create_plan(pid, title="计划", chapter_count=3, per_chapter_word_target=3000)
    result = chap_svc.create_chapter(pid, title="第一章")

    refreshed = plan_svc.get_plan(plan["plan_id"])
    assert result["chapter_id"] in refreshed["chapter_ids"]


def test_create_chapter_no_active_plan_is_silent(service_env):
    chap_svc = service_env["chapter_service"]
    pid = service_env["project_id"]
    # No plan exists → create_chapter must still succeed
    out = chap_svc.create_chapter(pid, title="孤章")
    assert out["chapter_id"].startswith("ch_")


def test_create_chapter_skip_plan_sync(service_env):
    plan_svc = service_env["plan_service"]
    chap_svc = service_env["chapter_service"]
    pid = service_env["project_id"]

    plan = plan_svc.create_plan(pid, title="计划", chapter_count=3, per_chapter_word_target=3000)
    result = chap_svc.create_chapter(pid, title="章", _skip_plan_sync=True)

    refreshed = plan_svc.get_plan(plan["plan_id"])
    assert result["chapter_id"] not in refreshed["chapter_ids"]


# ----------------------------------------------------------------------
# ChapterService sync hook: delete_chapter
# ----------------------------------------------------------------------


def test_delete_chapter_removes_from_all_plans(service_env):
    plan_svc = service_env["plan_service"]
    chap_svc = service_env["chapter_service"]
    pid = service_env["project_id"]

    p1 = plan_svc.create_plan(pid, title="A", chapter_count=3, per_chapter_word_target=3000)
    p2 = plan_svc.create_plan(pid, title="B", chapter_count=3, per_chapter_word_target=3000)

    # create_chapter appends to active plan (most recent = p2). Manually also add to p1.
    result = chap_svc.create_chapter(pid, title="共享章")
    plan_svc.append_chapter_id(p1["plan_id"], result["chapter_id"])

    chap_svc.delete_chapter(pid, result["chapter_id"])

    assert result["chapter_id"] not in plan_svc.get_plan(p1["plan_id"])["chapter_ids"]
    assert result["chapter_id"] not in plan_svc.get_plan(p2["plan_id"])["chapter_ids"]


def test_remove_chapter_id_noop_when_absent(service_env):
    plan_svc = service_env["plan_service"]
    pid = service_env["project_id"]

    plan = plan_svc.create_plan(pid, title="空", chapter_count=3, per_chapter_word_target=3000)
    # No chapter added — remove should be silently idempotent
    plan_svc.remove_chapter_id(plan["plan_id"], "ch_nonexistent")

    refreshed = plan_svc.get_plan(plan["plan_id"])
    assert refreshed["chapter_ids"] == []


# ----------------------------------------------------------------------
# get_plan_status aggregate
# ----------------------------------------------------------------------


def test_get_plan_status_returns_none_for_missing(service_env):
    assert service_env["plan_service"].get_plan_status("bp_nope") is None


def test_get_plan_status_aggregates_fields(service_env):
    plan_svc = service_env["plan_service"]
    chap_svc = service_env["chapter_service"]
    pid = service_env["project_id"]

    plan = plan_svc.create_plan(
        pid, title="聚合测试", chapter_count=3, per_chapter_word_target=3000
    )
    c1 = chap_svc.create_chapter(pid, title="一")
    c2 = chap_svc.create_chapter(pid, title="二")
    # Update chapter content so word_count > 0
    chap_svc.update_chapter(pid, c1["chapter_id"], content="a" * 1500, word_count=1500)
    chap_svc.update_chapter(pid, c2["chapter_id"], content="b" * 500, word_count=500, status="completed")

    status = plan_svc.get_plan_status(plan["plan_id"])
    assert status is not None
    assert status["plan_id"] == plan["plan_id"]
    assert status["chapter_count"] == 3
    assert status["per_chapter_word_target"] == 3000
    assert status["total_word_target"] == 9000
    assert status["words_written_total"] == 2000
    assert status["progress_pct"] == pytest.approx(22.2, abs=0.1)
    assert status["completed_chapter_count"] == 1
    assert len(status["chapters"]) == 2
    assert status["chapters"][0]["chapter_order"] == 1
    assert status["chapters"][1]["word_count"] == 500


def test_get_plan_status_handles_missing_chapters(service_env):
    """chapter_ids can reference chapters that were hard-deleted outside the sync hook."""
    plan_svc = service_env["plan_service"]
    pid = service_env["project_id"]

    plan = plan_svc.create_plan(pid, title="残留", chapter_count=1, per_chapter_word_target=3000)
    plan_svc.append_chapter_id(plan["plan_id"], "ch_ghost")

    status = plan_svc.get_plan_status(plan["plan_id"])
    assert status["chapters"] == []
    assert status["words_written_total"] == 0
