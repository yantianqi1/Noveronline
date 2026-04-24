"""Tests for `_query_worldline_session` against the unified DB.

Was file-based (reading ``uploads/projects/{pid}/worldlines/sessions/*.json``)
until Task 1 of the 2026-04-19 writer-agent optimization. This suite locks in
the DB-backed contract so the tool can't silently regress to disk reads.
"""

from __future__ import annotations

from app.database import get_engine
from app.repositories.worldline_session_repo import WorldlineSessionRepository
from app.services.writer_agent.tool_executors import _query_worldline_session


def _session_payload(
    session_id: str,
    *,
    project_id: str,
    label: str = "推演会话",
    simulation_goal: str = "看看主角会不会投靠敌方",
    focus_question: str = "主角面临选择时会怎么做？",
    status: str = "running",
    branches: list[dict] | None = None,
    world_variables: list[dict] | None = None,
    updated_at: str = "2026-04-18T12:00:00",
) -> dict:
    return {
        "session_id": session_id,
        "project_id": project_id,
        "graph_id": "graph_1",
        "label": label,
        "simulation_goal": simulation_goal,
        "focus_question": focus_question,
        "branch_count": len(branches) if branches else 0,
        "prepare_id": "prep_1",
        "session_scope": "project",
        "status": status,
        "branches": branches or [],
        "world_variables": world_variables or [],
        "timeline_focus": [],
        "agent_behavior_axes": [],
        "source_summary": {},
        "source_archive_ids": [],
        "source_project_ids": [project_id],
        "source_archive_count": 0,
        "created_at": "2026-04-18T00:00:00",
        "updated_at": updated_at,
    }


def _branch(
    branch_id: str,
    *,
    title: str,
    core_change: str = "",
    key_agents: list[str] | None = None,
    timeline: list[dict] | None = None,
    actor_states: dict | None = None,
    status: str = "running",
    current_step: int = 0,
) -> dict:
    return {
        "branch_id": branch_id,
        "title": title,
        "core_change": core_change,
        "narrative_value": "",
        "current_step": current_step,
        "status": status,
        "key_agents": key_agents or [],
        "expected_conflicts": [],
        "evolution_intensity": "medium",
        "evolution_depth": 3,
        "actor_states": actor_states or {},
        "organization_states": {},
        "relationship_states": [],
        "timeline": timeline or [],
        "pending_variables": [],
        "pending_actions": [],
        "created_at": "2026-04-18T00:00:00",
        "updated_at": "2026-04-18T00:00:00",
    }


def _event(step: int, title: str, summary: str) -> dict:
    return {
        "event_id": f"ev_{step}",
        "step": step,
        "title": title,
        "summary": summary,
        "event_type": "evolution",
        "driving_entities": [],
        "variable_effects": [],
        "action_effects": [],
        "relation_changes": [],
        "state_changes": [],
        "status": "canon",
        "confidence": "high",
        "confidence_reason": "",
        "event_source": "archive_based",
        "created_at": "2026-04-18T00:00:00",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_project_returns_no_sessions_notice():
    result = _query_worldline_session({}, project_id="proj_empty")
    assert "暂无世界线推演记录" in result


def test_missing_session_id_returns_not_found():
    WorldlineSessionRepository(get_engine())  # engine bootstrapped
    result = _query_worldline_session({"session_id": "does_not_exist"}, project_id="proj_x")
    assert "未找到 session" in result


def test_renders_title_description_variables_branches_events():
    repo = WorldlineSessionRepository(get_engine())
    repo.save_session(
        _session_payload(
            "sess_demo",
            project_id="proj_demo",
            label="核心推演",
            simulation_goal="推演主角反叛",
            focus_question="朋友会背叛主角吗？",
            world_variables=[
                {"variable_id": "v1", "name": "紧张度", "description": "高压", "impact_axis": "情绪"},
            ],
            branches=[
                _branch(
                    "br_main",
                    title="主线",
                    core_change="主角下定决心",
                    key_agents=["chen_ji"],
                    current_step=3,
                    actor_states={"chen_ji": {"mood": "冷静"}, "li_hua": {"mood": "犹豫"}},
                    timeline=[
                        _event(1, "开场", "主角收到书信"),
                        _event(2, "转折", "朋友表态"),
                        _event(3, "抉择", "主角决定反叛"),
                    ],
                ),
                _branch(
                    "br_alt",
                    title="备选",
                    core_change="朋友归顺",
                    key_agents=["li_hua"],
                    current_step=1,
                    timeline=[_event(1, "试探", "朋友主动靠拢")],
                ),
            ],
        )
    )

    result = _query_worldline_session({}, project_id="proj_demo")

    assert "sess_demo" in result
    assert "核心推演" in result  # label
    assert "推演主角反叛" in result  # simulation_goal
    assert "朋友会背叛主角吗？" in result  # focus_question
    assert "紧张度" in result  # variable name
    assert "分支（共 2）" in result
    assert "br_main" in result and "br_alt" in result
    # Agents merged across branches
    assert "chen_ji" in result and "li_hua" in result
    # Events flattened and newest-first
    assert "抉择" in result
    idx_choice = result.index("抉择")
    idx_open = result.index("开场")
    assert idx_choice < idx_open, "events should be sorted step DESC"


def test_cross_project_guard_rejects_foreign_session():
    repo = WorldlineSessionRepository(get_engine())
    repo.save_session(
        _session_payload("sess_foreign", project_id="proj_other", branches=[])
    )

    result = _query_worldline_session(
        {"session_id": "sess_foreign"}, project_id="proj_current"
    )
    assert "不属于当前项目" in result


def test_picks_most_recent_session_when_session_id_omitted():
    repo = WorldlineSessionRepository(get_engine())
    # Older session first
    repo.save_session(
        _session_payload(
            "sess_older",
            project_id="proj_multi",
            label="旧会话",
            branches=[_branch("b1", title="旧分支")],
        )
    )
    # Newer session — save_session stamps updated_at to now, so this becomes "most recent"
    repo.save_session(
        _session_payload(
            "sess_newer",
            project_id="proj_multi",
            label="新会话",
            branches=[_branch("b2", title="新分支")],
        )
    )

    result = _query_worldline_session({}, project_id="proj_multi")
    # Header line includes the chosen session id
    assert "sess_newer" in result
    assert "新会话" in result
    # The older one should not be the headline session
    assert "sess_older" not in result.splitlines()[0]


def test_session_without_branches_renders_minimally_without_errors():
    repo = WorldlineSessionRepository(get_engine())
    repo.save_session(
        _session_payload("sess_bare", project_id="proj_bare", branches=[])
    )

    result = _query_worldline_session({"session_id": "sess_bare"}, project_id="proj_bare")
    # Should have title / description / status but no branch or events sections
    assert "sess_bare" in result
    assert "分支" not in result
    assert "最近事件" not in result
