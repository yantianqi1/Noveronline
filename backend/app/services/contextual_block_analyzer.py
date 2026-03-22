"""带故事记忆快照的块级分析服务。"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .prompt_budget_manager import PromptBudgetManager
from .seed_llm_payload_normalizer import normalize_contextual_block_payload
from .seed_stage_settings import SEED_STAGE_MAX_WORKERS


ACTIVE_HINTS = ("现身", "出手", "赶来", "指挥", "前往")
DEAD_HINTS = ("身死", "战死", "死去", "陨落", "坠亡", "丧命")
INJURED_HINTS = ("受伤", "重伤", "负伤", "流血")
MISSING_HINTS = ("失踪", "下落不明", "消失")

CONTEXTUAL_BLOCK_SYSTEM_PROMPT = """你是一名小说结构分析师。

请基于"前情快照 + 当前主块正文 + 边界上下文"分析当前块，只输出主块章节的最终判断。

你必须直接输出严格有效的 JSON 对象，不要输出任何额外解释、不要用 markdown 代码块包裹。
JSON 结构必须严格遵循以下示例格式：

{
  "plot_summary": "承接前情与当前块的剧情概要",
  "character_state_updates": [
    {
      "name": "角色名",
      "state": "active 或 dead 或 injured 或 missing",
      "evidence": ["状态佐证原文"]
    }
  ],
  "relationship_updates": [
    {
      "source": "实体A",
      "target": "实体B",
      "state": "ally 或 conflict 或 co_occurrence",
      "evidence": ["关系变化佐证原文"]
    }
  ],
  "thread_updates": [
    {
      "thread_key": "线索关键词",
      "status": "open 或 closed 或 progressed",
      "summary": "线索进展描述"
    }
  ],
  "block_end_state": {
    "focus_characters": ["核心角色A", "核心角色B"],
    "focus_organizations": ["核心组织"],
    "open_threads": ["未关闭的线索1", "未关闭的线索2"],
    "summary": "块结束时的整体态势概括"
  }
}
"""


class ContextualBlockAnalyzer:
    """使用前情快照补齐块级剧情分析。"""

    MODULE_KEY = "contextual_block_analysis"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
        prompt_budget_manager: Optional[PromptBudgetManager] = None,
        max_workers: int = SEED_STAGE_MAX_WORKERS,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()
        self.prompt_budget_manager = prompt_budget_manager or PromptBudgetManager()
        self.max_workers = max_workers

    def analyze_blocks(
        self,
        blocks: Sequence[Dict[str, Any]],
        local_block_facts: Sequence[Dict[str, Any]],
        snapshots: Sequence[Dict[str, Any]],
        chapters: Sequence[Dict[str, Any]],
        use_llm: bool,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        packet_map = {item["block_id"]: item for item in local_block_facts}
        snapshot_map = {item["block_id"]: item for item in snapshots}
        chapter_map = {item["chapter_id"]: item for item in chapters}
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(len(blocks), 1))) as executor:
            futures = [
                executor.submit(
                    self._analyze_block,
                    block,
                    packet_map[block["block_id"]],
                    snapshot_map[block["block_id"]],
                    chapter_map,
                    use_llm,
                    progress_callback,
                )
                for block in blocks
            ]
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: item["block_id"])
        return {"block_count": len(results), "blocks": results}

    def _analyze_block(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
        use_llm: bool,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        if progress_callback:
            progress_callback("start", block)
        if use_llm:
            payload = self._analyze_with_llm(block, packet, snapshot, chapter_map)
        else:
            payload = self._analyze_offline(block, packet, snapshot)
        if progress_callback:
            progress_callback("complete", block)
        return payload

    def _analyze_offline(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        plot_summary = self._plot_summary(packet, snapshot)
        character_state_updates = self._character_state_updates(packet)
        relationship_updates = [
            {
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "state": item.get("change", "co_occurrence"),
                "evidence": item.get("evidence", [])[:2],
            }
            for item in packet.get("local_relationship_changes", [])
        ]
        thread_updates = [
            {
                "thread_key": item.get("thread_key", ""),
                "status": item.get("status", "open"),
                "summary": item.get("summary", ""),
            }
            for item in packet.get("local_threads", [])
        ]
        return {
            "block_id": block["block_id"],
            "plot_summary": plot_summary,
            "character_state_updates": character_state_updates,
            "relationship_updates": relationship_updates,
            "thread_updates": thread_updates,
            "block_end_state": {
                "focus_characters": [item["name"] for item in packet.get("local_entities", []) if item.get("entity_type") == "character"][:6],
                "focus_organizations": [item["name"] for item in packet.get("local_entities", []) if item.get("entity_type") == "organization"][:4],
                "open_threads": [item.get("thread_key", "") for item in packet.get("local_threads", []) if item.get("status", "open") != "closed"][:6],
                "summary": plot_summary,
            },
        }

    def _analyze_with_llm(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
        owned_text = self._chapter_text(block["owned_chapter_ids"], chapter_map)
        context_text = self._chapter_text(block["context_chapter_ids"], chapter_map)
        user_message = self.prompt_budget_manager.build_prompt(
            {
                "前情快照": f"block_id: {block['block_id']}\n## 前情快照\n{json.dumps(snapshot, ensure_ascii=False)}",
                "块内事实": f"## 局部事实\n{json.dumps(packet, ensure_ascii=False)}",
                "主块正文": f"## 主块正文\n{owned_text}",
                "上下文章节": f"## 边界上下文\n{context_text or '无'}",
            }
        )
        payload = client.chat_json_value(
            messages=[
                {"role": "system", "content": CONTEXTUAL_BLOCK_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        payload = normalize_json_object(payload, "前情快照剧情分析")
        normalized = normalize_contextual_block_payload(payload, packet)
        normalized["block_id"] = block["block_id"]
        return normalized

    def _plot_summary(self, packet: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
        lead = snapshot.get("recent_blocks", [])
        head = f"承接前情：{lead[-1]['summary']}" if lead else "剧情起点：当前块开始推进新的主线。"
        return f"{head} 当前块推进：{packet.get('local_summary', '')}".strip()

    def _character_state_updates(self, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        updates = []
        evidence_by_name = self._character_evidence(packet)
        for name, evidence in evidence_by_name.items():
            state = self._infer_state(evidence)
            updates.append({"name": name, "state": state, "evidence": evidence[:2]})
        return updates

    def _character_evidence(self, packet: Dict[str, Any]) -> Dict[str, List[str]]:
        evidence_map: Dict[str, List[str]] = {}
        for event in packet.get("local_events", []):
            for name in event.get("characters", []):
                evidence_map.setdefault(name, []).extend(event.get("evidence", [])[:2])
        return evidence_map

    def _infer_state(self, evidence: Sequence[str]) -> str:
        joined = " ".join(evidence)
        if any(item in joined for item in DEAD_HINTS):
            return "dead"
        if any(item in joined for item in INJURED_HINTS):
            return "injured"
        if any(item in joined for item in MISSING_HINTS):
            return "missing"
        if any(item in joined for item in ACTIVE_HINTS):
            return "active"
        return "active"

    def _chapter_text(
        self,
        chapter_ids: Sequence[str],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> str:
        return "\n\n".join(
            f"### {chapter_map[item].get('title', item)}\n{chapter_map[item]['content']}"
            for item in chapter_ids
            if item in chapter_map
        )
