"""多 Agent 协同编排器。"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Optional

from .context_agent import ContextAgent
from .memory_agent import MemoryAgent
from .orchestration_support import (
    context_status_detail,
    done_event,
    empty_memory_bundle,
    load_custom_reviewer_rules,
    memory_status_detail,
    skipped_review_result,
    sse_event,
    style_status_detail,
)
from .reviewer_agent import ReviewerAgent
from .style_agent import StyleAgent
from .writer_agent import WriterAgent

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2


class NovelDraftOrchestrator:
    """编排多 Agent 协同生成正文的全流程。"""

    def __init__(
        self,
        context_agent: Optional[ContextAgent] = None,
        memory_agent: Optional[MemoryAgent] = None,
        style_agent: Optional[StyleAgent] = None,
        writer_agent: Optional[WriterAgent] = None,
        reviewer_agent: Optional[ReviewerAgent] = None,
    ):
        self.context_agent = context_agent or ContextAgent()
        self.memory_agent = memory_agent or MemoryAgent()
        self.style_agent = style_agent or StyleAgent()
        self.writer_agent = writer_agent or WriterAgent()
        self.reviewer_agent = reviewer_agent or ReviewerAgent()

    def generate_stream(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        author_instruction = str(payload.get("author_instruction", "")).strip()
        if not author_instruction:
            yield {"type": "error", "message": "请输入创作指令"}
            return
        self._configure_reviewer(payload.get("project_id", ""))
        start_time = time.time()
        revision_context = payload.get("revision_context")
        context_pack, context_summary = yield from self._context_stage(payload)
        if not context_pack:
            return
        memory_bundle = yield from self._memory_stage(payload)
        style_hints = yield from self._style_stage(payload)
        yield {"type": "context_ready", "summary": context_summary, "context_pack": context_pack}
        full_text = yield from self._writer_stage(
            author_instruction,
            context_pack,
            memory_bundle,
            style_hints,
            revision_context,
            "正在生成正文...",
            "正文完成",
            "正文生成失败",
        )
        if full_text is None:
            return
        review_result = yield from self._review_stage(full_text, context_pack, memory_bundle, "正在检查连续性与一致性...")
        elapsed = round(time.time() - start_time, 1)
        yield done_event(
            full_text=full_text,
            review_result=review_result,
            revision_count=0,
            model_name=self.writer_agent.model_name,
            elapsed_seconds=elapsed,
            context_summary=context_summary,
        )

    def revise_stream(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        previous_text = payload.get("previous_text", "")
        if not previous_text:
            yield {"type": "error", "message": "缺少上一版正文"}
            return
        self._configure_reviewer(payload.get("project_id", ""))
        start_time = time.time()
        revision_context = {
            "previous_text": previous_text,
            "revision_instruction": payload.get("revision_instruction", "") or "请优化正文",
        }
        yield {"type": "text_clear"}
        full_text = yield from self._writer_stage(
            payload.get("author_instruction", "") or "根据修订意见改写",
            payload.get("context_pack_snapshot", {}),
            payload.get("memory_bundle_snapshot", {}),
            payload.get("style_hints_snapshot", {}),
            revision_context,
            "正在修订正文...",
            "修订完成",
            "修订失败",
        )
        if full_text is None:
            return
        review_result = yield from self._review_stage(
            full_text,
            payload.get("context_pack_snapshot", {}),
            payload.get("memory_bundle_snapshot", {}),
            "正在重新审校...",
        )
        elapsed = round(time.time() - start_time, 1)
        yield done_event(
            full_text=full_text,
            review_result=review_result,
            revision_count=1,
            model_name=self.writer_agent.model_name,
            elapsed_seconds=elapsed,
        )

    def _configure_reviewer(self, project_id: str) -> None:
        custom_rules = load_custom_reviewer_rules(project_id)
        if custom_rules and self.reviewer_agent.system_prompt != custom_rules:
            self.reviewer_agent = ReviewerAgent(custom_rules=custom_rules)

    def _context_stage(
        self,
        payload: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, tuple[Dict[str, Any], Dict[str, Any]]]:
        yield sse_event("agent_status", "context_agent", "running", "正在分析本章需求...")
        try:
            context_pack = self.context_agent.collect(payload)
            context_summary = self.context_agent.summarize(context_pack)
        except ValueError as exc:
            yield sse_event("agent_status", "context_agent", "error", f"上下文收集失败: {exc}")
            return {}, {}
        continuity_msg = "，已注入前章连续性" if context_summary.get("has_continuity") else ""
        yield sse_event(
            "agent_status",
            "context_agent",
            "done",
            f"上下文准备完成{continuity_msg}",
            context_status_detail(context_summary, context_pack),
        )
        return context_pack, context_summary

    def _memory_stage(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        yield sse_event("agent_status", "memory_agent", "running", "正在从世界线检索相关记忆...")
        try:
            memory_bundle = self.memory_agent.collect(
                project_id=payload.get("project_id", ""),
                pov_character=payload.get("pov_character", ""),
                scope_type=payload.get("scope_type", "project_chapter"),
                session_id=payload.get("session_id", ""),
                branch_id=payload.get("branch_id", "main"),
            )
        except Exception as exc:
            logger.warning("MemoryAgent 失败，使用空记忆继续: %s", exc)
            yield sse_event("agent_status", "memory_agent", "done", "记忆收集跳过（无可用记忆）")
            return empty_memory_bundle()
        memory_count = len(memory_bundle.get("memories", []))
        message = (
            f"检索到 {memory_count} 条相关记忆"
            if memory_count > 0
            else "未找到运行时记忆，将使用角色档案信息"
        )
        yield sse_event(
            "agent_status",
            "memory_agent",
            "done",
            message,
            memory_status_detail(memory_bundle),
        )
        return memory_bundle

    def _style_stage(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        yield sse_event("agent_status", "style_agent", "running", "正在分析前文风格与节奏...")
        try:
            style_hints = self.style_agent.analyze(
                project_id=payload.get("project_id", ""),
                chapter_id=payload.get("chapter_id", ""),
            )
        except Exception as exc:
            logger.warning("StyleAgent 失败，使用默认风格: %s", exc)
            style_hints = StyleAgent()._default_hints()
            yield sse_event("agent_status", "style_agent", "done", "使用默认风格")
            return style_hints
        yield sse_event(
            "agent_status",
            "style_agent",
            "done",
            "风格识别完成",
            style_status_detail(style_hints),
        )
        return style_hints

    def _writer_stage(
        self,
        author_instruction: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
        style_hints: Dict[str, Any],
        revision_context: Optional[Dict[str, Any]],
        start_message: str,
        done_label: str,
        error_label: str,
    ) -> Generator[Dict[str, Any], None, Optional[str]]:
        yield sse_event("agent_status", "writer_agent", "running", start_message)
        full_text = ""
        try:
            for chunk in self.writer_agent.generate_stream(
                author_instruction=author_instruction,
                context_pack=context_pack,
                memory_bundle=memory_bundle,
                style_hints=style_hints,
                revision_context=revision_context,
            ):
                full_text += chunk
                yield {"type": "text_chunk", "data": {"chunk": chunk}}
        except ValueError as exc:
            yield sse_event("agent_status", "writer_agent", "error", f"{error_label}: {exc}")
            return None
        except Exception as exc:
            logger.error("WriterAgent 流式生成异常: %s", exc, exc_info=True)
            yield sse_event("agent_status", "writer_agent", "error", f"{error_label}: {exc}")
            return None
        yield sse_event(
            "agent_status",
            "writer_agent",
            "done",
            f"{done_label}：{len(full_text)} 字",
        )
        return full_text

    def _review_stage(
        self,
        full_text: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
        start_message: str,
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        yield sse_event("agent_status", "reviewer_agent", "running", start_message)
        try:
            review_result = self.reviewer_agent.review(full_text, context_pack, memory_bundle)
        except Exception as exc:
            logger.warning("ReviewerAgent 失败: %s", exc)
            review_result = skipped_review_result()
        issues = review_result.get("issues", [])
        if review_result.get("pass", True):
            yield sse_event(
                "agent_status",
                "reviewer_agent",
                "done",
                f"审核通过（评分 {review_result.get('score', 0)}）",
                {"pass": True, "score": review_result.get("score", 0)},
            )
            return review_result
        yield sse_event(
            "agent_status",
            "reviewer_agent",
            "done",
            f"发现 {len(issues)} 个问题，等待用户操作",
            {"pass": False, "score": review_result.get("score", 0), "issues": issues},
        )
        return review_result
