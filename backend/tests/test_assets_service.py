"""Phase 1 tests for the asset library service (storage + CRUD + FTS)."""

from __future__ import annotations

import os
import uuid

import pytest

from sqlalchemy import create_engine

from app.database import init_db
from app.repositories.asset_repo import AssetRepository
from app.services.assets.assets_service import (
    AssetsService,
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
)


@pytest.fixture()
def isolated_assets(monkeypatch, tmp_path):
    """Create an in-memory engine and wire AssetsService to it."""
    upload_root = tmp_path / "uploads"
    (upload_root / "system").mkdir(parents=True)
    (upload_root / "projects").mkdir(parents=True)

    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    repo = AssetRepository(engine)
    yield AssetsService(repo=repo)


def test_create_get_list_global(isolated_assets):
    svc = isolated_assets
    asset = svc.create(
        scope=GLOBAL_SCOPE,
        asset_type="writing_style",
        title="冷峻第一人称",
        category="叙事视角",
        summary="冷静克制的第一人称叙述",
        content="句式短促，动词为主，避免形容词堆叠……",
        payload={"sentence_length": "short", "pov": "first"},
        tags=["冷峻", "短句"],
    )
    assert asset["asset_id"].startswith("asset_")
    assert asset["scope"] == GLOBAL_SCOPE
    assert asset["enabled"] is True
    assert asset["payload"]["pov"] == "first"
    assert asset["tags"] == ["冷峻", "短句"]
    assert asset["word_count"] == len("句式短促，动词为主，避免形容词堆叠……")

    fetched = svc.get(asset["asset_id"], scope=GLOBAL_SCOPE)
    assert fetched is not None
    assert fetched["title"] == "冷峻第一人称"

    listed = svc.list(scope=GLOBAL_SCOPE, asset_type="writing_style")
    assert len(listed) == 1


def test_update_and_toggle(isolated_assets):
    svc = isolated_assets
    a = svc.create(
        scope=GLOBAL_SCOPE, asset_type="prompt_template", title="风格注入提示",
        content="原始内容",
    )
    aid = a["asset_id"]

    updated = svc.update(
        aid, scope=GLOBAL_SCOPE,
        content="新内容更长一些，用于校验 word_count 更新逻辑。",
        category="提示词",
        tags=["注入"],
    )
    assert updated["category"] == "提示词"
    assert updated["word_count"] == len("新内容更长一些，用于校验 word_count 更新逻辑。")
    assert updated["tags"] == ["注入"]

    n = svc.batch_set_enabled([aid], False, scope=GLOBAL_SCOPE)
    assert n == 1
    assert svc.get(aid, scope=GLOBAL_SCOPE)["enabled"] is False


def test_fts_search_and_enabled_filter(isolated_assets):
    svc = isolated_assets
    svc.create(
        scope=GLOBAL_SCOPE, asset_type="writing_style", title="武侠写意风",
        content="刀光剑影 江湖恩怨 大开大合 写意笔法",
    )
    disabled = svc.create(
        scope=GLOBAL_SCOPE, asset_type="writing_style", title="武侠工笔风",
        content="刀光剑影 工笔白描 极致细节",
        enabled=False,
    )

    hits = svc.search("刀光剑影", scope=GLOBAL_SCOPE, asset_type="writing_style")
    titles = {h["title"] for h in hits}
    assert "武侠写意风" in titles
    assert "武侠工笔风" not in titles  # disabled excluded by default

    hits_all = svc.search(
        "刀光剑影", scope=GLOBAL_SCOPE,
        asset_type="writing_style", enabled_only=False,
    )
    titles_all = {h["title"] for h in hits_all}
    assert "武侠工笔风" in titles_all


def test_project_scope_and_merged_search(isolated_assets):
    svc = isolated_assets
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    # ensure project dir exists like real ProjectManager would
    from app.models.project import ProjectManager
    os.makedirs(os.path.join(ProjectManager.PROJECTS_DIR, pid), exist_ok=True)

    svc.create(
        scope=GLOBAL_SCOPE, asset_type="worldview", title="赛博朋克通用世界观",
        content="霓虹 雨夜 巨型企业 神经接口",
    )
    svc.create(
        scope=PROJECT_SCOPE, project_id=pid, asset_type="worldview",
        title="本项目：雨夜东京2087",
        content="霓虹招牌 阴雨连绵 黑客地下网",
    )

    merged = svc.search_merged(
        "霓虹", project_id=pid, asset_type="worldview",
    )
    # project hit should be first
    assert merged[0]["scope"] == PROJECT_SCOPE
    assert merged[0]["title"] == "本项目：雨夜东京2087"
    assert any(m["scope"] == GLOBAL_SCOPE for m in merged)


def test_delete(isolated_assets):
    svc = isolated_assets
    a = svc.create(scope=GLOBAL_SCOPE, asset_type="note", title="临时笔记")
    assert svc.delete(a["asset_id"], scope=GLOBAL_SCOPE) is True
    assert svc.get(a["asset_id"], scope=GLOBAL_SCOPE) is None


def test_link_persists_project_id(isolated_assets):
    """project 范围下的 link 必须把 project_id 写入 asset_links，
    否则 cascade_delete_project 按 project_id 过滤删除时会漏掉它们。"""
    svc = isolated_assets
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    src = svc.create(
        scope=PROJECT_SCOPE, project_id=pid,
        asset_type="note", title="A",
    )
    dst = svc.create(
        scope=PROJECT_SCOPE, project_id=pid,
        asset_type="note", title="B",
    )
    svc.link(
        src["asset_id"], dst["asset_id"], "references",
        scope=PROJECT_SCOPE, project_id=pid,
    )
    from sqlalchemy import select
    from app.tables.assets import asset_links
    with svc._repo.connect() as conn:
        row = conn.execute(
            select(asset_links).where(
                asset_links.c.src_asset_id == src["asset_id"],
            ),
        ).fetchone()
    assert row is not None
    assert row._mapping["project_id"] == pid


def test_link_global_scope_leaves_project_id_null(isolated_assets):
    """global scope 下的 link 不应写 project_id。"""
    svc = isolated_assets
    a = svc.create(scope=GLOBAL_SCOPE, asset_type="note", title="A")
    b = svc.create(scope=GLOBAL_SCOPE, asset_type="note", title="B")
    svc.link(
        a["asset_id"], b["asset_id"], "references",
        scope=GLOBAL_SCOPE,
    )
    from sqlalchemy import select
    from app.tables.assets import asset_links
    with svc._repo.connect() as conn:
        row = conn.execute(
            select(asset_links).where(
                asset_links.c.src_asset_id == a["asset_id"],
            ),
        ).fetchone()
    assert row is not None
    assert row._mapping["project_id"] is None
