"""上下文收集 Agent — 封装 ChapterContextPackBuilder + 前章连续性注入。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ...chapter_context_pack_builder import ChapterContextPackBuilder
from ...chapter_meta_service import ChapterMetaService

logger = logging.getLogger(__name__)


class ContextAgent:
    """根据创作者选择的范围，自动组装 Chapter Context Pack，并注入前章连续性上下文。"""

    def __init__(
        self,
        builder: Optional[ChapterContextPackBuilder] = None,
        chapter_meta_service: Optional[ChapterMetaService] = None,
    ):
        self.builder = builder or ChapterContextPackBuilder()
        self.chapter_meta_service = chapter_meta_service or ChapterMetaService()

    def collect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        收集上下文包。

        Args:
            payload: 与 ChapterContextPackBuilder.build() 相同的参数字典，
                     包含 scope_type, project_id, chapter_id/session_id,
                     pov_character, writing_goal, scene_focus 等。
                     新增 auto_continuity (bool, 默认 true)。

        Returns:
            完整的 context pack 字典，含 continuity_anchor（如可用）。
        """
        try:
            pack = self.builder.build(payload)
            logger.info(
                "ContextAgent: 收集完成 — must_know=%d, should_know=%d, warnings=%d, scenes=%d",
                len(pack.get("must_know", [])),
                len(pack.get("should_know", [])),
                len(pack.get("warnings", [])),
                len(pack.get("scene_candidates", [])),
            )

            # 前章连续性注入
            auto_continuity = payload.get("auto_continuity", True)
            if auto_continuity:
                continuity = self._build_continuity(payload)
                if continuity:
                    pack["continuity_anchor"] = continuity["continuity_anchor"]
                    logger.info(
                        "ContextAgent: 连续性注入完成 — summaries=%d, threads=%d",
                        len(pack["continuity_anchor"].get("chapter_summaries", [])),
                        len(pack["continuity_anchor"].get("open_threads", [])),
                    )

            return pack
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("ContextAgent: 收集上下文时发生错误 — %s", exc)
            raise ValueError(f"收集上下文失败: {exc}") from exc

    def summarize(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        """返回上下文包的轻量摘要，用于前端状态指示。"""
        has_continuity = "continuity_anchor" in pack and bool(
            pack["continuity_anchor"].get("chapter_summaries")
            or pack["continuity_anchor"].get("prev_chapter_ending")
        )
        return {
            "must_know_count": len(pack.get("must_know", [])),
            "should_know_count": len(pack.get("should_know", [])),
            "warnings_count": len(pack.get("warnings", [])),
            "scene_count": len(pack.get("scene_candidates", [])),
            "scope_type": pack.get("context_scope", {}).get("scope_type", ""),
            "pov_character": pack.get("context_scope", {}).get("pov_character", ""),
            "has_continuity": has_continuity,
        }

    def _build_continuity(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """尝试构建前章连续性上下文。"""
        project_id = payload.get("project_id", "")
        if not project_id:
            return None

        # 确定当前章节索引
        chapter_order = payload.get("chapter_order", 0)
        if not chapter_order:
            # 尝试从 chapter_id 推断
            chapter_order = self._resolve_chapter_order(payload)

        if chapter_order is None or chapter_order <= 0:
            return None

        try:
            return self.chapter_meta_service.get_chapter_continuity_context(
                project_id, chapter_order
            )
        except Exception as exc:
            logger.warning("ContextAgent: 连续性上下文构建失败 — %s", exc)
            return None

    def _resolve_chapter_order(self, payload: Dict[str, Any]) -> Optional[int]:
        """从 payload 中的 chapter_id 解析出章节序号。"""
        chapter_id = payload.get("chapter_id", "")
        if not chapter_id:
            return None

        project_id = payload.get("project_id", "")
        if not project_id:
            return None

        try:
            from ....models.project import ProjectManager
            segments = ProjectManager.load_project_json(project_id, "chapter_segments.json")
            if not segments:
                return None
            for chapter in segments.get("chapters", []):
                if chapter.get("chapter_id") == chapter_id:
                    return chapter.get("order", 0)
        except Exception:
            pass
        return None
