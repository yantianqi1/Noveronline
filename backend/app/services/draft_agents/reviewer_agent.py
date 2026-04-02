"""一致性审校 Agent — 结构化审核，支持 writer 打回重试循环。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..llm_router import LlmRouter

logger = logging.getLogger(__name__)

NOVEL_DRAFT_REVIEWER_MODULE = "novel_draft_reviewer"
REVIEWER_TEMPERATURE = 0.2
REVIEWER_MAX_TOKENS = 3072

# 审核通过的最低分数线
PASS_SCORE_THRESHOLD = 70

REVIEWER_SYSTEM_PROMPT = """你是一名专业的小说连续性审校编辑。

你的工作是检查一段新生成的小说正文，从以下四个维度做结构化审核，并给出整体判断。

## 审核维度

### 1. 连续性（continuity）
- 本章开头与上章结尾是否自然衔接（场景、情绪、时间）
- 角色在上章末尾的状态与本章描述是否矛盾

### 2. 角色一致性（character_consistency）
- POV 角色的行为动机是否符合当前设定中的性格
- 非 POV 角色的行为是否合理

### 3. 悬念与伏笔（thread_management）
- 未解决线索是否有被推进或呼应
- 是否意外"提前解决"了不该解决的悬念

### 4. 风格一致性（style_consistency）
- 叙事视角是否稳定（不在第三人称中混入第一人称感受）
- 节奏是否与前文风格相符

## 输出要求
只输出 JSON 对象，格式如下：
{
  "pass": true 或 false,
  "score": 0-100 的整数，
  "issues": [
    {
      "dimension": "连续性 | 角色一致性 | 悬念与伏笔 | 风格一致性",
      "severity": "high | medium | low",
      "description": "问题描述",
      "suggestion": "修改建议"
    }
  ],
  "keep": ["值得保留的段落或特点描述"],
  "overall_assessment": "一句话总评"
}

评判标准：
- 如果没有 high 级别问题且 score >= 70，pass 为 true
- severity 为 high 的问题必须修改
- severity 为 medium 的问题建议修改
- severity 为 low 的问题可忽略
- keep 列表中应标注写得好的、不应在修改中丢失的部分
"""


class ReviewerAgent:
    """结构化审校 Agent，支持打回重试循环。"""

    def __init__(self, llm_router: Optional[LlmRouter] = None, custom_rules: Optional[str] = None):
        self.llm_router = llm_router or LlmRouter()
        self.system_prompt = custom_rules if custom_rules else REVIEWER_SYSTEM_PROMPT

    def review(
        self,
        generated_text: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        审校生成的正文。

        Returns:
            结构化审校结果，包含 pass, score, issues, keep, overall_assessment。
        """
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
            return self._normalize_result(result, "llm", client.model)
        except Exception as exc:
            logger.warning("ReviewerAgent: LLM 审校失败 — %s", exc)
            return self._rule_based_review(generated_text, context_pack)

    def build_revision_feedback(self, review_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        从审校结果构造修改意见单，用于发回 writer_agent。

        Returns:
            修改意见单，包含 issues 和 keep，可直接注入 writer 的 revision_context。
        """
        issues = review_result.get("issues", [])
        keep = review_result.get("keep", [])

        # 构造给 writer 的修订指令
        revision_lines = ["请根据以下审校意见对正文做定向修改："]
        revision_lines.append("")

        for i, issue in enumerate(issues, 1):
            severity_label = {"high": "【必须修改】", "medium": "【建议修改】", "low": "【可选修改】"}.get(
                issue.get("severity", "medium"), "【修改】"
            )
            dimension = issue.get("dimension", "其他")
            description = issue.get("description", "")
            suggestion = issue.get("suggestion", "")
            revision_lines.append(f"{i}. {severity_label}[{dimension}] {description}")
            if suggestion:
                revision_lines.append(f"   建议：{suggestion}")

        if keep:
            revision_lines.append("")
            revision_lines.append("以下部分写得好，请保留不要改动：")
            for item in keep:
                revision_lines.append(f"- {item}")

        revision_lines.append("")
        revision_lines.append("注意：只修改上述指出的问题，不要重写整段正文。")

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
        """组装审校 prompt。"""
        sections = []

        # 已知设定
        must_know_lines = []
        for item in context_pack.get("must_know", [])[:6]:
            must_know_lines.append(f"- {item.get('summary', '')}")
        must_know_text = "\n".join(must_know_lines) if must_know_lines else "- 暂无"
        sections.append(f"## 已知设定（必须延续的事实）\n{must_know_text}")

        # 风险提示
        warning_lines = []
        for item in context_pack.get("warnings", [])[:4]:
            warning_lines.append(f"- {item.get('summary', '')}")
        warning_text = "\n".join(warning_lines) if warning_lines else "- 暂无"
        sections.append(f"## 风险提示\n{warning_text}")

        # 角色记忆
        memory_text = memory_bundle.get("rendered_context", "暂无")
        sections.append(f"## 角色记忆\n{memory_text}")

        # 前章连续性上下文
        anchor = context_pack.get("continuity_anchor")
        if anchor:
            continuity_lines = []
            ending = anchor.get("prev_chapter_ending", "")
            if ending:
                continuity_lines.append(f"上章末尾原文：{ending[:300]}...")

            for item in anchor.get("chapter_summaries", [])[:3]:
                continuity_lines.append(
                    f"第{item.get('chapter_index', '?')}章摘要：{item.get('summary', '')}"
                )

            threads = anchor.get("open_threads", [])
            if threads:
                continuity_lines.append(f"未解悬念线：{'、'.join(threads)}")

            note = anchor.get("timeline_note", "")
            if note:
                continuity_lines.append(f"时间线注记：{note}")

            if continuity_lines:
                sections.append("## 前章连续性上下文\n" + "\n".join(continuity_lines))

        # 待审校正文
        sections.append(f"## 待审校正文\n{generated_text[:6000]}")
        sections.append("请检查正文是否符合上述设定和连续性要求，输出 JSON 审校报告��")

        return "\n\n".join(sections)

    def _rule_based_review(
        self,
        generated_text: str,
        context_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """基于规则的轻量审校（不调用 LLM）。"""
        issues: List[Dict[str, Any]] = []

        pov = context_pack.get("context_scope", {}).get("pov_character", "")
        if pov and pov not in generated_text:
            issues.append({
                "dimension": "角色一致性",
                "severity": "medium",
                "description": f"POV 角色「{pov}」在生成正文中未出现",
                "suggestion": f"确保 POV 角色「{pov}」在正文中出现并有相应的视角描写",
            })

        for item in context_pack.get("warnings", []):
            summary = item.get("summary", "")
            if "冲突" in summary or "歧义" in summary:
                issues.append({
                    "dimension": "连续性",
                    "severity": "low",
                    "description": f"请注意风险提示：{summary}",
                    "suggestion": "检查正文是否规避了该风险",
                })

        has_high = any(i.get("severity") == "high" for i in issues)
        score = max(0, 100 - len(issues) * 15) if issues else 100
        passed = not has_high and score >= PASS_SCORE_THRESHOLD

        assessment = f"规则检查完成，发现 {len(issues)} 个关注点。" if issues else "规则检查通过，未发现明显问题。"
        return {
            "pass": passed,
            "score": score,
            "issues": issues,
            "keep": [],
            "overall_assessment": assessment,
            "model_name": "",
            "review_mode": "rule",
        }

    def _normalize_result(
        self, result: Dict[str, Any], mode: str, model_name: str = ""
    ) -> Dict[str, Any]:
        """标准化 LLM 返回的审校结果。"""
        issues = result.get("issues", [])
        # 标准化每个 issue
        normalized_issues = []
        for issue in issues:
            normalized_issues.append({
                "dimension": issue.get("dimension", issue.get("category", "其他")),
                "severity": issue.get("severity", "medium"),
                "description": issue.get("description", ""),
                "suggestion": issue.get("suggestion", ""),
            })

        has_high = any(i.get("severity") == "high" for i in normalized_issues)
        score = result.get("score", 80 if not issues else 50)
        passed = result.get("pass", not has_high and score >= PASS_SCORE_THRESHOLD)

        logger.info(
            "ReviewerAgent: 审校完成 — pass=%s, score=%d, issues=%d",
            passed,
            score,
            len(normalized_issues),
        )

        return {
            "pass": passed,
            "score": score,
            "issues": normalized_issues,
            "keep": result.get("keep", []),
            "overall_assessment": result.get("overall_assessment", "审校完成。"),
            "model_name": model_name,
            "review_mode": mode,
        }

    def _empty_result(self, message: str) -> Dict[str, Any]:
        return {
            "pass": True,
            "score": 0,
            "issues": [],
            "keep": [],
            "overall_assessment": message,
            "model_name": "",
            "review_mode": "skipped",
        }
