"""Writer-first runtime bridge.

This compatibility implementation keeps the public contract aligned with the
future Pi worker while the SaaS control plane is still landing. It never
generates mock prose: a successful run requires an LLM Facility binding.
"""

from __future__ import annotations

import json
from typing import Any

from app.database import get_engine
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.scene_repo import SceneRepository
from app.repositories.writer_run_repo import WriterRunRepository

from .event_mapper import writer_event
from .llm_facility_adapter import LlmFacilityAdapter
from .tools import WriterToolRegistry


class PiWriterRuntime:
    def __init__(
        self,
        repo: WriterRunRepository | None = None,
        llm_adapter: LlmFacilityAdapter | None = None,
    ):
        self.repo = repo or WriterRunRepository(get_engine())
        self.llm_adapter = llm_adapter or LlmFacilityAdapter()

    def check_binding(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        module_key: str,
    ) -> dict[str, Any]:
        return self.llm_adapter.binding_summary(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            module_key=module_key,
        )

    async def run(self, run: dict[str, Any]) -> None:
        context = _run_context(run)
        module_key = run.get("module_key") or "writer_composer"
        self.repo.mark_running(context["tenant_id"], context["run_id"])
        self._persist_event("writer.run.started", context, {"module_key": module_key})

        try:
            client = await self.llm_adapter.build_async_client(
                tenant_id=context["tenant_id"],
                project_id=context["project_id"],
                run_id=context["run_id"],
                module_key=module_key,
            )
            brief = self._build_context_brief(run, context)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是 MiroFish-Novel Writer Agent。只输出可供作者审阅的正文草稿；"
                        "不要声称已经采用为手稿。"
                    ),
                },
                {"role": "user", "content": brief},
            ]
            full_text = ""
            async for chunk in client.chat_stream(messages, temperature=0.7, max_tokens=4096):
                full_text += chunk
                self._persist_event("writer.token", context, {"token": chunk})
            draft = self.repo.save_draft_revision(
                tenant_id=context["tenant_id"],
                project_id=context["project_id"],
                run_id=context["run_id"],
                chapter_id=run.get("chapter_id"),
                scene_id=run.get("scene_id"),
                content=full_text,
                metadata={"module_key": module_key},
                created_by=run.get("requested_by"),
            )
            self._persist_event("writer.draft.saved", context, {"draft_id": draft["draft_id"]})
            self.repo.mark_completed(context["tenant_id"], context["run_id"], result={"draft_id": draft["draft_id"]})
            self._persist_event("writer.run.completed", context, {"draft_id": draft["draft_id"]})
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "WORKFLOW_FAILED")
            self.repo.mark_failed(
                context["tenant_id"],
                context["run_id"],
                code=code,
                message=str(exc),
                details=getattr(exc, "details", {}),
            )
            self._persist_event("writer.run.failed", context, {"code": code, "message": str(exc)})

    def _build_context_brief(self, run: dict[str, Any], context: dict[str, str]) -> str:
        tool_results: list[dict[str, Any]] = []
        tool_results.append(
            self._execute_internal_tool(
                "query_chapter_scene",
                context,
                {"chapter_id": run.get("chapter_id"), "scene_id": run.get("scene_id")},
                lambda: self._query_chapter_scene(run["project_id"], run.get("chapter_id"), run.get("scene_id")),
            )
        )
        tool_results.extend(self._execute_phase2_tools(run, context))
        parts = [
            f"项目：{run['project_id']}",
            f"模式：{run.get('mode') or 'draft'}",
            f"作者指令：{run.get('instruction') or ''}",
        ]
        if tool_results:
            parts.append("工具上下文：")
            parts.append(json.dumps(tool_results, ensure_ascii=False))
        options = run.get("options") or {}
        target_words = options.get("target_words")
        if target_words:
            parts.append(f"目标字数：{target_words}")
        return "\n".join(parts)

    def _execute_phase2_tools(self, run: dict[str, Any], context: dict[str, str]) -> list[dict[str, Any]]:
        options = run.get("options") or {}
        registry = WriterToolRegistry(get_engine())
        requests = []
        selected_asset_ids = list(options.get("selected_asset_ids") or [])
        asset_query = options.get("asset_query") or options.get("style_query")
        if selected_asset_ids or asset_query:
            requests.append(
                (
                    "query_assets",
                    {
                        "selected_asset_ids": selected_asset_ids,
                        "query": asset_query or "",
                    },
                )
            )
        world_rule_query = options.get("world_rule_query")
        if world_rule_query:
            requests.append(("query_world_rules", {"query": world_rule_query}))
        for name in options.get("character_names") or []:
            requests.append(("query_character_profile", {"name": name}))
        for node_name in options.get("graph_node_names") or []:
            requests.append(("query_graph_neighbors", {"node_name": node_name}))
        worldline_path_ids = list(options.get("worldline_path_ids") or [])
        if worldline_path_ids:
            requests.append(("query_worldline_paths", {"path_ids": worldline_path_ids}))

        results: list[dict[str, Any]] = []
        for tool_name, args in requests:
            result = self._execute_internal_tool(
                tool_name,
                context,
                args,
                lambda tool_name=tool_name, args=args: registry.execute(tool_name, context, args),
            )
            results.append(result)
        return results

    def _execute_internal_tool(
        self,
        tool_name: str,
        context: dict[str, str],
        args: dict[str, Any],
        callback,
    ) -> dict[str, Any]:
        self._persist_event("writer.tool.started", context, {"tool_name": tool_name, "args": args})
        try:
            result = callback()
        except Exception as exc:  # noqa: BLE001
            self._persist_event(
                "writer.tool.completed",
                context,
                {
                    "tool_name": tool_name,
                    "result": {"message": str(exc), "code": getattr(exc, "code", "TOOL_EXECUTION_FAILED")},
                    "is_error": True,
                },
            )
            raise
        self._persist_event(
            "writer.tool.completed",
            context,
            {"tool_name": tool_name, "result": result, "is_error": False},
        )
        return {"tool_name": tool_name, "result": result}

    def _query_chapter_scene(
        self,
        project_id: str,
        chapter_id: str | None,
        scene_id: str | None,
    ) -> dict[str, Any]:
        engine = get_engine()
        result: dict[str, Any] = {}
        if chapter_id:
            chapter = ChapterRepository(engine).get_chapter(project_id, chapter_id)
            if chapter:
                result["chapter"] = {
                    "chapter_id": chapter.get("chapter_id"),
                    "title": chapter.get("title"),
                    "summary": chapter.get("summary"),
                    "outline_json": chapter.get("outline_json"),
                }
        if scene_id:
            scene = SceneRepository(engine).get_scene(project_id, scene_id)
            if scene:
                result["scene"] = {
                    "scene_id": scene.get("scene_id"),
                    "title": scene.get("title"),
                    "content": scene.get("content"),
                    "writing_brief_json": scene.get("writing_brief_json"),
                }
        return result

    def _persist_event(self, event_type: str, context: dict[str, str], payload: dict[str, Any]) -> None:
        event = writer_event(event_type, context, payload)
        self.repo.append_event(
            tenant_id=context["tenant_id"],
            project_id=context["project_id"],
            run_id=context["run_id"],
            event_type=event["type"],
            payload=event["payload"],
        )


def _run_context(run: dict[str, Any]) -> dict[str, str]:
    return {
        "tenant_id": run["tenant_id"],
        "project_id": run["project_id"],
        "run_id": run["run_id"],
    }
