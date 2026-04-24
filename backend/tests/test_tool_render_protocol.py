"""W-2 D5 tests: execute_tool render protocol + agent_loop tool_result event.

Covers:
- Legacy str-returning executors are transparently wrapped into {result}
- New dict-returning executors have both result and render round-tripped
- Unknown tool name yields a {result} error dict
- _get_chapter_word_stats emits a WordBudgetRender when target is provided
- agent_loop tool_result event includes the render field (via mock)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ----------------------------------------------------------------------
# execute_tool wrapper behaviour
# ----------------------------------------------------------------------


def test_execute_tool_wraps_legacy_str_return(monkeypatch):
    from app.services.writer_agent import tool_executors as te

    def fake_executor(params, project_id):
        return "hello world"

    monkeypatch.setitem(te._EXECUTORS, "__test_legacy__", fake_executor)
    out = te.execute_tool("__test_legacy__", {}, "proj")
    assert out == {"result": "hello world"}


def test_execute_tool_passes_through_dict_with_render(monkeypatch):
    from app.services.writer_agent import tool_executors as te

    def fake_executor(params, project_id):
        return {
            "result": "fine",
            "render": {"version": 1, "type": "word_budget", "data": {"x": 1}, "actions": []},
        }

    monkeypatch.setitem(te._EXECUTORS, "__test_dict__", fake_executor)
    out = te.execute_tool("__test_dict__", {}, "proj")
    assert out["result"] == "fine"
    assert out["render"]["type"] == "word_budget"
    assert out["render"]["data"] == {"x": 1}


def test_execute_tool_truncates_only_result_not_render(monkeypatch):
    from app.services.writer_agent import tool_executors as te

    big_text = "x" * (te.TOOL_RESULT_MAX_CHARS + 1000)
    big_render_payload = {
        "version": 1,
        "type": "word_budget",
        "data": {"big": "y" * 20000},
        "actions": [],
    }

    def fake_executor(params, project_id):
        return {"result": big_text, "render": big_render_payload}

    monkeypatch.setitem(te._EXECUTORS, "__test_trunc__", fake_executor)
    out = te.execute_tool("__test_trunc__", {}, "proj")
    assert len(out["result"]) <= te.TOOL_RESULT_MAX_CHARS
    # render is not truncated — UI needs full structure
    assert out["render"]["data"] == big_render_payload["data"]


def test_execute_tool_unknown_name(monkeypatch):
    from app.services.writer_agent import tool_executors as te

    out = te.execute_tool("__nonexistent__", {}, "proj")
    assert "未知工具" in out["result"]
    assert "render" not in out


def test_execute_tool_swallows_exception():
    from app.services.writer_agent import tool_executors as te

    def boom(params, project_id):
        raise RuntimeError("boom")

    te._EXECUTORS["__test_boom__"] = boom
    try:
        out = te.execute_tool("__test_boom__", {}, "proj")
        assert "render" not in out
        assert "执行出错" in out["result"] or "执行失败" in out["result"]
    finally:
        del te._EXECUTORS["__test_boom__"]


# ----------------------------------------------------------------------
# _get_chapter_word_stats render emission
# ----------------------------------------------------------------------


def test_get_chapter_word_stats_emits_render_when_target_set(monkeypatch):
    """Verify WordBudgetRender is attached + status is 'over' when total > target * 1.1."""
    from app.services.writer_agent import tool_executors as te

    fake_blocks = [
        {"block_id": "b1", "block_order": 1, "content": "a" * 1500},
        {"block_id": "b2", "block_order": 2, "content": "b" * 2000},
    ]

    fake_adapter = MagicMock()
    fake_adapter.list_blocks.return_value = fake_blocks

    monkeypatch.setattr(te, "_get_manuscript_adapter", lambda pid: fake_adapter)

    # Mock ChapterRepository lookup so we don't need a real DB row
    with patch.object(te, "ChapterRepository") as chap_cls:
        chap_cls.return_value.get_chapter.return_value = {
            "chapter_order": 5,
            "title": "试章",
        }
        out = te._get_chapter_word_stats(
            {"chapter_id": "ch_x", "target_word_count": 3000}, "proj"
        )

    assert "render" in out and out["render"] is not None
    render = out["render"]
    assert render["type"] == "word_budget"
    data = render["data"]
    assert data["chapter_id"] == "ch_x"
    assert data["chapter_order"] == 5
    assert data["target"] == 3000
    assert data["total"] == 3500
    assert data["diff"] == 500
    assert data["status"] == "over"  # 500/3000 = 16.7% > 10% tolerance
    assert len(data["blocks"]) == 2
    assert data["blocks"][0]["block_id"] == "b1"


def test_get_chapter_word_stats_on_target_status(monkeypatch):
    """Within tolerance → status='on_target'."""
    from app.services.writer_agent import tool_executors as te

    fake_adapter = MagicMock()
    fake_adapter.list_blocks.return_value = [
        {"block_id": "b1", "block_order": 1, "content": "a" * 2950},
    ]
    monkeypatch.setattr(te, "_get_manuscript_adapter", lambda pid: fake_adapter)

    with patch.object(te, "ChapterRepository") as chap_cls:
        chap_cls.return_value.get_chapter.return_value = {"chapter_order": 1, "title": ""}
        out = te._get_chapter_word_stats(
            {"chapter_id": "ch_y", "target_word_count": 3000}, "proj"
        )

    # 2950 vs target 3000 → -50 (-1.7%) within 10% tolerance
    assert out["render"]["data"]["status"] == "on_target"


def test_get_chapter_word_stats_no_target_returns_no_render(monkeypatch):
    from app.services.writer_agent import tool_executors as te

    fake_adapter = MagicMock()
    fake_adapter.list_blocks.return_value = [
        {"block_id": "b1", "block_order": 1, "content": "a" * 500},
    ]
    monkeypatch.setattr(te, "_get_manuscript_adapter", lambda pid: fake_adapter)

    out = te._get_chapter_word_stats({"chapter_id": "ch_z"}, "proj")
    # No target → no budget → no card
    assert out.get("render") is None


# ----------------------------------------------------------------------
# agent_loop tool_result event shape
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_loop_tool_result_includes_render():
    """End-to-end: an LLM response with one tool_call → tool_result event
    carries the render field emitted by the tool executor."""
    from app.services.writer_agent import tool_executors as te
    from app.services.writer_agent.agent_loop import AgentLoop

    # Fake executor that emits a render payload
    def fake_render_tool(params, project_id):
        return {
            "result": "scanned 42 matches",
            "render": {
                "version": 1,
                "type": "word_budget",
                "data": {
                    "chapter_id": "ch1",
                    "chapter_order": 1,
                    "target": 3000,
                    "total": 2800,
                    "diff": -200,
                    "blocks": [],
                    "status": "under",
                },
                "actions": [],
            },
        }

    te._EXECUTORS["__test_render_tool__"] = fake_render_tool

    # Minimal fake LLM client: one round with a single tool_call, then nothing.
    class _ToolCallObj:
        def __init__(self, name, args):
            self.id = "call_1"
            self.function = MagicMock(name=name, arguments=args)
            self.function.name = name
            self.function.arguments = args

    call_sequence = iter([
        MagicMock(content="", tool_calls=[_ToolCallObj("__test_render_tool__", "{}")], _usage=None),
        MagicMock(content="done", tool_calls=[], _usage=None),
    ])

    class _FakeClient:
        async def chat_with_tools(self, **kwargs):
            return next(call_sequence)

    loop = AgentLoop(
        llm_client=_FakeClient(),
        tools=[],
        system_prompt="you are test",
        project_id="proj",
    )

    events = []
    try:
        async for ev in loop.run("please run the tool"):
            events.append(ev)
    finally:
        del te._EXECUTORS["__test_render_tool__"]

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    tr = tool_results[0]
    assert tr["name"] == "__test_render_tool__"
    assert tr["status"] == "ok"
    assert tr["full_result"] == "scanned 42 matches"
    assert tr["render"] is not None
    assert tr["render"]["type"] == "word_budget"
    assert tr["render"]["data"]["status"] == "under"


@pytest.mark.asyncio
async def test_agent_loop_tool_result_render_none_for_legacy_str():
    """Legacy str-returning tools → tool_result.render == None (back-compat)."""
    from app.services.writer_agent import tool_executors as te
    from app.services.writer_agent.agent_loop import AgentLoop

    def fake_legacy_tool(params, project_id):
        return "plain text only"

    te._EXECUTORS["__test_legacy_tool__"] = fake_legacy_tool

    class _ToolCallObj:
        def __init__(self, name, args):
            self.id = "call_1"
            self.function = MagicMock(name=name, arguments=args)
            self.function.name = name
            self.function.arguments = args

    call_sequence = iter([
        MagicMock(content="", tool_calls=[_ToolCallObj("__test_legacy_tool__", "{}")], _usage=None),
        MagicMock(content="done", tool_calls=[], _usage=None),
    ])

    class _FakeClient:
        async def chat_with_tools(self, **kwargs):
            return next(call_sequence)

    loop = AgentLoop(
        llm_client=_FakeClient(),
        tools=[],
        system_prompt="you are test",
        project_id="proj",
    )

    events = []
    try:
        async for ev in loop.run("please run"):
            events.append(ev)
    finally:
        del te._EXECUTORS["__test_legacy_tool__"]

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["render"] is None
