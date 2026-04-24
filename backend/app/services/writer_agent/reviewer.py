"""Independent reviewer pass for writer drafts.

Receives a just-produced draft plus its surrounding context (writing_brief,
previous-chapter tail, accumulated dedup constraints) and asks an
independent LLM (``writer_reviewer`` module) to surface concrete rewrite
suggestions before the draft is committed. The user sees the reviewer's
output in the frontend and chooses to either accept the rewrite or keep
the original draft — the reviewer does NOT itself perform the rewrite.

Contract: single JSON response per the schema in :func:`prompts.build_reviewer_prompt`.
Failure modes (missing LLM binding, parse error, timeout) are surfaced as a
benign "review skipped" payload rather than raising, so a failing reviewer
never blocks the writer flow.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.llm_router import LlmRouter

from .prompts import build_reviewer_prompt, build_reviewer_user_message

logger = logging.getLogger(__name__)


_ALLOWED_SEVERITIES = {"high", "medium", "low"}
_ALLOWED_CATEGORIES = {
    "cliche",
    "pattern_reuse",
    "pov_drift",
    "timeline",
    "pacing",
    "figurative_density",
    "redundant_modifier",
    "voice",
}


class WriterReviewer:
    """LLM wrapper that scores a draft and emits actionable rewrite suggestions."""

    def __init__(self, llm_router: LlmRouter | None = None):
        self.router = llm_router or LlmRouter()

    async def review(
        self,
        *,
        draft: str,
        writing_brief: dict | None = None,
        prev_narrative: str = "",
        dedup_constraints: dict | None = None,
    ) -> dict[str, Any]:
        """Run one review pass.

        Returns a dict with ``overall_score``, ``summary``, ``issues`` plus a
        ``status`` flag so the caller can distinguish "reviewer unbound" /
        "reviewer failed" from a legitimate empty review. Never raises.
        """
        if not draft or not draft.strip():
            return self._skipped("draft 为空，跳过审校")

        brief = writing_brief or {}
        pov = brief.get("pov") or {}
        pov_name = pov.get("name", "") if isinstance(pov, dict) else ""
        speech_style = pov.get("speech_style", "") if isinstance(pov, dict) else ""

        try:
            client = await self.router.build_async_client("writer_reviewer")
        except ValueError:
            return self._skipped("writer_reviewer 模块未绑定，跳过审校")
        except Exception as exc:  # noqa: BLE001
            logger.warning("reviewer client build failed: %s", exc)
            return self._skipped(f"审校客户端构建失败：{exc}")

        messages = [
            {"role": "system", "content": build_reviewer_prompt()},
            {
                "role": "user",
                "content": build_reviewer_user_message(
                    draft=draft,
                    scene_focus=brief.get("scene_focus") or "",
                    pov_name=pov_name or "",
                    speech_style=speech_style or "",
                    prev_narrative=prev_narrative or brief.get("recent_narrative", "") or "",
                    dedup_constraints=dedup_constraints or brief.get("dedup_constraints") or {},
                ),
            },
        ]

        try:
            raw = await client.chat_json_value(messages, temperature=0.2, max_tokens=2000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("reviewer LLM call failed: %s", exc)
            return self._skipped(f"审校 LLM 调用失败：{exc}")

        return self._normalize(raw)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skipped(reason: str) -> dict[str, Any]:
        return {
            "status": "skipped",
            "reason": reason,
            "overall_score": None,
            "summary": "",
            "issues": [],
        }

    @classmethod
    def _normalize(cls, raw: Any) -> dict[str, Any]:
        """Coerce the LLM response into the contract the frontend expects.

        Malformed shapes degrade gracefully to an empty issues list so the
        UI can still render "review complete, no issues" instead of an error.
        """
        if not isinstance(raw, dict):
            return {
                "status": "ok",
                "overall_score": None,
                "summary": "",
                "issues": [],
            }

        issues_raw = raw.get("issues")
        issues: list[dict[str, Any]] = []
        if isinstance(issues_raw, list):
            for idx, item in enumerate(issues_raw):
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity", "medium")).lower()
                if severity not in _ALLOWED_SEVERITIES:
                    severity = "medium"
                category = str(item.get("category", "cliche")).lower()
                if category not in _ALLOWED_CATEGORIES:
                    category = "cliche"
                issues.append(
                    {
                        "id": str(item.get("id") or f"iss_{idx + 1}"),
                        "severity": severity,
                        "category": category,
                        "location": str(item.get("location", ""))[:120],
                        "original": str(item.get("original", ""))[:280],
                        "suggestion": str(item.get("suggestion", ""))[:400],
                        "reason": str(item.get("reason", ""))[:120],
                    }
                )

        score = raw.get("overall_score")
        try:
            score_value: float | None = max(0.0, min(1.0, float(score))) if score is not None else None
        except (TypeError, ValueError):
            score_value = None

        return {
            "status": "ok",
            "overall_score": score_value,
            "summary": str(raw.get("summary", ""))[:400],
            "issues": issues[:16],
        }
