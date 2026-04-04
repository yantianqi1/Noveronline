"""Dual-layer writer orchestrator: orchestrator agent + writer agent."""

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Generator, Optional

from .agent_loop import AgentLoop
from .prompts import build_orchestrator_prompt
from .tools import NOVEL_TOOLS, MANUSCRIPT_TOOLS
from .writer import WriterComposer
from .post_processor import PostProcessor
from .novel_db import NovelDB

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

    def run(self, request: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """
        Execute the full writing pipeline.

        request keys:
            project_id (required)
            task_type: write_scene|continue|rewrite|expand|outline|consistency_check
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

        # Ensure novel.sqlite3 exists
        db = NovelDB()
        db.ensure_schema(project_id)

        # --- Phase 1: Orchestrator Agent ---
        yield {"type": "orchestrator_status", "phase": "starting", **_stamp(), "message": "编排层启动中..."}

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
        orchestrator_client = self.router.build_client("writer_orchestrator")

        # Include manuscript tools for continuation tasks
        tools = NOVEL_TOOLS
        if task_type == "continue":
            tools = NOVEL_TOOLS + MANUSCRIPT_TOOLS

        agent_loop = AgentLoop(
            llm_client=orchestrator_client,
            tools=tools,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )

        # Build the user message for the orchestrator
        user_msg = self._build_orchestrator_user_message(task_type, context)

        # Run agent loop, forwarding events directly
        brief_content = ""
        tool_count = 0
        tool_results_raw: list[dict] = []  # Collect raw tool outputs
        for event in agent_loop.run(user_msg):
            if event["type"] == "brief_ready":
                brief_content = event.get("content", "")
            elif event["type"] in ("tool_call", "tool_result", "thinking", "prompt_snapshot"):
                if event["type"] == "tool_call":
                    tool_count += 1
                if event["type"] == "tool_result":
                    tool_results_raw.append({
                        "tool": event.get("name", ""),
                        "result": event.get("full_result", event.get("summary", "")),
                    })
                yield event
            elif event["type"] == "error":
                yield event
                return

        # Phase summary
        yield {
            "type": "phase_summary",
            **_stamp(),
            "phase": "collecting",
            "tool_count": tool_count,
            "message": f"收集完成：{tool_count}次工具调用，耗时{_stamp()['elapsed_ms'] / 1000:.1f}s",
        }

        # Parse writing_brief
        writing_brief = self._parse_brief(brief_content, context)

        # Inject raw tool results directly — bypasses LLM summarization loss
        if tool_results_raw:
            writing_brief["_tool_results"] = tool_results_raw

        logger.info(
            "writing_brief parsed: keys=%s, raw_len=%d, tool_results=%d",
            list(writing_brief.keys()),
            len(brief_content),
            len(tool_results_raw),
        )

        # --- Phase 2: Writer Agent ---
        yield {"type": "orchestrator_status", "phase": "writing", **_stamp(), "message": "写作层启动中..."}

        # Load preset prompt
        preset_prompt = self._load_preset(project_id, request.get("preset_id"))

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

        for chunk in composer.compose_stream(writing_brief, preset_prompt):
            full_text += chunk
            yield {"type": "writer_token", "token": chunk}

        # --- Phase 3: Post-Processing ---
        scene_id = request.get("scene_id") or f"sc_{uuid.uuid4().hex[:12]}"

        processor = PostProcessor()
        result = processor.process(
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

    def _load_preset(self, project_id: str, preset_id: Optional[str]) -> str:
        """Load writing preset prompt. Falls back to default if not found."""
        db = NovelDB()
        presets = db.list_presets(project_id)

        if preset_id:
            for p in presets:
                if p["preset_id"] == preset_id:
                    return p["system_prompt"]

        # Try default preset
        for p in presets:
            if p.get("is_default"):
                return p["system_prompt"]

        # Hardcoded fallback
        return (
            "你是一名资深小说家。根据提供的写作指令创作小说正文。\n\n"
            "要求：\n"
            "1. 只输出小说正文，不要输出元信息、注释或大纲。\n"
            "2. 场景描写要有画面感，对话要贴合角色性格。\n"
            "3. 严格遵守设定中的事实，不要与之矛盾。\n"
            "4. 推进剧情时让角色的选择有因果逻辑。"
        )
