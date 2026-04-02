"""多 Agent 协同编排器 — 编排上下文收集、记忆收集、风格分析、正文创作、一致性审校的全流程。

支持 writer ↔ reviewer 打回重试循环：最多 MAX_REVISION_ROUNDS 次修订。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Optional

from .context_agent import ContextAgent
from .memory_agent import MemoryAgent
from .reviewer_agent import ReviewerAgent
from .style_agent import StyleAgent
from .writer_agent import WriterAgent

logger = logging.getLogger(__name__)

# 最大修订轮数（即最多生成 MAX_REVISION_ROUNDS + 1 稿）
MAX_REVISION_ROUNDS = 2


def _load_custom_reviewer_rules(project_id: str) -> str:
    """尝试加载项目的自定义审校规则，不存在则返回空字符串。"""
    if not project_id:
        return ""
    try:
        from ...models.project import ProjectManager
        data = ProjectManager.load_project_json(project_id, "reviewer_rules.json")
        return (data or {}).get("custom_prompt", "")
    except Exception:
        return ""


class NovelDraftOrchestrator:
    """编排多 Agent 协同生成正文的全流程，yield SSE 事件字典。"""

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
        """
        多 Agent 协同生成正文的完整流程。

        Args:
            payload: 前端传入的请求体，包含:
                - project_id: 项目 ID
                - scope_type: project_chapter | worldline_branch
                - chapter_id / chapter_order: 章节定位（project_chapter 模式）
                - session_id / branch_id: 世界线定位（worldline_branch 模式）
                - pov_character: POV 角色
                - author_instruction: 创作者的自由输入指令
                - writing_goal: 写作目标（可选）
                - scene_focus: 场景焦点（可选）
                - auto_continuity: 是否自动注入前章连续性（可选，默认 true）
                - revision_context: 修订上下文（可选），包含 previous_text 和 revision_instruction

        Yields:
            SSE 事件字典，type 字段标识事件类型。
        """
        author_instruction = str(payload.get("author_instruction", "")).strip()
        if not author_instruction:
            yield {"type": "error", "message": "请输入创作指令"}
            return

        # 加载自定义审校规则（如有）
        project_id = payload.get("project_id", "")
        custom_rules = _load_custom_reviewer_rules(project_id)
        if custom_rules and self.reviewer_agent.system_prompt != custom_rules:
            self.reviewer_agent = ReviewerAgent(custom_rules=custom_rules)

        start_time = time.time()
        revision_context = payload.get("revision_context")

        # ─── Phase 1: 收集上下文 ───
        yield self._sse("agent_status", agent="context_agent", status="running",
                        message="正在分析本章需求...")
        try:
            context_pack = self.context_agent.collect(payload)
            context_summary = self.context_agent.summarize(context_pack)
            continuity_msg = "，已注入前章连续性" if context_summary.get("has_continuity") else ""
            yield self._sse("agent_status", agent="context_agent", status="done",
                           message=f"上下文准备完成{continuity_msg}",
                           detail={"memory_count": context_summary["must_know_count"],
                                   "has_continuity": context_summary.get("has_continuity", False),
                                   "must_know_items": [
                                       item.get("summary", "")
                                       for item in context_pack.get("must_know", [])[:5]
                                   ],
                                   "should_know_count": len(context_pack.get("should_know", [])),
                                   "warnings": [
                                       item.get("summary", "")
                                       for item in context_pack.get("warnings", [])[:4]
                                   ]})
        except ValueError as exc:
            yield self._sse("agent_status", agent="context_agent", status="error",
                           message=f"上下文收集失败: {exc}")
            return

        # ─── Phase 1b: 收集角色记忆 ───
        yield self._sse("agent_status", agent="memory_agent", status="running",
                        message="正在从世界线检索相关记忆...")
        try:
            memory_bundle = self.memory_agent.collect(
                project_id=payload.get("project_id", ""),
                pov_character=payload.get("pov_character", ""),
                scope_type=payload.get("scope_type", "project_chapter"),
                session_id=payload.get("session_id", ""),
                branch_id=payload.get("branch_id", "main"),
            )
            n_memories = len(memory_bundle.get("memories", []))
            memory_msg = f"检索到 {n_memories} 条相关记忆" if n_memories > 0 else "未找到运行时记忆，将使用角色档案信息"
            yield self._sse("agent_status", agent="memory_agent", status="done",
                           message=memory_msg,
                           detail={"memories": [
                               {"summary": m.get("summary", "")}
                               for m in memory_bundle.get("memories", [])[:5]
                           ]})
        except Exception as exc:
            logger.warning("MemoryAgent 失败，使用空记忆继续: %s", exc)
            memory_bundle = {"character_profile": {}, "memories": [], "relationships": [], "rendered_context": ""}
            yield self._sse("agent_status", agent="memory_agent", status="done",
                           message="记忆收集跳过（无可用记忆）")

        # ─── Phase 1c: 分析文风 ───
        yield self._sse("agent_status", agent="style_agent", status="running",
                        message="正在分析前文风格与节奏...")
        try:
            style_hints = self.style_agent.analyze(
                project_id=payload.get("project_id", ""),
                chapter_id=payload.get("chapter_id", ""),
            )
            yield self._sse("agent_status", agent="style_agent", status="done",
                           message="风格识别完成",
                           detail={"pov": style_hints.get("pov_person", "第三人称"),
                                   "pace": style_hints.get("rhythm", "均匀适中"),
                                   "tone": "中性",
                                   "rendered_hints": style_hints.get("rendered_hints", "")})
        except Exception as exc:
            logger.warning("StyleAgent 失败，使用默认风格: %s", exc)
            style_hints = StyleAgent()._default_hints()
            yield self._sse("agent_status", agent="style_agent", status="done",
                           message="使用默认风格")

        # ─── 上下文就绪 ───
        yield {
            "type": "context_ready",
            "summary": context_summary,
            "context_pack": context_pack,
        }

        # ─── Phase 2: 生成正文（单轮） ───
        full_text = ""

        yield self._sse("agent_status", agent="writer_agent", status="running",
                       message="正在生成正文...")

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
            yield self._sse("agent_status", agent="writer_agent", status="error",
                           message=f"正文生成失败: {exc}")
            return
        except Exception as exc:
            logger.error("WriterAgent 流式生成异常: %s", exc, exc_info=True)
            yield self._sse("agent_status", agent="writer_agent", status="error",
                           message=f"正文生成异常: {exc}")
            return

        yield self._sse("agent_status", agent="writer_agent", status="done",
                       message=f"正文完成：{len(full_text)} 字")

        # ─── Phase 3: 审校（单轮） ───
        yield self._sse("agent_status", agent="reviewer_agent", status="running",
                       message="正在检查连续性与一致性...")

        try:
            review_result = self.reviewer_agent.review(full_text, context_pack, memory_bundle)
        except Exception as exc:
            logger.warning("ReviewerAgent 失败: %s", exc)
            review_result = {
                "pass": True,
                "score": 0,
                "issues": [],
                "keep": [],
                "overall_assessment": "审校跳过",
                "review_mode": "skipped",
            }

        issues = review_result.get("issues", [])
        n_issues = len(issues)
        if review_result.get("pass", True):
            yield self._sse("agent_status", agent="reviewer_agent", status="done",
                           message=f"审核通过（评分 {review_result.get('score', 0)}）",
                           detail={"pass": True, "score": review_result.get("score", 0)})
        else:
            yield self._sse("agent_status", agent="reviewer_agent", status="done",
                           message=f"发现 {n_issues} 个问题，等待用户操作",
                           detail={"pass": False, "score": review_result.get("score", 0),
                                   "issues": issues})

        # ─── 完成 ───
        elapsed = round(time.time() - start_time, 1)
        yield {
            "type": "done",
            "data": {
                "final_draft": full_text,
                "revision_count": 0,
                "unresolved_issues": issues if not review_result.get("pass", True) else [],
            },
            "full_text": full_text,
            "char_count": len(full_text),
            "review": review_result,
            "context_summary": context_summary,
            "model_name": self.writer_agent.model_name,
            "elapsed_seconds": elapsed,
            "revision_count": 0,
        }

    def revise_stream(self, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """
        用户驱动的修订流程：重写正文 + 重新审校。

        Args:
            payload: 包含:
                - project_id: 项目 ID
                - previous_text: 上一版正文（可能已被用户编辑）
                - revision_instruction: 修订指令（从审校报告构造或用户自定义）
                - author_instruction: 可选的额外用户指令
                - context_pack_snapshot: 上下文快照（从首次生成时保存）
                - memory_bundle_snapshot: 记忆快照
                - style_hints_snapshot: 风格快照

        Yields:
            SSE 事件字典。
        """
        start_time = time.time()
        previous_text = payload.get("previous_text", "")
        revision_instruction = payload.get("revision_instruction", "")
        author_instruction = payload.get("author_instruction", "")

        if not previous_text:
            yield {"type": "error", "message": "缺少上一版正文"}
            return

        # 加载自定义审校规则
        project_id = payload.get("project_id", "")
        custom_rules = _load_custom_reviewer_rules(project_id)
        if custom_rules:
            self.reviewer_agent = ReviewerAgent(custom_rules=custom_rules)

        context_pack = payload.get("context_pack_snapshot", {})
        memory_bundle = payload.get("memory_bundle_snapshot", {})
        style_hints = payload.get("style_hints_snapshot", {})

        revision_context = {
            "previous_text": previous_text,
            "revision_instruction": revision_instruction or "请优化正文",
        }

        # ─── 通知前端清空文本 ───
        yield {"type": "text_clear"}

        # ─── 重写正文 ───
        yield self._sse("agent_status", agent="writer_agent", status="running",
                       message="正在修订正文...")

        full_text = ""
        combined_instruction = author_instruction or "根据修订意见改写"

        try:
            for chunk in self.writer_agent.generate_stream(
                author_instruction=combined_instruction,
                context_pack=context_pack,
                memory_bundle=memory_bundle,
                style_hints=style_hints,
                revision_context=revision_context,
            ):
                full_text += chunk
                yield {"type": "text_chunk", "data": {"chunk": chunk}}
        except Exception as exc:
            logger.error("WriterAgent 修订异常: %s", exc, exc_info=True)
            yield self._sse("agent_status", agent="writer_agent", status="error",
                           message=f"修订失败: {exc}")
            return

        yield self._sse("agent_status", agent="writer_agent", status="done",
                       message=f"修订完成：{len(full_text)} 字")

        # ─── 重新审校 ───
        yield self._sse("agent_status", agent="reviewer_agent", status="running",
                       message="正在重新审校...")

        try:
            review_result = self.reviewer_agent.review(full_text, context_pack, memory_bundle)
        except Exception as exc:
            logger.warning("ReviewerAgent 修订审校失败: %s", exc)
            review_result = {
                "pass": True,
                "score": 0,
                "issues": [],
                "keep": [],
                "overall_assessment": "审校跳过",
                "review_mode": "skipped",
            }

        issues = review_result.get("issues", [])
        n_issues = len(issues)
        if review_result.get("pass", True):
            yield self._sse("agent_status", agent="reviewer_agent", status="done",
                           message=f"审核通过（评分 {review_result.get('score', 0)}）",
                           detail={"pass": True, "score": review_result.get("score", 0)})
        else:
            yield self._sse("agent_status", agent="reviewer_agent", status="done",
                           message=f"发现 {n_issues} 个问题，等待用户操作",
                           detail={"pass": False, "score": review_result.get("score", 0),
                                   "issues": issues})

        elapsed = round(time.time() - start_time, 1)
        yield {
            "type": "done",
            "data": {
                "final_draft": full_text,
                "revision_count": 1,
                "unresolved_issues": issues if not review_result.get("pass", True) else [],
            },
            "full_text": full_text,
            "char_count": len(full_text),
            "review": review_result,
            "model_name": self.writer_agent.model_name,
            "elapsed_seconds": elapsed,
            "revision_count": 1,
        }

    def _sse(
        self,
        event_type: str,
        agent: str = "",
        status: str = "",
        message: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构造标准 SSE 事件字典。"""
        event: Dict[str, Any] = {"type": event_type}
        if agent:
            event["agent"] = agent
        if status:
            event["status"] = status
        if message:
            event["message"] = message
        if detail is not None:
            event["detail"] = detail
        return event
