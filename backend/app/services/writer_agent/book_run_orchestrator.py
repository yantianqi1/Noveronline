"""Book-run orchestrator: multi-chapter agent task.

State machine:

    PLAN_INIT → RETRIEVE → OUTLINE →
    ┌── FOR chapter IN plan: ───────────────────────────────────┐
    │  CHAPTER_WRITE → WORD_AUDIT → LEXICON_AUDIT → CHAPTER_COMMIT │
    └───────────────────────────────────────────────────────────┘
    → DONE

Each inner stage runs an ``AgentLoop`` with a tailored system prompt and
tool whitelist. Scripted audits (word count / forbidden lexicon) gate the
audit loops so they only fire when a problem is detected.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional

from ...database import get_engine
from ...repositories.chapter_repo import ChapterRepository
from ...repositories.outline_repo import OutlineRepository
from ...utils.word_count import count_cjk_chars
from ..assets.manuscript_adapter import ManuscriptAssetAdapter
from .agent_loop import AgentLoop
from .book_plan_service import BookPlanService
from .prompts import (
    build_book_outline_prompt,
    build_book_retrieval_planner_prompt,
    build_chapter_writer_prompt,
    build_lexicon_audit_prompt,
    build_word_audit_prompt,
)
from .tool_executors import _load_forbidden_lexicon_entries
from .tools import (
    ASSET_TOOLS,
    BOOK_RUN_TOOLS,
    MANUSCRIPT_TOOLS,
    NOVEL_TOOLS,
    UNIFIED_TOOLS,
)

logger = logging.getLogger(__name__)


# Tool whitelist sets per stage -------------------------------------------------

_READ_TOOL_NAMES = {
    "query_entity", "query_relationship", "query_chapter", "query_scene",
    "search_settings", "get_recent_scenes", "get_world_state",
    "list_worldline_branches", "get_branch_timeline", "get_branch_agent_state",
    "get_open_threads", "get_character_voice", "query_relationship_timeline",
    "query_character_timeline", "query_thread_history", "search_world_rules",
    "get_story_overview", "query_segment_summaries", "get_story_ontology",
    "search_assets", "get_asset", "list_assets",
    "global_search", "query_graph_neighbors", "query_event",
    "query_relationship_network", "query_worldline_session",
    "get_manuscript_context", "search_manuscript", "get_manuscript_stats",
    "get_chapter_word_stats", "list_forbidden_lexicon",
}

_WORD_AUDIT_TOOL_NAMES = {
    "get_chapter_word_stats", "query_scene", "search_manuscript",
    "get_manuscript_context", "splice_block",
}

_LEXICON_AUDIT_TOOL_NAMES = {
    "scan_forbidden_lexicon", "get_manuscript_context", "rewrite_span",
}


def _filter_tools(all_tools: List[Dict], allowed_names: set[str]) -> List[Dict]:
    return [t for t in all_tools if t.get("function", {}).get("name") in allowed_names]


_ALL_TOOLS = NOVEL_TOOLS + ASSET_TOOLS + UNIFIED_TOOLS + MANUSCRIPT_TOOLS + BOOK_RUN_TOOLS

_READ_ONLY_TOOLS = _filter_tools(_ALL_TOOLS, _READ_TOOL_NAMES)
_WORD_AUDIT_TOOLS = _filter_tools(_ALL_TOOLS, _WORD_AUDIT_TOOL_NAMES)
_LEXICON_AUDIT_TOOLS = _filter_tools(_ALL_TOOLS, _LEXICON_AUDIT_TOOL_NAMES)


# Limits -----------------------------------------------------------------------

_AUDIT_MAX_ROUNDS = 6                  # max AgentLoop rounds per audit stage
_AUDIT_CROSS_MAX_CYCLES = 2            # how many times WORD↔LEXICON can ping-pong
_CHAPTER_PROSE_MAX_CHARS = 60_000      # safety cap on agent output
_RETRIEVE_SUMMARY_HEAD = 8000          # chars kept as retrieval summary


# ------------------------------------------------------------------------------


class BookRunOrchestrator:
    """Run a persisted ``book_plan`` end-to-end, yielding SSE events."""

    def __init__(self, llm_router=None):
        from ..llm_router import LlmRouter
        self.router = llm_router or LlmRouter()
        self.plan_service = BookPlanService()
        self._engine = get_engine()

    async def run(self, plan_id: str) -> AsyncIterator[Dict[str, Any]]:
        t0 = time.monotonic()

        def _stamp() -> Dict[str, Any]:
            return {
                "ts": time.strftime("%H:%M:%S"),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

        plan = self.plan_service.get_plan(plan_id)
        if not plan:
            yield {"type": "error", "message": f"book_plan 不存在: {plan_id}", **_stamp()}
            return

        project_id = plan["project_id"]
        chapter_count = int(plan.get("chapter_count") or 1)
        start_order = int(plan.get("start_chapter_order") or 1)
        self._tolerance_pct = int(plan.get("word_tolerance_pct") or 10)

        yield {"type": "book_run_stage", "stage": "PLAN_INIT", "message": f"启动成书计划 {plan_id}", **_stamp()}
        self.plan_service.set_status(plan_id, "retrieving", last_stage="PLAN_INIT")

        # --- RETRIEVE ----------------------------------------------------------
        try:
            orch_client = await self.router.build_async_client("writer_orchestrator")
        except Exception as exc:
            yield {"type": "error", "message": f"LLM 未绑定 (writer_orchestrator): {exc}", **_stamp()}
            return

        yield {"type": "book_run_stage", "stage": "RETRIEVE", "message": "全书检索规划中...", **_stamp()}
        retrieval_summary = ""
        try:
            retrieval_summary = await self._run_retrieve(plan, project_id, orch_client, t0, _stamp)
            self.plan_service.set_retrieval_summary(plan_id, retrieval_summary)
        except Exception as exc:
            logger.exception("RETRIEVE failed")
            yield {"type": "error", "message": f"RETRIEVE 失败: {exc}", **_stamp()}
            self.plan_service.set_status(plan_id, "failed", last_stage="RETRIEVE")
            self.plan_service.append_error(plan_id, {"stage": "RETRIEVE", "error": str(exc)})
            return

        # --- OUTLINE -----------------------------------------------------------
        yield {"type": "book_run_stage", "stage": "OUTLINE", "message": "生成全书大纲...", **_stamp()}
        self.plan_service.set_status(plan_id, "outlining", last_stage="OUTLINE")

        outline_array: list[dict] = []
        try:
            async for ev in self._run_outline_loop(plan, project_id, orch_client, retrieval_summary, t0):
                if ev["type"] == "book_run_outline_result":
                    outline_array = ev["outline"]
                else:
                    yield ev
        except Exception as exc:
            logger.exception("OUTLINE failed")
            yield {"type": "error", "message": f"OUTLINE 失败: {exc}", **_stamp()}
            self.plan_service.set_status(plan_id, "failed", last_stage="OUTLINE")
            self.plan_service.append_error(plan_id, {"stage": "OUTLINE", "error": str(exc)})
            return

        if not outline_array:
            yield {"type": "error", "message": "OUTLINE 返回为空，终止", **_stamp()}
            self.plan_service.set_status(plan_id, "failed", last_stage="OUTLINE")
            return

        chapter_ids_by_order = await asyncio.to_thread(
            self._persist_outline, plan, outline_array
        )
        self.plan_service.update_plan(
            plan_id,
            chapter_ids=list(chapter_ids_by_order.values()),
        )

        # --- PER-CHAPTER LOOP --------------------------------------------------
        self.plan_service.set_status(plan_id, "writing", last_stage="OUTLINE")
        completed: list[int] = []
        failed: list[dict] = []

        chapter_repo = ChapterRepository(self._engine)
        prev_summary = ""

        for chapter_order in range(start_order, start_order + chapter_count):
            chapter_id = chapter_ids_by_order.get(chapter_order)
            if not chapter_id:
                failed.append({"chapter_order": chapter_order, "reason": "missing_chapter_id"})
                continue
            self.plan_service.set_status(
                plan_id, "writing",
                last_stage=f"CHAPTER_WRITE#{chapter_order}",
                current_chapter_order=chapter_order,
            )
            yield {
                "type": "book_run_stage",
                "stage": "CHAPTER_WRITE",
                "chapter_order": chapter_order,
                "message": f"开始写第 {chapter_order} 章",
                **_stamp(),
            }

            # Grab this chapter's outline entries
            chapter_outline = [
                e for e in outline_array
                if int(e.get("chapter_index") or 0) == chapter_order
            ]

            try:
                prose = ""
                summary_line = ""
                async for ev in self._run_chapter_write(
                    plan, project_id, chapter_order, chapter_id,
                    chapter_outline, prev_summary, retrieval_summary,
                    orch_client, t0,
                ):
                    if ev.get("type") == "_chapter_write_result":
                        prose = ev.get("prose") or ""
                        summary_line = ev.get("summary") or ""
                    else:
                        yield ev
            except Exception as exc:
                logger.exception("CHAPTER_WRITE failed for chapter %s", chapter_order)
                failed.append({"chapter_order": chapter_order, "stage": "CHAPTER_WRITE", "error": str(exc)})
                self.plan_service.append_error(plan_id, failed[-1])
                yield {"type": "error", "chapter_order": chapter_order,
                       "message": f"第 {chapter_order} 章写作失败: {exc}", **_stamp()}
                break

            if not prose.strip():
                reason = "agent returned empty prose"
                failed.append({"chapter_order": chapter_order, "stage": "CHAPTER_WRITE", "reason": reason})
                self.plan_service.append_error(plan_id, failed[-1])
                yield {"type": "error", "chapter_order": chapter_order, "message": reason, **_stamp()}
                break

            # Commit prose as manuscript blocks
            await asyncio.to_thread(
                self._commit_prose_as_blocks, project_id, chapter_id, prose
            )

            stats = await asyncio.to_thread(
                self._scripted_word_stats, project_id, chapter_id, plan.get("per_chapter_word_target")
            )
            yield {
                "type": "chapter_progress",
                "chapter_order": chapter_order,
                "word_count": stats["total"],
                "target": stats["target"],
                "diff_pct": stats["diff_pct"],
                **_stamp(),
            }

            # --- Audit cycles ---
            cycle = 0
            chapter_audit_failed = False
            while cycle < _AUDIT_CROSS_MAX_CYCLES:
                cycle += 1

                # WORD_AUDIT ---------------------------------------------
                if not self._within_tolerance(stats):
                    yield {"type": "book_run_stage", "stage": "WORD_AUDIT",
                           "chapter_order": chapter_order,
                           "message": f"字数差 {stats['diff']:+d}，启动字数审计（第 {cycle} 轮）",
                           **_stamp()}
                    try:
                        async for ev in self._run_word_audit(
                            plan, project_id, chapter_order, chapter_id, orch_client, t0
                        ):
                            yield ev
                    except Exception as exc:
                        logger.exception("WORD_AUDIT failed")
                        failed.append({"chapter_order": chapter_order, "stage": "WORD_AUDIT", "error": str(exc)})
                        self.plan_service.append_error(plan_id, failed[-1])
                        chapter_audit_failed = True
                        break
                    stats = await asyncio.to_thread(
                        self._scripted_word_stats, project_id, chapter_id, plan.get("per_chapter_word_target")
                    )
                    yield {
                        "type": "chapter_progress",
                        "chapter_order": chapter_order,
                        "word_count": stats["total"],
                        "target": stats["target"],
                        "diff_pct": stats["diff_pct"],
                        **_stamp(),
                    }

                # LEXICON_AUDIT ------------------------------------------
                hits = await asyncio.to_thread(
                    self._scripted_lexicon_scan, project_id, chapter_id,
                    plan.get("forbidden_lexicon_asset_ids") or []
                )
                if hits:
                    yield {"type": "audit_hit", "kind": "lexicon",
                           "chapter_order": chapter_order,
                           "details": {"count": len(hits), "sample": hits[:5]},
                           **_stamp()}
                    yield {"type": "book_run_stage", "stage": "LEXICON_AUDIT",
                           "chapter_order": chapter_order,
                           "message": f"禁词命中 {len(hits)} 处，启动禁词审计（第 {cycle} 轮）",
                           **_stamp()}
                    try:
                        async for ev in self._run_lexicon_audit(
                            plan, project_id, chapter_order, chapter_id, orch_client, t0
                        ):
                            yield ev
                    except Exception as exc:
                        logger.exception("LEXICON_AUDIT failed")
                        failed.append({"chapter_order": chapter_order, "stage": "LEXICON_AUDIT", "error": str(exc)})
                        self.plan_service.append_error(plan_id, failed[-1])
                        chapter_audit_failed = True
                        break
                    stats = await asyncio.to_thread(
                        self._scripted_word_stats, project_id, chapter_id, plan.get("per_chapter_word_target")
                    )
                    remaining = await asyncio.to_thread(
                        self._scripted_lexicon_scan, project_id, chapter_id,
                        plan.get("forbidden_lexicon_asset_ids") or []
                    )
                    yield {"type": "audit_fixed", "kind": "lexicon",
                           "chapter_order": chapter_order, "round": cycle,
                           "remaining": len(remaining), **_stamp()}

                word_ok = self._within_tolerance(stats)
                remaining_hits = await asyncio.to_thread(
                    self._scripted_lexicon_scan, project_id, chapter_id,
                    plan.get("forbidden_lexicon_asset_ids") or []
                )
                if word_ok and not remaining_hits:
                    break

            if chapter_audit_failed or not self._within_tolerance(stats):
                failed.append({"chapter_order": chapter_order, "stage": "AUDIT",
                               "reason": "tolerance_not_reached" if not self._within_tolerance(stats) else "audit_error",
                               "stats": stats})
                self.plan_service.append_error(plan_id, failed[-1])
                yield {"type": "error", "chapter_order": chapter_order,
                       "message": "字数/禁词审计未通过，成书流程中止",
                       **_stamp()}
                break

            # CHAPTER_COMMIT
            await asyncio.to_thread(
                chapter_repo.update_chapter, project_id, chapter_id,
                status="completed", summary=summary_line[:500] if summary_line else "",
                word_count=stats["total"],
            )
            self.plan_service.append_chapter_id(plan_id, chapter_id)
            completed.append(chapter_order)
            prev_summary = summary_line or prev_summary
            yield {"type": "book_run_stage", "stage": "CHAPTER_COMMIT",
                   "chapter_order": chapter_order,
                   "message": f"第 {chapter_order} 章落库完成（{stats['total']} 字）",
                   **_stamp()}

        # --- DONE --------------------------------------------------------------
        final_status = "completed" if not failed else "failed"
        self.plan_service.set_status(plan_id, final_status, last_stage="DONE")
        yield {
            "type": "book_run_done",
            "plan_id": plan_id,
            "chapters_completed": completed,
            "failed_chapters": failed,
            "status": final_status,
            **_stamp(),
        }

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    async def _run_retrieve(
        self, plan: dict, project_id: str, orch_client, t0: float, stamp_fn,
    ) -> str:
        """Run a single AgentLoop over _READ_ONLY_TOOLS; return brief output as summary."""
        system_prompt = build_book_retrieval_planner_prompt(plan)
        user_msg = (
            "你现在的任务：按前述硬规则收集本书写作的全局上下文。\n"
            "实际调用工具（这个 agent 有工具权限），每轮可并发多个工具，"
            "最终以中文摘要的形式输出结论，长度不超过 6000 字。"
        )
        loop = AgentLoop(
            llm_client=orch_client,
            tools=_READ_ONLY_TOOLS,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        final_text = ""
        async for ev in loop.run(user_msg):
            if ev["type"] == "brief_ready":
                final_text = ev.get("content") or ""
        return (final_text or "")[:_RETRIEVE_SUMMARY_HEAD]

    async def _run_outline_loop(
        self, plan: dict, project_id: str, orch_client, retrieval_summary: str, t0: float,
    ):
        system_prompt = build_book_outline_prompt(plan, retrieval_summary)
        user_msg = (
            "请生成本书大纲。遵守前述硬规则输出 JSON 数组（用 ```json 代码块包裹）。"
        )
        loop = AgentLoop(
            llm_client=orch_client,
            tools=_READ_ONLY_TOOLS,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        final_text = ""
        async for ev in loop.run(user_msg):
            if ev["type"] == "brief_ready":
                final_text = ev.get("content") or ""
            elif ev["type"] in ("tool_call", "tool_result", "thinking", "error"):
                yield ev
        outline = _parse_json_array(final_text)
        yield {"type": "book_run_outline_result", "outline": outline}

    def _persist_outline(self, plan: dict, outline_array: list[dict]) -> dict[int, str]:
        """Group outline entries by chapter_index, create chapter rows, save versions.

        Returns {chapter_order: chapter_id}.
        """
        project_id = plan["project_id"]
        start_order = int(plan.get("start_chapter_order") or 1)
        chapter_count = int(plan.get("chapter_count") or 1)
        chapter_repo = ChapterRepository(self._engine)
        outline_repo = OutlineRepository(self._engine)

        # Group by chapter_index
        by_chapter: dict[int, list[dict]] = {}
        for entry in outline_array:
            try:
                idx = int(entry.get("chapter_index") or 0)
            except (TypeError, ValueError):
                idx = 0
            if idx <= 0:
                continue
            by_chapter.setdefault(idx, []).append(entry)

        result: dict[int, str] = {}
        for chapter_order in range(start_order, start_order + chapter_count):
            entries = by_chapter.get(chapter_order) or []
            # Find or create chapter
            existing = chapter_repo.get_chapter_by_order(project_id, chapter_order)
            if existing:
                chapter_id = existing["chapter_id"]
            else:
                chapter_id = f"chap_{uuid.uuid4().hex[:12]}"
                title = ""
                if entries:
                    hint = entries[0].get("direction_hint") or entries[0].get("title") or ""
                    title = str(hint)[:40]
                chapter_repo.create_chapter(project_id, chapter_id, chapter_order, title=title)

            outline_json = json.dumps(entries, ensure_ascii=False)
            chapter_repo.update_chapter(
                project_id, chapter_id,
                outline_json=outline_json,
                pov_character=(entries[0].get("pov") if entries else "") or "",
            )
            version_id = outline_repo.save_outline_version(
                project_id, chapter_id, outline_json,
                label=f"book_run:{plan.get('plan_id', '')}",
            )
            self.plan_service.append_outline_version(plan["plan_id"], version_id)
            result[chapter_order] = chapter_id
        return result

    async def _run_chapter_write(
        self, plan: dict, project_id: str, chapter_order: int, chapter_id: str,
        chapter_outline: list[dict], prev_summary: str, retrieval_summary: str,
        orch_client, t0: float,
    ):
        """Run chapter writer loop. Yields SSE events plus a final sentinel
        event ``{"type": "_chapter_write_result", "prose": ..., "summary": ...}``.
        """
        system_prompt = build_chapter_writer_prompt(
            plan, chapter_order, chapter_id, chapter_outline,
            prev_summary, retrieval_summary,
        )
        user_msg = (
            f"请为第 {chapter_order} 章创作全部正文。严格遵守大纲与目标字数，"
            "用 ```chapter``` 代码块包裹正文。不要调用任何写工具。"
        )
        loop = AgentLoop(
            llm_client=orch_client,
            tools=_READ_ONLY_TOOLS,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        final_text = ""
        async for ev in loop.run(user_msg):
            if ev["type"] == "brief_ready":
                final_text = ev.get("content") or ""
            elif ev["type"] in ("tool_call", "tool_result", "thinking", "error"):
                yield ev
        prose = _extract_chapter_prose(final_text)
        summary_line = _extract_summary_line(final_text)
        yield {
            "type": "_chapter_write_result",
            "prose": prose[:_CHAPTER_PROSE_MAX_CHARS],
            "summary": summary_line,
        }

    def _commit_prose_as_blocks(self, project_id: str, chapter_id: str, prose: str) -> None:
        """Split prose by blank lines and commit each paragraph-cluster as a manuscript block."""
        chapter_repo = ChapterRepository(self._engine)
        adapter = ManuscriptAssetAdapter(
            project_id,
            chapter_lookup=lambda cid: chapter_repo.get_chapter(project_id, cid) if cid else None,
        )
        # Cluster every 2-3 paragraphs into one block for editability granularity
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
        blocks: list[str] = []
        buf: list[str] = []
        for p in paragraphs:
            buf.append(p)
            if sum(len(x) for x in buf) >= 400 or len(buf) >= 3:
                blocks.append("\n\n".join(buf))
                buf = []
        if buf:
            blocks.append("\n\n".join(buf))

        last_id: str | None = None
        for b in blocks:
            result = adapter.commit(b, chapter_id=chapter_id, insert_after_block_id=last_id)
            last_id = result["block_id"]

    def _scripted_word_stats(
        self, project_id: str, chapter_id: str, target: int | None,
    ) -> dict[str, Any]:
        chapter_repo = ChapterRepository(self._engine)
        adapter = ManuscriptAssetAdapter(
            project_id,
            chapter_lookup=lambda cid: chapter_repo.get_chapter(project_id, cid) if cid else None,
        )
        blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
        total = sum(count_cjk_chars(b.get("content") or "") for b in blocks)
        tgt = int(target) if target else 0
        diff = total - tgt
        diff_pct = (diff / tgt * 100) if tgt else 0.0
        return {"total": total, "target": tgt, "diff": diff, "diff_pct": diff_pct}

    def _scripted_lexicon_scan(
        self, project_id: str, chapter_id: str, lexicon_asset_ids: list[str],
    ) -> list[dict]:
        """Structured scan that returns hit dicts (reuses tool_executors helpers)."""
        return _structured_scan(project_id, chapter_id, lexicon_asset_ids)

    def _within_tolerance(self, stats: dict) -> bool:
        tgt = stats.get("target") or 0
        if not tgt:
            return True  # no target → skip audit
        return abs(stats.get("diff_pct") or 0) <= getattr(self, "_tolerance_pct", 10)

    async def _run_word_audit(
        self, plan: dict, project_id: str, chapter_order: int, chapter_id: str,
        orch_client, t0: float,
    ):
        system_prompt = build_word_audit_prompt(plan, chapter_order, chapter_id)
        user_msg = (
            f"请对章节 {chapter_id} 做字数审计。先调 get_chapter_word_stats 拿数据，"
            "再按硬规则决定扩写或精简，直到进入容忍区间。"
        )
        loop = AgentLoop(
            llm_client=orch_client,
            tools=_WORD_AUDIT_TOOLS,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        loop.MAX_ROUNDS = _AUDIT_MAX_ROUNDS
        async for ev in loop.run(user_msg):
            if ev["type"] in ("tool_call", "tool_result", "thinking", "error", "brief_ready"):
                yield ev

    async def _run_lexicon_audit(
        self, plan: dict, project_id: str, chapter_order: int, chapter_id: str,
        orch_client, t0: float,
    ):
        system_prompt = build_lexicon_audit_prompt(plan, chapter_order, chapter_id)
        user_msg = (
            f"请对章节 {chapter_id} 做禁词审计。先调 scan_forbidden_lexicon 拿命中，"
            "再逐条 rewrite_span 修复。"
        )
        loop = AgentLoop(
            llm_client=orch_client,
            tools=_LEXICON_AUDIT_TOOLS,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        loop.MAX_ROUNDS = _AUDIT_MAX_ROUNDS
        async for ev in loop.run(user_msg):
            if ev["type"] in ("tool_call", "tool_result", "thinking", "error", "brief_ready"):
                yield ev


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_json_array(text: str) -> list[dict]:
    if not text:
        return []
    m = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", text)
    if m:
        try:
            result = json.loads(m.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    start = text.find("[")
    if start < 0:
        return []
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(text[start:i + 1])
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    return []
    return []


_CHAPTER_BLOCK_RE = re.compile(r"```chapter\s*([\s\S]+?)```", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(r"^SUMMARY:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def _extract_chapter_prose(text: str) -> str:
    if not text:
        return ""
    m = _CHAPTER_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: take everything if no fenced block
    # Strip any leading JSON-like meta lines
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("SUMMARY:")]
    return "\n".join(lines).strip()


def _extract_summary_line(text: str) -> str:
    if not text:
        return ""
    m = _SUMMARY_LINE_RE.search(text)
    return m.group(1).strip() if m else ""


def _structured_scan(
    project_id: str, chapter_id: str, lexicon_asset_ids: list[str],
) -> list[dict]:
    """Structured variant of scan_forbidden_lexicon returning hit dicts (not text).

    Used internally by the orchestrator to decide whether to trigger LEXICON_AUDIT.
    Shares the same entry-loading logic as the agent tool.
    """
    import re as _re
    import time as _time
    from .tool_executors import _get_manuscript_adapter, _format_hit

    adapter = _get_manuscript_adapter(project_id)
    blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
    if not blocks:
        return []
    entries = _load_forbidden_lexicon_entries(project_id, lexicon_asset_ids or None)
    if not entries:
        return []

    deadline = _time.monotonic() + 5
    hits: list[dict] = []
    for entry in entries:
        try:
            if entry["match_type"] == "regex":
                compiled = _re.compile(entry["pattern"])
            elif entry["match_type"] == "phrase":
                compiled = _re.compile(
                    _re.escape(entry["pattern"]).replace(r"\ ", r"\s+")
                )
            else:
                compiled = None
        except _re.error:
            continue
        for b in blocks:
            if _time.monotonic() > deadline:
                return hits
            content = b.get("content") or ""
            if compiled is None:
                start = 0
                p = entry["pattern"]
                while True:
                    idx = content.find(p, start)
                    if idx < 0:
                        break
                    hits.append(_format_hit(b, entry, idx, idx + len(p), p))
                    start = idx + max(len(p), 1)
            else:
                for m in compiled.finditer(content):
                    if _time.monotonic() > deadline:
                        return hits
                    hits.append(_format_hit(b, entry, m.start(), m.end(), m.group(0)))
    # Whitelist filter
    filtered = []
    for h in hits:
        wls = h.get("whitelist_contexts") or []
        if wls and any(wl for wl in wls if wl in (h.get("context") or "")):
            continue
        filtered.append(h)
    return filtered
