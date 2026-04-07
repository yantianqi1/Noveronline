"""Phase 2 tests: writer-agent asset library tool executors."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def env(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    (upload_root / "system").mkdir(parents=True)
    (upload_root / "projects" / "proj_demo").mkdir(parents=True)

    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))

    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    a = svc.create(
        scope="global", asset_type="writing_style",
        title="冷峻第一人称样本",
        category="叙事视角",
        summary="冷静克制的第一人称",
        content="句式短促 动词为主 避免形容词堆叠 大量留白",
        payload={"pov": "first", "tone": "cold"},
    )
    disabled = svc.create(
        scope="global", asset_type="writing_style",
        title="禁用的暖色风格",
        content="温暖明亮 大量形容词 抒情段落",
        enabled=False,
    )
    project_asset = svc.create(
        scope="project", project_id="proj_demo",
        asset_type="worldview", title="本项目世界观",
        content="霓虹雨夜 神经接口 巨型企业",
    )
    return {"asset_id": a["asset_id"], "disabled_id": disabled["asset_id"]}


def test_search_assets_executor(env):
    from app.services.writer_agent.tool_executors import execute_tool
    out = execute_tool(
        "search_assets",
        {"query": "形容词堆叠", "asset_type": "writing_style"},
        "proj_demo",
    )
    assert "冷峻第一人称样本" in out
    assert "禁用的暖色风格" not in out  # disabled excluded


def test_get_asset_executor_returns_payload(env):
    from app.services.writer_agent.tool_executors import execute_tool
    out = execute_tool("get_asset", {"asset_id": env["asset_id"]}, "proj_demo")
    assert "冷峻第一人称样本" in out
    assert "结构化数据" in out
    assert '"pov"' in out


def test_get_asset_blocks_disabled(env):
    from app.services.writer_agent.tool_executors import execute_tool
    out = execute_tool("get_asset", {"asset_id": env["disabled_id"]}, "proj_demo")
    assert "禁用状态" in out


def test_list_assets_executor(env):
    from app.services.writer_agent.tool_executors import execute_tool
    out = execute_tool(
        "list_assets", {"asset_type": "worldview"}, "proj_demo",
    )
    assert "本项目世界观" in out


def test_tools_registered():
    from app.services.writer_agent.tools import ASSET_TOOL_NAME_SET
    assert {"search_assets", "get_asset", "list_assets"} <= ASSET_TOOL_NAME_SET
