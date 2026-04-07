"""Manuscript ↔ assets adapter.

Stores manuscript blocks as ``asset_type='manuscript_block'`` rows in the
project-scoped assets DB while exposing the legacy block dict shape that
``NovelDB.commit_manuscript_block`` / ``list_manuscript_blocks`` callers expect.

Block ordering is kept in ``payload['block_order']`` (int with gap=10), and
all per-block metadata (chapter_id, pov, threads, …) lives in payload too.
Chapter joins are resolved via an injected ``chapter_lookup`` callable so this
module stays free of writer-agent imports.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Callable

from .assets_storage import AssetsStorage


_BLOCK_ORDER_GAP = 10


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_block_id() -> str:
    return f"mb_{uuid.uuid4().hex[:12]}"


# Fields that become top-level keys in the legacy block dict.
_PAYLOAD_KEYS = (
    "block_order", "chapter_id", "chapter_tag", "source_scene_id",
    "open_threads_json", "pov_entity_id", "involved_entities_json",
    "location", "narrative_note",
)


def _row_to_block(row: sqlite3.Row, include_content: bool = True) -> dict[str, Any]:
    payload = {}
    raw = row["payload_json"]
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
    block: dict[str, Any] = {
        "block_id": row["asset_id"],
        "project_id": row["project_id"],
        "block_order": int(payload.get("block_order") or 0),
        "word_count": int(row["word_count"] or 0),
        "chapter_id": payload.get("chapter_id"),
        "chapter_tag": payload.get("chapter_tag"),
        "source_scene_id": payload.get("source_scene_id"),
        "summary": row["summary"] or "",
        "open_threads_json": payload.get("open_threads_json"),
        "pov_entity_id": payload.get("pov_entity_id"),
        "involved_entities_json": payload.get("involved_entities_json"),
        "location": payload.get("location"),
        "narrative_note": payload.get("narrative_note"),
        "committed_at": row["created_at"],
    }
    if include_content:
        block["content"] = row["content"] or ""
    return block


ChapterLookup = Callable[[str], dict | None]
"""``chapter_lookup(chapter_id) -> {'title': str, 'chapter_order': int} | None``"""


class ManuscriptAssetAdapter:
    """Project-scoped manuscript blocks backed by the assets DB."""

    def __init__(self, project_id: str, chapter_lookup: ChapterLookup | None = None):
        self.project_id = project_id
        self.store = AssetsStorage.for_project(project_id)
        self._chapter_lookup = chapter_lookup or (lambda _cid: None)

    # ------------------------------------------------------------------
    # SQL helpers
    # ------------------------------------------------------------------

    def _select_blocks(
        self, conn: sqlite3.Connection, where: str = "", params: tuple = ()
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT * FROM assets
            WHERE asset_type = 'manuscript_block' AND project_id = ?
        """
        all_params: list[Any] = [self.project_id]
        if where:
            sql += " AND " + where
            all_params.extend(params)
        sql += " ORDER BY CAST(json_extract(payload_json, '$.block_order') AS INTEGER)"
        return conn.execute(sql, all_params).fetchall()

    def _max_block_order(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(CAST(json_extract(payload_json, '$.block_order') AS INTEGER)), 0) AS mx
            FROM assets WHERE asset_type = 'manuscript_block' AND project_id = ?
            """,
            (self.project_id,),
        ).fetchone()
        return int(row["mx"] or 0)

    def _set_block_order(self, conn: sqlite3.Connection, asset_id: str, order: int) -> None:
        conn.execute(
            """
            UPDATE assets
            SET payload_json = json_set(COALESCE(payload_json, '{}'), '$.block_order', ?),
                updated_at = ?
            WHERE asset_id = ?
            """,
            (order, _now(), asset_id),
        )

    def _resolve_chapter_tag(self, chapter_id: str | None) -> str | None:
        if not chapter_id:
            return None
        ch = self._chapter_lookup(chapter_id)
        if not ch:
            return None
        return f"第{ch.get('chapter_order', '?')}章 · {ch.get('title', '')}"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def commit(
        self,
        content: str,
        *,
        source_scene_id: str | None = None,
        insert_after_block_id: str | None = None,
        chapter_id: str | None = None,
        pov_entity_id: str | None = None,
        location: str | None = None,
        involved_entities_json: str | None = None,
    ) -> dict[str, Any]:
        block_id = _new_block_id()
        now = _now()
        word_count = len(content)
        chapter_tag = self._resolve_chapter_tag(chapter_id)

        with self.store.connect() as conn:
            # Determine block_order
            if insert_after_block_id:
                ref = conn.execute(
                    "SELECT CAST(json_extract(payload_json, '$.block_order') AS INTEGER) AS bo "
                    "FROM assets WHERE asset_id = ?",
                    (insert_after_block_id,),
                ).fetchone()
                if ref is None or ref["bo"] is None:
                    block_order = self._max_block_order(conn) + _BLOCK_ORDER_GAP
                else:
                    ref_order = int(ref["bo"])
                    nxt = conn.execute(
                        """
                        SELECT MIN(CAST(json_extract(payload_json, '$.block_order') AS INTEGER)) AS nxt
                        FROM assets
                        WHERE asset_type = 'manuscript_block' AND project_id = ?
                          AND CAST(json_extract(payload_json, '$.block_order') AS INTEGER) > ?
                        """,
                        (self.project_id, ref_order),
                    ).fetchone()
                    if nxt and nxt["nxt"] is not None:
                        gap = int(nxt["nxt"]) - ref_order
                        if gap > 1:
                            block_order = ref_order + gap // 2
                        else:
                            self._renumber(conn)
                            ref2 = conn.execute(
                                "SELECT CAST(json_extract(payload_json, '$.block_order') AS INTEGER) AS bo "
                                "FROM assets WHERE asset_id = ?",
                                (insert_after_block_id,),
                            ).fetchone()
                            block_order = int(ref2["bo"]) + _BLOCK_ORDER_GAP // 2
                    else:
                        block_order = ref_order + _BLOCK_ORDER_GAP
            else:
                block_order = self._max_block_order(conn) + _BLOCK_ORDER_GAP

            payload = {
                "block_order": block_order,
                "chapter_id": chapter_id,
                "chapter_tag": chapter_tag,
                "source_scene_id": source_scene_id,
                "pov_entity_id": pov_entity_id,
                "location": location,
                "involved_entities_json": involved_entities_json,
                "open_threads_json": None,
                "narrative_note": None,
            }

            conn.execute(
                """
                INSERT INTO assets (
                    asset_id, scope, project_id, asset_type, category, title,
                    summary, content, payload_json, tags_json,
                    source_kind, source_ref, enabled, pinned, word_count,
                    created_at, updated_at
                ) VALUES (?, 'project', ?, 'manuscript_block', '', ?, '', ?, ?, '[]',
                          'writer_agent_commit', ?, 1, 0, ?, ?, ?)
                """,
                (
                    block_id,
                    self.project_id,
                    f"块 #{block_order}",
                    content,
                    json.dumps(payload, ensure_ascii=False),
                    source_scene_id or "",
                    word_count,
                    now,
                    now,
                ),
            )
            conn.commit()

        return {
            "block_id": block_id,
            "block_order": block_order,
            "word_count": word_count,
            "chapter_id": chapter_id,
            "committed_at": now,
        }

    def _renumber(self, conn: sqlite3.Connection) -> None:
        rows = self._select_blocks(conn)
        for idx, r in enumerate(rows):
            self._set_block_order(conn, r["asset_id"], (idx + 1) * _BLOCK_ORDER_GAP)

    def list_blocks(
        self, *, include_content: bool = True, chapter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            if chapter_id is not None:
                rows = self._select_blocks(
                    conn,
                    "json_extract(payload_json, '$.chapter_id') = ?",
                    (chapter_id,),
                )
            else:
                rows = self._select_blocks(conn)
            blocks = [_row_to_block(r, include_content=include_content) for r in rows]
            if not include_content:
                for b in blocks:
                    b.pop("content", None)
            return blocks

    def get_block(self, block_id: str) -> dict[str, Any] | None:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE asset_id = ? AND asset_type = 'manuscript_block'",
                (block_id,),
            ).fetchone()
            return _row_to_block(row) if row else None

    def update_block(self, block_id: str, **kwargs: Any) -> None:
        allowed_top = {"content", "summary"}
        allowed_payload = {
            "chapter_id", "chapter_tag", "open_threads_json", "pov_entity_id",
            "involved_entities_json", "location", "narrative_note",
        }
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload_json, content FROM assets WHERE asset_id = ?",
                (block_id,),
            ).fetchone()
            if not row:
                return
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}

            sets: list[str] = []
            params: list[Any] = []
            for k, v in kwargs.items():
                if k in allowed_top:
                    sets.append(f"{k} = ?")
                    params.append(v if v is not None else "")
                elif k in allowed_payload:
                    payload[k] = v

            # Auto-derive chapter_tag if chapter_id changed but tag not given
            if "chapter_id" in kwargs and "chapter_tag" not in kwargs:
                payload["chapter_tag"] = self._resolve_chapter_tag(kwargs.get("chapter_id"))

            if "content" in kwargs:
                sets.append("word_count = ?")
                params.append(len(kwargs["content"] or ""))

            sets.append("payload_json = ?")
            params.append(json.dumps(payload, ensure_ascii=False))
            sets.append("updated_at = ?")
            params.append(_now())
            params.append(block_id)
            conn.execute(
                f"UPDATE assets SET {', '.join(sets)} WHERE asset_id = ?",
                params,
            )
            conn.commit()

    def delete_block(self, block_id: str) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "DELETE FROM assets WHERE asset_id = ? AND asset_type = 'manuscript_block'",
                (block_id,),
            )
            conn.commit()

    def reorder(self, block_ids: list[str]) -> None:
        with self.store.connect() as conn:
            for idx, bid in enumerate(block_ids):
                self._set_block_order(conn, bid, (idx + 1) * _BLOCK_ORDER_GAP)
            conn.commit()

    def tag_blocks(self, block_ids: list[str], chapter_tag: str) -> int:
        with self.store.connect() as conn:
            for bid in block_ids:
                row = conn.execute(
                    "SELECT payload_json FROM assets WHERE asset_id = ?",
                    (bid,),
                ).fetchone()
                if not row:
                    continue
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except json.JSONDecodeError:
                    payload = {}
                payload["chapter_tag"] = chapter_tag
                conn.execute(
                    "UPDATE assets SET payload_json = ?, updated_at = ? WHERE asset_id = ?",
                    (json.dumps(payload, ensure_ascii=False), _now(), bid),
                )
            conn.commit()
            return len(block_ids)

    def move_to_chapter(self, block_id: str, target_chapter_id: str | None) -> None:
        chapter_tag = self._resolve_chapter_tag(target_chapter_id)
        self.update_block(
            block_id,
            chapter_id=target_chapter_id,
            chapter_tag=chapter_tag,
        )

    # ------------------------------------------------------------------
    # Stats / search / export / continuation
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total_blocks, COALESCE(SUM(word_count), 0) AS total_words
                FROM assets WHERE asset_type = 'manuscript_block' AND project_id = ?
                """,
                (self.project_id,),
            ).fetchone()
            tag_rows = conn.execute(
                """
                SELECT DISTINCT json_extract(payload_json, '$.chapter_tag') AS tag
                FROM assets
                WHERE asset_type = 'manuscript_block' AND project_id = ?
                  AND json_extract(payload_json, '$.chapter_tag') IS NOT NULL
                ORDER BY CAST(json_extract(payload_json, '$.block_order') AS INTEGER)
                """,
                (self.project_id,),
            ).fetchall()
            chapter_rows = conn.execute(
                """
                SELECT json_extract(payload_json, '$.chapter_id') AS chapter_id,
                       COUNT(*) AS block_count,
                       COALESCE(SUM(word_count), 0) AS word_count
                FROM assets
                WHERE asset_type = 'manuscript_block' AND project_id = ?
                  AND json_extract(payload_json, '$.chapter_id') IS NOT NULL
                GROUP BY json_extract(payload_json, '$.chapter_id')
                """,
                (self.project_id,),
            ).fetchall()

        chapters: list[dict[str, Any]] = []
        for r in chapter_rows:
            cid = r["chapter_id"]
            ch = self._chapter_lookup(cid) or {}
            chapters.append({
                "chapter_id": cid,
                "title": ch.get("title", ""),
                "chapter_order": ch.get("chapter_order", 0),
                "block_count": r["block_count"],
                "word_count": r["word_count"],
            })
        chapters.sort(key=lambda c: c.get("chapter_order") or 0)

        return {
            "total_blocks": row["total_blocks"],
            "total_words": row["total_words"],
            "chapter_tags": [r["tag"] for r in tag_rows if r["tag"]],
            "chapters": chapters,
        }

    def search_fts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        # Reuse the assets FTS index, restricting to manuscript_block.
        from .assets_service import _build_fts_match
        match_expr = _build_fts_match(query)
        with self.store.connect() as conn:
            if match_expr:
                rows = conn.execute(
                    """
                    SELECT a.*, snippet(assets_fts, 2, '<b>', '</b>', '...', 48) AS snippet
                    FROM assets_fts
                    JOIN assets a ON a.rowid = assets_fts.rowid
                    WHERE assets_fts MATCH ?
                      AND a.asset_type = 'manuscript_block'
                      AND a.project_id = ?
                    LIMIT ?
                    """,
                    (match_expr, self.project_id, limit),
                ).fetchall()
            else:
                like = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT a.*, SUBSTR(a.content, 1, 96) AS snippet
                    FROM assets a
                    WHERE a.asset_type = 'manuscript_block' AND a.project_id = ?
                      AND (a.content LIKE ? OR a.summary LIKE ?)
                    ORDER BY CAST(json_extract(a.payload_json, '$.block_order') AS INTEGER)
                    LIMIT ?
                    """,
                    (self.project_id, like, like, limit),
                ).fetchall()

        out: list[dict[str, Any]] = []
        for r in rows:
            block = _row_to_block(r, include_content=False)
            ch = self._chapter_lookup(block["chapter_id"]) if block.get("chapter_id") else None
            out.append({
                "block_id": block["block_id"],
                "block_order": block["block_order"],
                "chapter_id": block.get("chapter_id"),
                "chapter_tag": block.get("chapter_tag"),
                "word_count": block["word_count"],
                "snippet": r["snippet"],
                "chapter_title": (ch or {}).get("title"),
            })
        return out

    def export_text(self) -> str:
        blocks = self.list_blocks(include_content=True)
        # Order: by chapter_order (if known) then block_order
        def sort_key(b: dict) -> tuple:
            ch = self._chapter_lookup(b.get("chapter_id")) if b.get("chapter_id") else None
            return ((ch or {}).get("chapter_order") or 999999, b["block_order"])
        blocks.sort(key=sort_key)
        return "\n\n".join(b["content"] for b in blocks)

    def get_continuation_blocks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM assets
                WHERE asset_type = 'manuscript_block' AND project_id = ?
                ORDER BY CAST(json_extract(payload_json, '$.block_order') AS INTEGER) DESC
                LIMIT ?
                """,
                (self.project_id, limit),
            ).fetchall()
        return [_row_to_block(r) for r in rows]
