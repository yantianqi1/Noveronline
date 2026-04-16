"""文风提取后台 runner。

并行调用 ``style_extractor`` LLM 模块对每个块抽取风格特征，再聚合成
``writing_style`` 资产入库。任务进度通过 ``TaskManager`` 暴露。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ....models.task import TaskManager, TaskStatus
from ....services.llm_router import LlmRouter
from ..assets_service import AssetsService, GLOBAL_SCOPE
from .aggregator import aggregate_chunk_results, render_style_content
from .chunk_style_prompt import build_chunk_messages
from .chunker import chunk_novel

logger = logging.getLogger(__name__)


class StyleExtractor:
    """Synchronous + background runner for novel-wide style extraction."""

    TASK_TYPE = "style_extract"

    def __init__(
        self,
        *,
        assets_service: AssetsService | None = None,
        llm_router: LlmRouter | None = None,
        max_workers: int = 6,
    ) -> None:
        self.assets = assets_service or AssetsService()
        self.llm_router = llm_router or LlmRouter()
        self.max_workers = max_workers

    # ------------------------------------------------------------------

    async def extract_sync(
        self,
        text: str,
        *,
        title: str,
        category: str = "",
        tags: list[str] | None = None,
        target_chunk_chars: int = 3000,
        max_chunks: int = 30,
        on_progress=None,
    ) -> dict[str, Any]:
        chunks = chunk_novel(text, target_chars=target_chunk_chars, max_chunks=max_chunks)
        if not chunks:
            raise ValueError("待提取的文本为空")

        client = self.llm_router.build_client("style_extractor")
        results: list[dict] = [None] * len(chunks)  # type: ignore

        def _process_sync(idx: int, chunk: str) -> tuple[int, dict | None, str | None]:
            try:
                payload = client.chat_json(
                    build_chunk_messages(chunk),
                    temperature=0.2,
                    max_tokens=1024,
                )
                return idx, (payload if isinstance(payload, dict) else None), None
            except Exception as exc:  # surface error per chunk; aggregator skips Nones
                logger.warning("style extractor chunk %d failed: %s", idx, exc)
                return idx, None, str(exc)

        sem = asyncio.Semaphore(self.max_workers)

        async def _bounded(idx: int, chunk: str) -> tuple[int, dict | None, str | None]:
            async with sem:
                return await asyncio.to_thread(_process_sync, idx, chunk)

        completed = 0
        errors: list[str] = []
        tasks = [_bounded(i, c) for i, c in enumerate(chunks)]
        for coro in asyncio.as_completed(tasks):
            idx, payload, err = await coro
            if payload:
                results[idx] = payload
            if err:
                errors.append(f"#{idx}: {err}")
            completed += 1
            if on_progress:
                on_progress(completed, len(chunks))

        good = [r for r in results if isinstance(r, dict)]
        if not good:
            raise RuntimeError(
                "所有分块都未返回有效结果；请检查 style_extractor LLM 模块绑定。"
                + ("\n首条错误：" + errors[0] if errors else "")
            )

        aggregated = aggregate_chunk_results(good)
        content = render_style_content(aggregated)

        asset = self.assets.create(
            scope=GLOBAL_SCOPE,
            asset_type="writing_style",
            title=title,
            category=category,
            summary=aggregated.get("tone") or aggregated.get("narrative_pov") or "",
            content=content,
            payload=aggregated,
            tags=tags or [],
            source_kind="extract_agent",
            source_ref=f"chunks={len(chunks)}",
        )
        return {
            "asset": asset,
            "chunk_count": len(chunks),
            "successful_chunks": len(good),
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def extract_background(
        self,
        text: str,
        *,
        title: str,
        category: str = "",
        tags: list[str] | None = None,
        target_chunk_chars: int = 3000,
        max_chunks: int = 30,
    ) -> str:
        """Spawn a background task, return task_id immediately."""
        tm = TaskManager()
        task_id = await tm.create_task(
            self.TASK_TYPE,
            metadata={"title": title, "category": category, "input_chars": len(text or "")},
        )
        await tm.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="启动文风提取任务...")

        async def _run():
            try:
                async def _on_progress(done: int, total: int) -> None:
                    pct = int(done * 100 / max(total, 1))
                    await tm.update_task(
                        task_id,
                        progress=pct,
                        message=f"已完成 {done}/{total} 块",
                    )

                result = await self.extract_sync(
                    text,
                    title=title,
                    category=category,
                    tags=tags,
                    target_chunk_chars=target_chunk_chars,
                    max_chunks=max_chunks,
                    on_progress=lambda done, total: asyncio.ensure_future(_on_progress(done, total)),
                )
                await tm.complete_task(task_id, {
                    "asset_id": result["asset"]["asset_id"],
                    "title": result["asset"]["title"],
                    "chunk_count": result["chunk_count"],
                    "successful_chunks": result["successful_chunks"],
                    "errors": result["errors"],
                })
            except Exception as exc:
                logger.exception("style extraction task failed")
                await tm.fail_task(task_id, str(exc))

        asyncio.create_task(_run())
        return task_id


async def run_style_extraction(text: str, *, title: str, **kwargs) -> str:
    """Convenience: spawn a background extraction and return the task id."""
    return await StyleExtractor().extract_background(text, title=title, **kwargs)
