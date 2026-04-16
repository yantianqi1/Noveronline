"""资产入库 Agent runner。

调用全局 LLM 模块 ``asset_ingestion`` 完成「类型识别 + 结构化抽取 + 摘要分类」，
并把结果写入 ``AssetsService``。失败显式抛错，绝不静默 fallback。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ....models.task import TaskManager, TaskStatus
from ...llm_router import LlmRouter
from ..assets_service import AssetsService, GLOBAL_SCOPE, PROJECT_SCOPE
from .prompts import SUPPORTED_TYPES, build_ingest_messages

logger = logging.getLogger(__name__)


class IngestionAgent:
    """单次入库流程：raw_text -> LLM -> AssetsService.create()"""

    TASK_TYPE = "asset_ingestion"
    MODULE_KEY = "asset_ingestion"

    def __init__(
        self,
        *,
        assets_service: AssetsService | None = None,
        llm_router: LlmRouter | None = None,
    ) -> None:
        self.assets = assets_service or AssetsService()
        self.llm_router = llm_router or LlmRouter()

    # ------------------------------------------------------------------
    def run_sync(
        self,
        raw_text: str,
        *,
        scope: str = GLOBAL_SCOPE,
        project_id: str | None = None,
        hint_type: str | None = None,
    ) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("raw_text 不能为空")
        if scope == PROJECT_SCOPE and not project_id:
            raise ValueError("project scope 必须提供 project_id")
        if hint_type and hint_type not in SUPPORTED_TYPES:
            raise ValueError(
                f"hint_type 非法: {hint_type}; 必须是 {SUPPORTED_TYPES}"
            )

        client = self.llm_router.build_client(self.MODULE_KEY)
        payload = client.chat_json(
            build_ingest_messages(text, hint_type=hint_type),
            temperature=0.2,
            max_tokens=2048,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"asset_ingestion LLM 返回非对象: {type(payload).__name__}"
            )

        asset_type = payload.get("asset_type") or hint_type
        if asset_type not in SUPPORTED_TYPES:
            raise RuntimeError(
                f"LLM 返回的 asset_type 非法: {asset_type!r}"
            )
        title = (payload.get("title") or "").strip()
        if not title:
            raise RuntimeError("LLM 未返回 title")

        asset = self.assets.create(
            scope=scope,
            asset_type=asset_type,
            title=title,
            project_id=project_id if scope == PROJECT_SCOPE else None,
            category=payload.get("category") or "",
            summary=payload.get("summary") or "",
            content=text,  # 保留原文，便于 detail 抽屉展示
            payload=payload.get("payload") or {},
            tags=payload.get("tags") or [],
            source_kind="ingestion_agent",
            source_ref=f"chars={len(text)}",
        )
        return {"asset": asset, "raw_payload": payload}

    # ------------------------------------------------------------------
    async def run_background(
        self,
        raw_text: str,
        *,
        scope: str = GLOBAL_SCOPE,
        project_id: str | None = None,
        hint_type: str | None = None,
    ) -> str:
        tm = TaskManager()
        task_id = await tm.create_task(
            self.TASK_TYPE,
            metadata={
                "scope": scope,
                "project_id": project_id,
                "hint_type": hint_type,
                "input_chars": len(raw_text or ""),
            },
        )
        await tm.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress=10,
            message="入库 Agent 开始解析素材...",
        )

        async def _run() -> None:
            try:
                await tm.update_task(task_id, progress=40, message="调用 LLM 抽取字段...")
                result = self.run_sync(
                    raw_text,
                    scope=scope,
                    project_id=project_id,
                    hint_type=hint_type,
                )
                await tm.update_task(task_id, progress=90, message="写入资产库...")
                await tm.complete_task(
                    task_id,
                    {
                        "asset_id": result["asset"]["asset_id"],
                        "title": result["asset"]["title"],
                        "asset_type": result["asset"]["asset_type"],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("ingestion agent failed")
                await tm.fail_task(task_id, str(exc))

        asyncio.create_task(_run())
        return task_id
