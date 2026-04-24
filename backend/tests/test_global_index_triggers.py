"""Contract tests for the global_index sync triggers.

Covers the two trigger generations:
  - 20260419_0001: ``assets``/``archive_library`` each had their own
    triggers.
  - 20260419_0003: archive_library merged into ``assets``; triggers now
    branch on ``asset_type`` (archive_entity vs. everything else).

These tests exercise the current generation only. Archive-entity rows
are inserted through the merged ``assets`` schema with
``asset_type='archive_entity'``.

Coverage:
  * assets (non-archive): INSERT / UPDATE / DELETE propagate to global_index
  * assets (archive_entity): same three propagations, source='archive'
  * Transaction rollback leaves no orphan global_index row
  * Newly written rows are immediately reachable via the FTS index
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, create_engine, text

from app.database import init_db


@pytest.fixture()
def engine() -> Engine:
    e = create_engine("sqlite:///:memory:", future=True)
    init_db(e)
    return e


def _insert_asset(
    engine: Engine,
    *,
    asset_id: str,
    title: str,
    summary: str = "",
    content: str = "",
    asset_type: str = "note",
    project_id: str | None = None,
    tags_json: str = "[]",
    payload_json: str = "{}",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO assets (
                    asset_id, project_id, scope, asset_type, category, title,
                    summary, content, payload_json, tags_json, source_kind,
                    source_ref, enabled, pinned, word_count, created_at, updated_at
                ) VALUES (
                    :aid, :pid, 'global', :atype, '', :title,
                    :summary, :content, :payload, :tags, 'test',
                    '', 1, 0, 0, '2026-01-01', '2026-01-01'
                )
                """
            ),
            {
                "aid": asset_id,
                "pid": project_id,
                "atype": asset_type,
                "title": title,
                "summary": summary,
                "content": content,
                "payload": payload_json,
                "tags": tags_json,
            },
        )


def _insert_archive(
    engine: Engine,
    *,
    archive_id: str,
    project_id: str,
    entity_name: str,
    entity_type: str = "character",
    core_drive: str = "",
    surface_mask: str = "",
    hidden_tension: str = "",
    relationship_summary: str = "",
    entity_role: str = "",
    template_payload_json: str = "{}",
) -> None:
    """Insert an archive entity. Post-P5 archive rows live in ``assets``
    with ``asset_type='archive_entity'``; the archive-specific columns
    (entity_*, template_*, *_tier) carry the domain data."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO assets (
                    asset_id, project_id, scope, asset_type, category, title,
                    summary, content, payload_json, tags_json,
                    source_kind, source_ref, enabled, pinned, word_count,
                    created_at, updated_at,
                    entity_uuid, entity_name, entity_type, agent_kind,
                    importance_tier, recommended_importance_tier,
                    selected_importance_tier, template_key, template_version,
                    entity_role, core_drive, surface_mask, hidden_tension,
                    relationship_summary, agent_behavior_hint,
                    human_ai_relation_tag, can_act_as_agent,
                    notable_risks_json, template_sections_json,
                    template_payload_json, template_metadata_json,
                    synced_at
                ) VALUES (
                    :aid, :pid, 'project', 'archive_entity', '', :name,
                    :role, '', '{}', '[]',
                    'archive', :uuid, 1, 0, 0,
                    '2026-01-01', '2026-01-01',
                    :uuid, :name, :etype, 'generic',
                    'supporting', 'supporting',
                    'supporting', 'generic.supporting.v1', 'v1',
                    :role, :drive, :mask, :tension,
                    :rel_summary, '',
                    '', 1,
                    '[]', '[]',
                    :payload, '{}',
                    '2026-01-01'
                )
                """
            ),
            {
                "aid": archive_id,
                "pid": project_id,
                "uuid": f"uuid_{archive_id}",
                "name": entity_name,
                "etype": entity_type,
                "role": entity_role,
                "drive": core_drive,
                "mask": surface_mask,
                "tension": hidden_tension,
                "rel_summary": relationship_summary,
                "payload": template_payload_json,
            },
        )


def _fetch_global_row(engine: Engine, source: str, source_ref: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json "
                "FROM global_index WHERE source = :src AND source_ref = :ref"
            ),
            {"src": source, "ref": source_ref},
        ).fetchone()
    if row is None:
        return None
    return dict(row._mapping)


# ----------------------------------------------------------------------
# assets ↔ global_index
# ----------------------------------------------------------------------


def test_assets_insert_populates_global_index(engine):
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(
        engine,
        asset_id=aid,
        title="冷峻第一人称",
        summary="冷静克制",
        content="句式短促",
        asset_type="writing_style",
        tags_json='["冷峻","短句"]',
    )
    row = _fetch_global_row(engine, "assets", aid)
    assert row is not None
    assert row["title"] == "冷峻第一人称"
    assert "冷静克制" in row["body"]
    assert "句式短促" in row["body"]
    assert row["entity_type"] == "writing_style"
    assert row["tags"] == '["冷峻","短句"]'


def test_assets_update_refreshes_global_index(engine):
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(engine, asset_id=aid, title="旧标题", summary="旧摘要")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE assets SET title = :t, summary = :s WHERE asset_id = :aid"),
            {"t": "新标题", "s": "新摘要", "aid": aid},
        )
    row = _fetch_global_row(engine, "assets", aid)
    assert row is not None
    assert row["title"] == "新标题"
    assert "新摘要" in row["body"]
    assert "旧摘要" not in row["body"]


def test_assets_delete_removes_global_index(engine):
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(engine, asset_id=aid, title="要删除的资产")
    assert _fetch_global_row(engine, "assets", aid) is not None
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM assets WHERE asset_id = :aid"), {"aid": aid})
    assert _fetch_global_row(engine, "assets", aid) is None


def test_assets_insert_preserves_project_id(engine):
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    _insert_asset(engine, asset_id=aid, title="项目资产", project_id=pid)
    row = _fetch_global_row(engine, "assets", aid)
    assert row is not None
    assert row["project_id"] == pid


def test_assets_global_scope_project_id_is_null(engine):
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(engine, asset_id=aid, title="全局资产", project_id=None)
    row = _fetch_global_row(engine, "assets", aid)
    assert row is not None
    assert row["project_id"] is None


# ----------------------------------------------------------------------
# archive entities (stored in assets with asset_type='archive_entity')
# ----------------------------------------------------------------------


def test_archive_insert_populates_global_index(engine):
    aid = f"arc_{uuid.uuid4().hex[:8]}"
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    _insert_archive(
        engine,
        archive_id=aid,
        project_id=pid,
        entity_name="林觉",
        entity_type="character",
        core_drive="保护族人",
        surface_mask="冷漠学者",
        hidden_tension="失去家人的创伤",
        entity_role="主角",
    )
    row = _fetch_global_row(engine, "archive", aid)
    assert row is not None
    assert row["title"] == "林觉"
    assert row["entity_type"] == "character"
    assert row["project_id"] == pid
    assert "保护族人" in row["body"]
    assert "冷漠学者" in row["body"]
    assert "失去家人的创伤" in row["body"]
    assert "主角" in row["body"]


def test_archive_update_refreshes_global_index(engine):
    aid = f"arc_{uuid.uuid4().hex[:8]}"
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    _insert_archive(engine, archive_id=aid, project_id=pid, entity_name="原名")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE assets SET entity_name = :n, title = :n WHERE asset_id = :aid AND asset_type = 'archive_entity'"),
            {"n": "改名后", "aid": aid},
        )
    row = _fetch_global_row(engine, "archive", aid)
    assert row is not None
    assert row["title"] == "改名后"


def test_archive_delete_removes_global_index(engine):
    aid = f"arc_{uuid.uuid4().hex[:8]}"
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    _insert_archive(engine, archive_id=aid, project_id=pid, entity_name="临时档案")
    assert _fetch_global_row(engine, "archive", aid) is not None
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM assets WHERE asset_id = :aid AND asset_type = 'archive_entity'"),
            {"aid": aid},
        )
    assert _fetch_global_row(engine, "archive", aid) is None


# ----------------------------------------------------------------------
# Transaction semantics
# ----------------------------------------------------------------------


def test_rollback_prevents_global_index_write(engine):
    """Aborted transaction must not leak a global_index row.

    Triggers fire inside the writing transaction, so rollback of the
    outer transaction must unwind the global_index insert too.
    """
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    conn = engine.connect()
    try:
        trans = conn.begin()
        conn.execute(
            text(
                """
                INSERT INTO assets (
                    asset_id, project_id, scope, asset_type, category, title,
                    summary, content, payload_json, tags_json, source_kind,
                    source_ref, enabled, pinned, word_count, created_at, updated_at
                ) VALUES (
                    :aid, NULL, 'global', 'note', '', '回滚测试',
                    '', '', '{}', '[]', 'test', '', 1, 0, 0, '2026-01-01', '2026-01-01'
                )
                """
            ),
            {"aid": aid},
        )
        trans.rollback()
    finally:
        conn.close()
    assert _fetch_global_row(engine, "assets", aid) is None


# ----------------------------------------------------------------------
# FTS end-to-end: newly inserted content is searchable
# ----------------------------------------------------------------------


def test_fts_finds_newly_inserted_asset(engine):
    """After INSERT, global_index_fts (trigram) should match a substring."""
    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(
        engine,
        asset_id=aid,
        title="神经接口设定",
        summary="脑机接口注入神经突触",
        asset_type="worldview",
    )
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT gi.source, gi.source_ref "
                "FROM global_index_fts gf JOIN global_index gi ON gf.rowid = gi.rowid "
                "WHERE gf.global_index_fts MATCH :q"
            ),
            {"q": "神经接口"},
        ).fetchone()
    assert row is not None
    assert row._mapping["source_ref"] == aid


def test_fts_finds_newly_inserted_archive(engine):
    aid = f"arc_{uuid.uuid4().hex[:8]}"
    pid = f"proj_{uuid.uuid4().hex[:8]}"
    _insert_archive(
        engine,
        archive_id=aid,
        project_id=pid,
        entity_name="苏玄",
        entity_type="character",
        core_drive="追寻失落的古剑传承",
    )
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT gi.source, gi.source_ref "
                "FROM global_index_fts gf JOIN global_index gi ON gf.rowid = gi.rowid "
                "WHERE gf.global_index_fts MATCH :q"
            ),
            {"q": "古剑传承"},
        ).fetchone()
    assert row is not None
    assert row._mapping["source"] == "archive"
    assert row._mapping["source_ref"] == aid


def test_search_path_reflects_update_not_stale_content(engine):
    """End-to-end search: after updating an asset, the backend search
    should return the new content, not the old. This goes through
    ``SearchRepository.search`` — the actual read path used by
    ``/api/unified-assets/search``.
    """
    from app.repositories.search_repo import SearchRepository

    aid = f"asset_{uuid.uuid4().hex[:8]}"
    _insert_asset(
        engine,
        asset_id=aid,
        title="初始标题",
        summary="关键词alpha应能搜到",
        asset_type="note",
    )
    repo = SearchRepository(engine)
    hits_before = repo.search("alpha", sources=["assets"])
    assert any(h["source_ref"] == aid for h in hits_before)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE assets SET summary = :s WHERE asset_id = :aid"),
            {"s": "完全替换为beta关键词", "aid": aid},
        )

    hits_beta = repo.search("beta", sources=["assets"])
    assert any(h["source_ref"] == aid for h in hits_beta)

    # After update, a search for the old "alpha" must not return the
    # updated row with stale content. We check the returned row's body
    # no longer mentions alpha (stale FTS tokens without matching content
    # rows are not a correctness issue here).
    hits_alpha = repo.search("alpha", sources=["assets"])
    for h in hits_alpha:
        if h["source_ref"] == aid:
            assert "alpha" not in (h.get("body") or ""), \
                "global_index row should no longer contain old summary"
