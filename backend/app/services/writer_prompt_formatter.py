"""写作上下文 prompt 渲染。"""

from __future__ import annotations

from typing import Any, Dict, List


RELATIONSHIP_CATEGORIES = {"relationship", "runtime_memory", "pov_state"}
CONTINUITY_CATEGORIES = {"continuity_bridge", "open_thread"}


class WriterPromptFormatter:
    def format(self, pack: Dict[str, Any]) -> str:
        canon_must_know = self._canon_items(pack.get("must_know", []))
        canon_should_know = self._canon_items(pack.get("should_know", []))
        relationship_items, continuity_items = self._split_should_know(canon_should_know)
        sections = [
            self._section("写作目标", [self._goal_line(pack["context_scope"])]),
            self._section("必须延续的事实", self._item_lines(canon_must_know)),
            self._section("当前人物与关系", self._item_lines(relationship_items)),
            self._section("开放线索与连续性", self._item_lines(continuity_items)),
            self._section("风险提示", self._item_lines(self._canon_items(pack.get("warnings", [])))),
            self._section("候选场景", self._scene_lines(pack.get("scene_candidates", []))),
            self._section("可参考候选设定", self._candidate_lines(pack)),
        ]
        return "\n\n".join(section for section in sections if section).strip()

    def _goal_line(self, scope: Dict[str, Any]) -> str:
        chapter_text = scope.get("chapter_id") or scope.get("branch_id") or "当前范围"
        goal = scope.get("writing_goal") or "生成可继续写作的场景卡"
        pov = scope.get("pov_character") or "未指定 POV"
        return f"- 范围：{chapter_text} | POV：{pov} | 目标：{goal}"

    def _section(self, title: str, lines: List[str]) -> str:
        content = "\n".join(line for line in lines if line)
        return f"## {title}\n{content or '- 暂无'}"

    def _item_lines(self, items: List[Dict[str, Any]]) -> List[str]:
        return [f"- {item.get('summary', '')} | 用途：{item.get('why_it_matters', '')}" for item in items]

    def _scene_lines(self, scenes: List[Dict[str, Any]]) -> List[str]:
        return [
            f"- {item.get('title', '')}：{item.get('setup', '')}；张力：{item.get('tension', '')}；为何现在：{item.get('why_now', '')}"
            for item in scenes
        ]

    def _candidate_lines(self, pack: Dict[str, Any]) -> List[str]:
        if not pack["context_scope"].get("include_candidates"):
            return ["- 默认不注入 candidate 设定。"]
        items = self._candidate_items(pack)
        return [f"- {item.get('summary', '')} | 用途：{item.get('why_it_matters', '')} | 标记：非 canon" for item in items] or ["- 当前没有 candidate 设定。"]

    def _split_should_know(self, items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        relationship_items = []
        continuity_items = []
        for item in items:
            if item.get("category") in RELATIONSHIP_CATEGORIES:
                relationship_items.append(item)
                continue
            if item.get("category") in CONTINUITY_CATEGORIES:
                continuity_items.append(item)
                continue
            continuity_items.append(item)
        return relationship_items, continuity_items

    def _canon_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [item for item in items if item.get("memory_layer", "canon") != "candidate"]

    def _candidate_items(self, pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for item in pack.get("must_know", []) + pack.get("should_know", []):
            if item.get("memory_layer") == "candidate":
                items.append(item)
        return items
