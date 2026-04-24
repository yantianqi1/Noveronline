"""Dual-layer writer orchestrator: orchestrator agent + writer agent."""

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Dict, Optional

from .agent_loop import AgentLoop
from .dedup_extractor import DedupExtractor
from .prompts import build_orchestrator_prompt
from .retrieval_planner import RetrievalPlanner
from .reviewer import WriterReviewer
from .tools import NOVEL_TOOLS, MANUSCRIPT_TOOLS, ASSET_TOOLS, UNIFIED_TOOLS
from .writer import WriterComposer
from .post_processor import PostProcessor

from ...database import get_engine
from ...repositories.chapter_repo import ChapterRepository
from ...repositories.dedup_index_repo import DedupIndexRepository
from ...repositories.preset_repo import PresetRepository

logger = logging.getLogger(__name__)


class WriterOrchestrator:
    """
    Full pipeline:
    1. Build orchestrator prompt from request
    2. Run AgentLoop (cheap model + tools) -> yield orchestrator_status events
    3. Parse writing_brief from agent output
    4. Load preset prompt from DB
    5. Run WriterComposer (strongest model) -> yield writer_token events
    6. Run PostProcessor -> yield done event
    """

    def __init__(self, llm_router=None):
        from ...services.llm_router import LlmRouter
        self.router = llm_router or LlmRouter()

    async def run(self, request: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute the full writing pipeline.

        request keys:
            project_id (required)
            task_type: write_scene|continue|outline
            chapter_id, chapter_order, scene_order
            pov_entity_id, involved_entity_ids
            scene_focus, user_instruction
            preset_id
            selected_text (for rewrite/expand)
            session_id (for worldline context)
        """
        project_id = request.get("project_id")
        if not project_id:
            yield {"type": "error", "message": "缺少 project_id"}
            return

        t0 = time.monotonic()

        def _stamp():
            return {
                "ts": time.strftime("%H:%M:%S"),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

        task_type = request.get("task_type", "write_scene")
        chapter_id = request.get("chapter_id", "")
        scene_order = request.get("scene_order", 1)

        # Repositories for novel data access
        engine = get_engine()
        chapter_repo = ChapterRepository(engine)
        preset_repo = PresetRepository(engine)

        # --- Phase 1: Orchestrator Agent ---

        # Build orchestrator context from request
        context = {
            "project_id": project_id,
            "chapter_id": chapter_id,
            "chapter_order": request.get("chapter_order", 0),
            "pov_character": request.get("pov_entity_id", ""),
            "involved_entities": ", ".join(request.get("involved_entity_ids", [])),
            "scene_focus": request.get("scene_focus", ""),
            "user_instruction": request.get("user_instruction", ""),
            "selected_text": request.get("selected_text", ""),
            "session_id": request.get("session_id", ""),
            "last_block_id": request.get("last_block_id", ""),
        }

        system_prompt = build_orchestrator_prompt(task_type, context)
        try:
            orchestrator_client = await self.router.build_async_client("writer_orchestrator")
        except ValueError as exc:
            yield {"type": "error", **_stamp(), "message": f"LLM 模块未绑定 (writer_orchestrator): {exc}"}
            return

        orchestrator_model = orchestrator_client.model
        yield {"type": "orchestrator_status", "phase": "starting", **_stamp(), "message": "编排层启动中...", "model": orchestrator_model}

        # --- Data health self-check ---
        # Surface missing narrative / graph data before the agent even starts
        # so the author knows why the writer might underperform (seed pipeline
        # not run, graph build pending, etc.). This is purely informational —
        # the run continues regardless.
        try:
            health_issues = await asyncio.to_thread(_collect_data_health_issues, project_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("data health check failed: %s", exc, exc_info=True)
            health_issues = []
        if health_issues:
            yield {
                "type": "data_health_warning",
                **_stamp(),
                "issues": health_issues,
                "message": "本项目的部分设定数据缺失，写作 Agent 的上下文可能不完整。",
            }

        # --- Phase 0: Retrieval Planner ---
        # 让一个轻量 LLM 先想清楚『正式写作前必须先调用哪些工具』，输出 JSON 计划，
        # 注入 user message 顶端作为最低检索基线。失败降级为空计划 + warning 事件，
        # AgentLoop 继续走启发式规则，不让请求硬死。
        retrieval_plan_text = ""
        try:
            yield {
                "type": "orchestrator_status",
                "phase": "retrieval_planning",
                **_stamp(),
                "message": "检索规划员分析中...",
            }
            planner = RetrievalPlanner(self.router)
            plan_dict = await asyncio.to_thread(planner.plan, task_type, context)
            retrieval_plan_text = RetrievalPlanner.render_for_user_message(plan_dict)
            if plan_dict.get("degraded"):
                yield {
                    "type": "orchestrator_status",
                    "phase": "retrieval_planning_degraded",
                    **_stamp(),
                    "message": (
                        "检索规划员降级：" + (plan_dict.get("error") or "未知原因")
                        + "。AgentLoop 将依靠 system prompt 启发式规则自主检索。"
                    ),
                }
            else:
                yield {
                    "type": "retrieval_plan",
                    **_stamp(),
                    "plan": plan_dict,
                }
        except Exception as exc:  # noqa: BLE001
            # 理论上 RetrievalPlanner.plan 不再抛错；保留这个兜底避免一旦内部
            # 有未预期的异常（例如 prompt 构造失败）让整个请求崩掉。
            logger.warning("retrieval planner unexpected failure: %s", exc, exc_info=True)
            yield {
                "type": "orchestrator_status",
                "phase": "retrieval_planning_degraded",
                **_stamp(),
                "message": f"检索规划员意外失败：{exc}。AgentLoop 将依靠启发式规则继续。",
            }
            retrieval_plan_text = ""

        # Asset tools always available; manuscript tools for continuation tasks.
        tools = NOVEL_TOOLS + ASSET_TOOLS + UNIFIED_TOOLS
        if task_type == "continue":
            tools = tools + MANUSCRIPT_TOOLS

        agent_loop = AgentLoop(
            llm_client=orchestrator_client,
            tools=tools,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )

        # Build the user message for the orchestrator
        user_msg = self._build_orchestrator_user_message(task_type, context)
        if retrieval_plan_text:
            user_msg = retrieval_plan_text + "\n\n" + user_msg

        # Run agent loop, forwarding events directly.
        # Dedup rationale: the agent sometimes re-issues the same tool call
        # (e.g. query_entity("陈迹") twice in the same round), which would
        # otherwise inject the identical result twice into the writer's
        # "### 参考资料" block. The tool_result event doesn't carry the input
        # args, so we fingerprint by (tool_name, first 256 chars of result) —
        # different args typically produce different result bodies, so this
        # key is both cheap and robust against false-positive dedup.
        brief_content = ""
        tool_count = 0
        tool_results_raw: list[dict] = []
        _seen_tool_fingerprints: set[str] = set()
        _tool_results_dropped = 0
        async for event in agent_loop.run(user_msg):
            if event["type"] == "brief_ready":
                brief_content = event.get("content", "")
            elif event["type"] in ("tool_call", "tool_result", "thinking", "prompt_snapshot"):
                if event["type"] == "tool_call":
                    tool_count += 1
                if event["type"] == "tool_result":
                    name = event.get("name", "")
                    result = event.get("full_result", event.get("summary", ""))
                    fingerprint = f"{name}::{(result or '')[:256]}"
                    if fingerprint in _seen_tool_fingerprints:
                        _tool_results_dropped += 1
                    else:
                        _seen_tool_fingerprints.add(fingerprint)
                        tool_results_raw.append({"tool": name, "result": result})
                yield event
            elif event["type"] == "error":
                yield event
                return
        if _tool_results_dropped:
            logger.info(
                "tool_results dedup: kept=%d, dropped=%d",
                len(tool_results_raw),
                _tool_results_dropped,
            )

        # Phase summary
        yield {
            "type": "phase_summary",
            **_stamp(),
            "phase": "collecting",
            "tool_count": tool_count,
            "message": f"收集完成：{tool_count}次工具调用，耗时{_stamp()['elapsed_ms'] / 1000:.1f}s",
            "token_usage": agent_loop.total_usage,
        }

        # Parse writing_brief
        writing_brief = self._parse_brief(brief_content, context)

        # Inject raw tool results directly -- bypasses LLM summarization loss
        if tool_results_raw:
            writing_brief["_tool_results"] = tool_results_raw

        logger.info(
            "writing_brief parsed: keys=%s, raw_len=%d, tool_results=%d",
            list(writing_brief.keys()),
            len(brief_content),
            len(tool_results_raw),
        )

        # Force-inject chapter outline into writing_brief so the writer
        # composer always has it, regardless of orchestrator tool calls.
        if chapter_id and task_type in ("write_scene", "continue"):
            chapter = await asyncio.to_thread(chapter_repo.get_chapter, project_id, chapter_id)
            if not chapter:
                logger.warning("Chapter %s not found for project %s, skipping outline injection", chapter_id, project_id)
            elif chapter.get("outline_json"):
                try:
                    outline_data = json.loads(chapter["outline_json"])
                    if outline_data:
                        writing_brief["chapter_outline"] = outline_data
                        logger.info("Injected chapter outline: %d beats", len(outline_data))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Failed to parse outline_json for chapter %s", chapter_id)

        # Force-inject continuation context for continue tasks so the writer
        # composer always has it, even if the orchestrator brief missed these keys.
        if task_type == "continue":
            from .manuscript_context_builder import build_continuation_context
            cont_ctx = await asyncio.to_thread(
                build_continuation_context,
                project_id, last_block_id=context.get("last_block_id") or None,
            )
            if cont_ctx.get("tail_text"):
                # Only inject if the brief doesn't already have it (orchestrator may have set it)
                if not writing_brief.get("continuation_context"):
                    writing_brief["continuation_context"] = {
                        "tail_text": cont_ctx["tail_text"],
                        "narrative_note": cont_ctx.get("narrative_note", ""),
                        "last_location": cont_ctx.get("last_location", ""),
                    }
                if not writing_brief.get("continue_from"):
                    writing_brief["continue_from"] = cont_ctx["tail_text"][-500:]
                # Inject summaries and threads into brief if missing
                if not writing_brief.get("recent_narrative") and cont_ctx.get("recent_summaries"):
                    writing_brief["recent_narrative"] = "\n".join(
                        f"第{s['block_order']}段：{s['summary']}"
                        for s in cont_ctx["recent_summaries"]
                        if s.get("summary")
                    )
                if not writing_brief.get("open_threads") and cont_ctx.get("active_threads"):
                    writing_brief["open_threads"] = cont_ctx["active_threads"]
                logger.info(
                    "Injected continuation context: tail=%d chars, summaries=%d, threads=%d",
                    len(cont_ctx.get("tail_text", "")),
                    len(cont_ctx.get("recent_summaries", [])),
                    len(cont_ctx.get("active_threads", [])),
                )

        # --- Anti-repetition constraints from prior chapters ---
        # Pull high-frequency patterns already used in chapters < current and
        # attach them to the brief; WriterComposer renders them as an
        # "### 反重复约束" block in the system prompt. Soft enhancement — if
        # the repo is unavailable or empty we continue without it.
        _co_raw = context.get("chapter_order") or request.get("chapter_order") or 0
        try:
            _co_int = int(_co_raw)
        except (TypeError, ValueError):
            _co_int = 0
        if _co_int > 0:
            try:
                dedup_repo = DedupIndexRepository(engine)
                dedup_constraints = await asyncio.to_thread(
                    dedup_repo.get_constraints,
                    project_id,
                    max(0, _co_int - 1),
                )
                if any(dedup_constraints.values()):
                    writing_brief["dedup_constraints"] = dedup_constraints
                    logger.info(
                        "Injected dedup constraints: %s",
                        {k: len(v) for k, v in dedup_constraints.items() if v},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("dedup constraints injection failed: %s", exc)

        # --- Outline branch: skip Phase 2/3, save directly ---
        if task_type == "outline":
            outline = self._parse_outline(brief_content)
            if chapter_id:
                await asyncio.to_thread(chapter_repo.ensure_chapter, project_id, chapter_id)
                await asyncio.to_thread(
                    chapter_repo.update_chapter,
                    project_id, chapter_id,
                    outline_json=json.dumps(outline, ensure_ascii=False),
                )
            logger.info("Outline saved: chapter_id=%s, scenes=%d", chapter_id, len(outline))
            yield {
                "type": "outline_ready",
                "outline": outline,
                "chapter_id": chapter_id,
                **_stamp(),
            }
            yield {"type": "done", **_stamp(), "outline_saved": True, "scene_count": len(outline)}
            return

        # --- Phase 2: Writer Agent ---
        try:
            writer_client = await self.router.build_async_client("writer_composer")
            writer_model = writer_client.model
        except Exception:
            writer_model = "unknown"
        yield {"type": "orchestrator_status", "phase": "writing", **_stamp(), "message": "写作层启动中...", "model": writer_model}

        # Load preset prompt
        preset_prompt = await asyncio.to_thread(self._load_preset, project_id, request.get("preset_id"))

        composer = WriterComposer(llm_router=self.router)

        # Emit writer prompt snapshot for debugging
        writer_system = composer._build_system_prompt(preset_prompt, writing_brief)
        writer_user = composer._build_user_prompt(writing_brief)
        yield {
            "type": "prompt_snapshot",
            **_stamp(),
            "phase": "writer",
            "round": 0,
            "messages": [
                {"role": "system", "content": writer_system},
                {"role": "user", "content": writer_user},
            ],
        }

        full_text = ""

        try:
            async for chunk in composer.compose_stream(writing_brief, preset_prompt):
                full_text += chunk
                yield {"type": "writer_token", "token": chunk}
        except ValueError as exc:
            yield {"type": "error", **_stamp(), "message": f"LLM 模块未绑定 (writer_composer): {exc}"}
            return

        # --- Phase 3: Post-Processing ---
        scene_id = request.get("scene_id") or f"sc_{uuid.uuid4().hex[:12]}"

        processor = PostProcessor()
        result = await asyncio.to_thread(
            processor.process,
            project_id=project_id,
            chapter_id=chapter_id,
            scene_order=scene_order,
            scene_id=scene_id,
            content=full_text,
            writing_brief=writing_brief,
            title=writing_brief.get("scene_focus", ""),
            pov_entity_id=request.get("pov_entity_id"),
            location=writing_brief.get("location"),
            involved_entities_json=json.dumps(
                request.get("involved_entity_ids", []), ensure_ascii=False
            ),
        )

        # Fire-and-forget: extract anti-repetition patterns from the committed
        # prose and store them in dedup_index for the NEXT generation. We never
        # await — the user sees `done` immediately; the extractor runs on the
        # event loop in the background. Failures inside the extractor are
        # swallowed there, so `create_task` can't propagate exceptions here.
        chapter_order_for_dedup = request.get("chapter_order", 0) or 0
        if chapter_order_for_dedup and full_text.strip():
            try:
                asyncio.create_task(
                    DedupExtractor().extract_and_save(
                        project_id=project_id,
                        chapter_order=int(chapter_order_for_dedup),
                        scene_id=scene_id,
                        content=full_text,
                        scene_order=scene_order,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("dedup extractor schedule failed: %s", exc)

        # --- Phase 4: Reviewer ---
        # Scene is already committed; reviewer produces a non-blocking quality
        # report that the frontend surfaces as an action panel ("accept rewrite"
        # vs "keep draft"). A missing/unbound reviewer module degrades to a
        # "skipped" status and the run still yields `done` normally — the user
        # sees the draft the same as before, just without a review panel.
        review_t0 = time.monotonic()
        yield {
            "type": "reviewer_status",
            **_stamp(),
            "status": "running",
            "message": "审校中...",
        }
        review_payload = await WriterReviewer().review(
            draft=full_text,
            writing_brief=writing_brief,
            prev_narrative=writing_brief.get("recent_narrative", "") or "",
            dedup_constraints=writing_brief.get("dedup_constraints") or {},
        )
        yield {
            "type": "reviewer_feedback",
            **_stamp(),
            "feedback": review_payload,
            "scene_id": scene_id,
            "chapter_id": chapter_id,
            "chapter_order": int(chapter_order_for_dedup) if chapter_order_for_dedup else 0,
            "scene_order": result.get("scene_order", scene_order),
        }
        yield {
            "type": "reviewer_complete",
            **_stamp(),
            "elapsed_ms": int((time.monotonic() - review_t0) * 1000),
            "status": review_payload.get("status", "ok"),
        }

        yield {"type": "done", **_stamp(), **result}

    def _build_orchestrator_user_message(self, task_type: str, context: dict) -> str:
        """Build the initial user message for the orchestrator agent."""
        parts = [f"请为以下写作任务收集所需的设定数据并生成 writing_brief。"]
        parts.append(f"任务类型：{task_type}")

        if context.get("scene_focus"):
            parts.append(f"场景描述：{context['scene_focus']}")
        if context.get("user_instruction"):
            parts.append(f"用户指令：{context['user_instruction']}")
        if context.get("selected_text"):
            text = context["selected_text"]
            if len(text) > 2000:
                text = text[:2000] + "...(已截断)"
            parts.append(f"选中文本：{text}")
        if context.get("pov_character"):
            parts.append(f"视角角色：{context['pov_character']}")
        if context.get("involved_entities"):
            parts.append(f"涉及角色：{context['involved_entities']}")

        return "\n".join(parts)

    def _parse_brief(self, content: str, fallback_context: dict) -> dict:
        """Parse writing_brief JSON from orchestrator output, with fallback."""
        if not content:
            logger.warning("Brief content is empty, using fallback")
            return self._fallback_brief(fallback_context)

        # Strategy 1: markdown code block (greedy match for nested JSON)
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]+\})\s*```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.warning("Markdown JSON block found but failed to parse")

        # Strategy 2: whole content is JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 3: find outermost { ... } using brace counting
        parsed = self._extract_json_by_braces(content)
        if parsed is not None:
            return parsed

        # Strategy 4: fallback — pass raw content through so writer still gets context
        logger.warning(
            "Failed to parse writing_brief as JSON (len=%d), using fallback with raw_context",
            len(content),
        )
        brief = self._fallback_brief(fallback_context)
        brief["raw_context"] = content
        return brief

    @staticmethod
    def _extract_json_by_braces(text: str) -> dict | None:
        """Find the outermost balanced { ... } and parse it as JSON."""
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _fallback_brief(self, context: dict) -> dict:
        return {
            "task": context.get("task_type", "write_scene"),
            "scene_focus": context.get("scene_focus", ""),
            "user_instruction": context.get("user_instruction", ""),
            "pov": {"name": context.get("pov_character", ""), "profile_summary": ""},
            "involved_characters": [],
            "relationships": [],
            "scene_context": "",
            "recent_narrative": "",
            "open_threads": [],
            "constraints": [],
        }

    def _parse_outline(self, content: str) -> list:
        """Parse a JSON array outline from the agent loop output."""
        if not content:
            return []

        # Strategy 1: markdown ```json code block containing an array
        arr_match = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", content)
        if arr_match:
            try:
                result = json.loads(arr_match.group(1))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # Strategy 2: find outermost [...] using bracket counting
        start = content.find("[")
        if start >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(content)):
                ch = content[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            result = json.loads(content[start : i + 1])
                            if isinstance(result, list):
                                return result
                        except json.JSONDecodeError:
                            break

        logger.warning("Failed to parse outline JSON array (len=%d)", len(content))
        return []

    def _load_preset(self, project_id: str, preset_id: Optional[str]) -> str:
        """Load writing preset prompt. Falls back to default if not found."""
        preset_repo = PresetRepository(get_engine())
        presets = preset_repo.list_presets(project_id)

        if preset_id:
            for p in presets:
                if p["preset_id"] == preset_id:
                    return p["system_prompt"]

        # Try default preset
        for p in presets:
            if p.get("is_default"):
                return p["system_prompt"]

        # Hardcoded fallback. Kept intentionally terse — the writer composer
        # ALSO appends build_anti_cliche_constraints() to every system prompt,
        # so the heavy anti-repetition + rhythm rules live there and don't
        # need to be repeated here. These items are the baseline principles
        # that make the difference between "LLM output" and "publishable".
        return (
            "你是一名资深小说家。根据提供的写作指令创作小说正文。\n\n"
            "基础要求：\n"
            "1. 只输出小说正文，不要输出元信息、注释、大纲或元评论。\n"
            "2. 场景要有画面感——具体的动作、感官细节、人物之间的张力；避免抒情化堆砌。\n"
            "3. 对白贴合角色性格、教育背景与情境；每个角色的句子长度和词汇偏好应有辨识度。\n"
            "4. 严格遵守设定事实；遇到设定冲突时优先牺牲新意，维持世界观一致。\n"
            "5. 推进剧情时让角色的选择有因果逻辑，避免工具人式推动。\n"
            "6. 节奏优先于修辞：宁用一个锋利的动作细节，勿用三个陈旧的比喻。\n"
            "7. 续写时严格保留前文 POV 角色的说话风格、节奏与内心节拍；"
            "禁止突然切换叙事视角或语言层级（如前文口语化，新章节突然改为书面语）。"
        )


# ----------------------------------------------------------------------
# Data health diagnostics
# ----------------------------------------------------------------------


def _collect_data_health_issues(project_id: str) -> list[dict]:
    """Detect missing data that degrades the writer agent's context quality.

    Runs a few cheap repository reads and returns a list of issue dicts with
    ``{code, severity, title, hint}``. ``severity`` is ``"warning"`` (writer
    can proceed, but output quality may suffer) or ``"info"`` (optional
    feature not yet populated). Fatal conditions are not surfaced here — the
    orchestrator's normal error paths handle those.
    """
    from ...database import get_engine
    from ...repositories.graph_repo import GraphRepository
    from ...repositories.narrative_repo import NarrativeRepository
    from ...repositories.worldline_session_repo import WorldlineSessionRepository

    engine = get_engine()
    issues: list[dict] = []

    # Narrative: arcs empty means no global story structure context.
    try:
        narrative_repo = NarrativeRepository(engine)
        if not narrative_repo.list_narrative_arcs(project_id, limit=1):
            issues.append(
                {
                    "code": "narrative_arcs_empty",
                    "severity": "warning",
                    "title": "叙事弧线数据为空",
                    "hint": (
                        "Agent 工具 `get_story_overview` 将返回空结果，"
                        "Agent 难以把握全书叙事节奏。"
                        "建议先在「总览」页跑完种子分析 Stage 3（聚合阶段）。"
                    ),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("narrative health probe failed: %s", exc, exc_info=True)

    # Graph: no graph means query_entity / query_graph_neighbors can't resolve.
    try:
        graph_repo = GraphRepository(engine)
        if not graph_repo.has_graph(project_id):
            issues.append(
                {
                    "code": "story_graph_missing",
                    "severity": "warning",
                    "title": "故事图谱尚未构建",
                    "hint": (
                        "`query_graph_neighbors` / `query_relationship_network` / "
                        "`query_event` 将无结果；实体别名解析也会退化。"
                        "建议先在「故事图谱」页触发图谱构建。"
                    ),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph health probe failed: %s", exc, exc_info=True)

    # Worldline: missing is normal for projects that don't use simulation;
    # emit as "info" so the UI can distinguish it from a real warning.
    try:
        session_repo = WorldlineSessionRepository(engine)
        if not session_repo.list_sessions(project_id=project_id, limit=1):
            issues.append(
                {
                    "code": "worldline_sessions_empty",
                    "severity": "info",
                    "title": "暂无世界线推演会话",
                    "hint": (
                        "`query_worldline_session` 将返回「暂无世界线推演记录」。"
                        "如果本次写作不需要推演分支数据，可忽略此提示。"
                    ),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("worldline health probe failed: %s", exc, exc_info=True)

    return issues
