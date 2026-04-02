"""Draft orchestrator 辅助函数。"""

from __future__ import annotations

from typing import Any, Dict, Optional


def load_custom_reviewer_rules(project_id: str) -> str:
    """尝试加载项目的自定义审校规则，不存在则返回空字符串。"""
    if not project_id:
        return ""
    try:
        from ....models.project import ProjectManager

        data = ProjectManager.load_project_json(project_id, "reviewer_rules.json")
        return (data or {}).get("custom_prompt", "")
    except Exception:
        return ""


def sse_event(
    event_type: str,
    agent: str = "",
    status: str = "",
    message: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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


def empty_memory_bundle() -> Dict[str, Any]:
    return {
        "character_profile": {},
        "memories": [],
        "relationships": [],
        "rendered_context": "",
    }


def skipped_review_result() -> Dict[str, Any]:
    return {
        "pass": True,
        "score": 0,
        "issues": [],
        "keep": [],
        "overall_assessment": "审校跳过",
        "review_mode": "skipped",
    }


def context_status_detail(
    context_summary: Dict[str, Any],
    context_pack: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "memory_count": context_summary["must_know_count"],
        "has_continuity": context_summary.get("has_continuity", False),
        "must_know_items": [
            item.get("summary", "")
            for item in context_pack.get("must_know", [])[:5]
        ],
        "should_know_count": len(context_pack.get("should_know", [])),
        "warnings": [
            item.get("summary", "")
            for item in context_pack.get("warnings", [])[:4]
        ],
    }


def memory_status_detail(memory_bundle: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "memories": [
            {"summary": item.get("summary", "")}
            for item in memory_bundle.get("memories", [])[:5]
        ],
    }


def style_status_detail(style_hints: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pov": style_hints.get("pov_person", "第三人称"),
        "pace": style_hints.get("rhythm", "均匀适中"),
        "tone": "中性",
        "rendered_hints": style_hints.get("rendered_hints", ""),
    }


def done_event(
    *,
    full_text: str,
    review_result: Dict[str, Any],
    revision_count: int,
    model_name: str,
    elapsed_seconds: float,
    context_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "type": "done",
        "data": {
            "final_draft": full_text,
            "revision_count": revision_count,
            "unresolved_issues": (
                review_result.get("issues", [])
                if not review_result.get("pass", True)
                else []
            ),
        },
        "full_text": full_text,
        "char_count": len(full_text),
        "review": review_result,
        "model_name": model_name,
        "elapsed_seconds": elapsed_seconds,
        "revision_count": revision_count,
    }
    if context_summary is not None:
        payload["context_summary"] = context_summary
    return payload

