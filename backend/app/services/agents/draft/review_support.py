"""ReviewerAgent 辅助函数。"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

PASS_SCORE_THRESHOLD = 70

from .prompts import assemble_reviewer_prompt

REVIEWER_SYSTEM_PROMPT = assemble_reviewer_prompt()


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
    sections.append(f"## 待审校正文\n{generated_text[:12000]}")
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

    # --- 人称混乱检测 ---
    # 去除引号内的对话文本，只检查叙述部分
    narration = re.sub(r'[""「」『』].*?[""「」『』]', '', generated_text)
    first_person_count = len(re.findall(r'我(?:的|们|自己)?', narration))
    # 如果叙述部分出现大量"我"且不是第一人称小说，可能存在人称混乱
    if first_person_count > 10:
        third_markers = len(re.findall(r'[他她它](?:的|们)?', narration))
        if third_markers > first_person_count * 2:
            issues.append(
                {
                    "dimension": "风格一致性",
                    "severity": "medium",
                    "description": f"第三人称叙述中出现了 {first_person_count} 次第一人称代词（排除对话），可能存在人称混乱",
                    "suggestion": "检查叙述部分是否意外混入了第一人称视角",
                }
            )

    # --- 重复用词检测 ---
    # 提取非常用修饰词（2-4字的形容/副词性片段），检查短距离内是否过度重复
    modifier_pattern = re.compile(r'(?:地|得)\s*(\S{2,4})')
    modifiers = modifier_pattern.findall(generated_text)
    if modifiers:
        modifier_counts = Counter(modifiers)
        repeated = [w for w, c in modifier_counts.items() if c >= 4]
        if repeated:
            issues.append(
                {
                    "dimension": "描写质量",
                    "severity": "low",
                    "description": f"以下修饰词在正文中多次重复：{'、'.join(repeated[:5])}",
                    "suggestion": "尝试使用更丰富的词汇替换重复的修饰词",
                }
            )

    # --- 段落单调检测 ---
    paragraphs = [p.strip() for p in generated_text.split('\n') if p.strip()]
    if len(paragraphs) >= 6:
        lengths = [len(p) for p in paragraphs]
        avg_len = sum(lengths) / len(lengths) if lengths else 1
        # 计算连续段落长度差异是否过小
        monotone_streak = 0
        max_streak = 0
        for i in range(1, len(lengths)):
            diff_ratio = abs(lengths[i] - lengths[i - 1]) / max(avg_len, 1)
            if diff_ratio < 0.2:
                monotone_streak += 1
                max_streak = max(max_streak, monotone_streak)
            else:
                monotone_streak = 0
        if max_streak >= 5:
            issues.append(
                {
                    "dimension": "叙事节奏",
                    "severity": "low",
                    "description": f"连续 {max_streak + 1} 个段落长度过于接近，节奏感单调",
                    "suggestion": "尝试交替使用长短段落，紧张处用短句，舒缓处用长句",
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
            "quote": issue.get("quote", ""),
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
