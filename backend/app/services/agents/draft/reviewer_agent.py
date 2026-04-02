"""一致性审校 Agent。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ...llm_router import LlmRouter
from .review_support import (
    REVIEWER_SYSTEM_PROMPT,
    build_review_prompt,
    empty_review_result,
    normalize_review_result,
    rule_based_review,
)

logger = logging.getLogger(__name__)

NOVEL_DRAFT_REVIEWER_MODULE = "novel_draft_reviewer"
REVIEWER_TEMPERATURE = 0.2
REVIEWER_MAX_TOKENS = 3072


class ReviewerAgent:
    """结构化审校 Agent，支持打回重试循环。"""

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        custom_rules: Optional[str] = None,
    ):
        self.llm_router = llm_router or LlmRouter()
        self.system_prompt = custom_rules or REVIEWER_SYSTEM_PROMPT

    def review(
        self,
        generated_text: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not generated_text.strip():
            return self._empty_result("生成的正文为空，跳过审校。")
        try:
            client = self.llm_router.build_client(NOVEL_DRAFT_REVIEWER_MODULE)
        except ValueError:
            logger.info("ReviewerAgent: 审校模块未绑定，跳过 LLM 审校，使用规则检查。")
            return self._rule_based_review(generated_text, context_pack)
        prompt = self._build_review_prompt(generated_text, context_pack, memory_bundle)
        try:
            result = client.chat_json(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=REVIEWER_TEMPERATURE,
                max_tokens=REVIEWER_MAX_TOKENS,
            )
        except Exception as exc:
            logger.warning("ReviewerAgent: LLM 审校失败 — %s", exc)
            return self._rule_based_review(generated_text, context_pack)
        return self._normalize_result(result, "llm", client.model)

    def build_revision_feedback(self, review_result: Dict[str, Any]) -> Dict[str, Any]:
        issues = review_result.get("issues", [])
        keep = review_result.get("keep", [])
        revision_lines = ["请根据以下审校意见对正文做定向修改：", ""]
        for index, issue in enumerate(issues, 1):
            severity_label = {
                "high": "【必须修改】",
                "medium": "【建议修改】",
                "low": "【可选修改】",
            }.get(issue.get("severity", "medium"), "【修改】")
            dimension = issue.get("dimension", "其他")
            description = issue.get("description", "")
            revision_lines.append(f"{index}. {severity_label}[{dimension}] {description}")
            suggestion = issue.get("suggestion", "")
            if suggestion:
                revision_lines.append(f"   建议：{suggestion}")
        if keep:
            revision_lines.extend(["", "以下部分写得好，请保留不要改动："])
            revision_lines.extend(f"- {item}" for item in keep)
        revision_lines.extend(["", "注意：只修改上述指出的问题，不要重写整段正文。"])
        return {
            "revision_instruction": "\n".join(revision_lines),
            "issues": issues,
            "keep": keep,
            "score": review_result.get("score", 0),
        }

    def _build_review_prompt(
        self,
        generated_text: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
    ) -> str:
        return build_review_prompt(generated_text, context_pack, memory_bundle)

    def _rule_based_review(
        self,
        generated_text: str,
        context_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        return rule_based_review(generated_text, context_pack)

    def _normalize_result(
        self,
        result: Dict[str, Any],
        mode: str,
        model_name: str = "",
    ) -> Dict[str, Any]:
        return normalize_review_result(result, mode, model_name)

    def _empty_result(self, message: str) -> Dict[str, Any]:
        return empty_review_result(message)
