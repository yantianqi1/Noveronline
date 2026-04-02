"""ReviewerAgent 辅助函数。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

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


def build_review_prompt(
    generated_text: str,
    context_pack: Dict[str, Any],
    memory_bundle: Dict[str, Any],
) -> str:
    sections: List[str] = []
    sections.append(_must_know_section(context_pack))
    sections.append(_warning_section(context_pack))
    sections.append(f"## 角色记忆\n{memory_bundle.get('rendered_context', '暂无')}")
    continuity_section = _continuity_section(context_pack)
    if continuity_section:
        sections.append(continuity_section)
    sections.append(f"## 待审校正文\n{generated_text[:6000]}")
    sections.append("请检查正文是否符合上述设定和连续性要求，输出 JSON 审校报告。")
    return "\n\n".join(sections)


def rule_based_review(
    generated_text: str,
    context_pack: Dict[str, Any],
) -> Dict[str, Any]:
    issues = []
    pov = context_pack.get("context_scope", {}).get("pov_character", "")
    if pov and pov not in generated_text:
        issues.append(
            {
                "dimension": "角色一致性",
                "severity": "medium",
                "description": f"POV 角色「{pov}」在生成正文中未出现",
                "suggestion": f"确保 POV 角色「{pov}」在正文中出现并有相应的视角描写",
            }
        )
    for item in context_pack.get("warnings", []):
        summary = item.get("summary", "")
        if "冲突" in summary or "歧义" in summary:
            issues.append(
                {
                    "dimension": "连续性",
                    "severity": "low",
                    "description": f"请注意风险提示：{summary}",
                    "suggestion": "检查正文是否规避了该风险",
                }
            )
    has_high = any(item.get("severity") == "high" for item in issues)
    score = max(0, 100 - len(issues) * 15) if issues else 100
    passed = not has_high and score >= PASS_SCORE_THRESHOLD
    assessment = (
        f"规则检查完成，发现 {len(issues)} 个关注点。"
        if issues
        else "规则检查通过，未发现明显问题。"
    )
    return {
        "pass": passed,
        "score": score,
        "issues": issues,
        "keep": [],
        "overall_assessment": assessment,
        "model_name": "",
        "review_mode": "rule",
    }


def normalize_review_result(
    result: Dict[str, Any],
    mode: str,
    model_name: str = "",
) -> Dict[str, Any]:
    issues = result.get("issues", [])
    normalized_issues = [
        {
            "dimension": issue.get("dimension", issue.get("category", "其他")),
            "severity": issue.get("severity", "medium"),
            "description": issue.get("description", ""),
            "suggestion": issue.get("suggestion", ""),
        }
        for issue in issues
    ]
    has_high = any(item.get("severity") == "high" for item in normalized_issues)
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


def empty_review_result(message: str) -> Dict[str, Any]:
    return {
        "pass": True,
        "score": 0,
        "issues": [],
        "keep": [],
        "overall_assessment": message,
        "model_name": "",
        "review_mode": "skipped",
    }


def _must_know_section(context_pack: Dict[str, Any]) -> str:
    lines = [f"- {item.get('summary', '')}" for item in context_pack.get("must_know", [])[:6]]
    return "## 已知设定（必须延续的事实）\n" + ("\n".join(lines) if lines else "- 暂无")


def _warning_section(context_pack: Dict[str, Any]) -> str:
    lines = [f"- {item.get('summary', '')}" for item in context_pack.get("warnings", [])[:4]]
    return "## 风险提示\n" + ("\n".join(lines) if lines else "- 暂无")


def _continuity_section(context_pack: Dict[str, Any]) -> str:
    anchor = context_pack.get("continuity_anchor")
    if not anchor:
        return ""
    lines: List[str] = []
    ending = anchor.get("prev_chapter_ending", "")
    if ending:
        lines.append(f"上章末尾原文：{ending[:300]}...")
    for item in anchor.get("chapter_summaries", [])[:3]:
        lines.append(f"第{item.get('chapter_index', '?')}章摘要：{item.get('summary', '')}")
    threads = anchor.get("open_threads", [])
    if threads:
        lines.append(f"未解悬念线：{'、'.join(threads)}")
    note = anchor.get("timeline_note", "")
    if note:
        lines.append(f"时间线注记：{note}")
    return "## 前章连续性上下文\n" + "\n".join(lines) if lines else ""
