"""带故事记忆快照的块级分析服务。"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .contextual_block_line_protocol import ContextualBlockLineProtocolExecutor
from .llm_router import LlmRouter
from .prompt_budget_manager import PromptBudgetManager
from .sentence_atlas_builder import build_sentence_atlas, build_sentence_map
from .seed_stage_fallback_support import attach_rule_fallback, should_use_rule_fallback, summarize_stage_failure
from .seed_llm_payload_normalizer import normalize_contextual_block_payload
from .seed_stage_settings import SEED_STAGE_MAX_WORKERS


ACTIVE_HINTS = ("现身", "出手", "赶来", "指挥", "前往")
DEAD_HINTS = ("身死", "战死", "死去", "陨落", "坠亡", "丧命")
INJURED_HINTS = ("受伤", "重伤", "负伤", "流血")
MISSING_HINTS = ("失踪", "下落不明", "消失")
logger = logging.getLogger(__name__)

CONTEXTUAL_BLOCK_SYSTEM_PROMPT = """你是一名小说结构分析师。

请基于"前情快照 + 当前主块正文 + 边界上下文"分析当前块，只输出主块章节的最终判断。

分析重点：
- 当前块如何承接前情（因果关系，而非简单重述前文）
- 块内角色的状态变化是否有原文支撑
- 块结束时哪些线索处于悬而未决的状态

你必须直接输出严格有效的 JSON 对象，不要输出任何额外解释、不要用 markdown 代码块包裹。
JSON 结构必须严格遵循以下格式：

{
  "plot_summary": "80-150字，三段式结构：[承接] 上一块的XX导致了... [推进] 当前块中... [悬念] 块末留下了...",
  "character_state_updates": [
    {
      "name": "角色名",
      "state": "active 或 dead 或 injured 或 missing",
      "evidence": ["状态佐证原文，从正文逐字引用，15-60字"]
    }
  ],
  "relationship_updates": [
    {
      "source": "主动方",
      "target": "被动方",
      "state": "ally 或 conflict 或 co_occurrence 或 mentor 或 betrayal 或 reunion",
      "evidence": ["关系变化佐证原文，逐字引用"]
    }
  ],
  "thread_updates": [
    {
      "thread_key": "线索关键词，8-20字",
      "status": "open 或 closed 或 progressed",
      "summary": "线索进展描述，30-60字"
    }
  ],
  "block_end_state": {
    "focus_characters": ["当前块结束时最重要的2-4个角色"],
    "focus_organizations": ["当前块结束时最相关的组织"],
    "open_threads": ["块结束时仍未关闭的线索"],
    "narrative_momentum": "当前块的叙事动力方向，20-40字，描述剧情下一步最可能的走向",
    "summary": "30-60字，块结束时的态势概括——聚焦于'接下来会怎样'而非'发生了什么'，不要照抄plot_summary"
  }
}

thread_updates.status 使用标准：
- open：新出现的悬念或线索
- progressed：本块中有推进但未完全解决的旧线索
- closed：在本块中明确得到解答或终结的线索

严格禁止：
- block_end_state.summary 不要照抄 plot_summary，两者必须有差异
- character_state_updates 只输出本块中状态发生了变化的角色，不要罗列所有出场角色
- evidence 必须逐字引用原文，不要改写或概括

## 输出示范
{
  "plot_summary": "承接前文柳如烟中毒后，沈渊携其赶回苍澜宗求医。途中遭遇暗影组织伏击，沈渊被迫使用古卷中的禁术击退敌人，但禁术的反噬让他短暂失去意识。柳如烟在昏迷中喃喃说出一个陌生名字，暗示其隐藏身份。",
  "character_state_updates": [
    {"name": "沈渊", "state": "injured", "evidence": ["禁术的反噬让沈渊口吐鲜血，双目暂时失明"]},
    {"name": "柳如烟", "state": "injured", "evidence": ["毒液已蔓延至肩部，柳如烟持续高烧昏迷"]}
  ],
  "relationship_updates": [
    {"source": "暗影组织", "target": "沈渊", "state": "conflict", "evidence": ["为首的黑衣人冷笑道：'沈渊，交出古卷，否则你们都得死在这里'"]}
  ],
  "thread_updates": [
    {"thread_key": "古卷禁术副作用", "status": "progressed", "summary": "沈渊首次使用古卷中的禁术，证实其有强大威力但伴随严重的身体反噬"},
    {"thread_key": "柳如烟隐藏身份", "status": "open", "summary": "柳如烟昏迷中喃喃说出陌生名字，暗示其真实身份另有隐情"}
  ],
  "block_end_state": {
    "focus_characters": ["沈渊", "柳如烟"],
    "focus_organizations": ["暗影组织", "苍澜宗"],
    "open_threads": ["古卷禁术副作用", "柳如烟隐藏身份", "暗影组织追杀动机"],
    "narrative_momentum": "沈渊急需回宗救治柳如烟，但禁术副作用和暗影组织追击形成双重压力",
    "summary": "沈渊暂时失明体力透支，柳如烟仍在昏迷，两人处于极度脆弱状态，暗影组织可能再次追击"
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
        sentence_atlas: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if sentence_atlas is None:
            _, sentence_atlas = build_sentence_atlas(chapters)
        packet_map = {item["block_id"]: item for item in local_block_facts}
        snapshot_map = {item["block_id"]: item for item in snapshots}
        chapter_map = {item["chapter_id"]: item for item in chapters}
        sentence_map = build_sentence_map(sentence_atlas)
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(len(blocks), 1))) as executor:
            futures = [
                executor.submit(
                    self._analyze_block,
                    block,
                    packet_map[block["block_id"]],
                    snapshot_map[block["block_id"]],
                    chapter_map,
                    sentence_map,
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
        sentence_map: Dict[str, Dict[str, Any]],
        use_llm: bool,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        if progress_callback:
            progress_callback("start", block)
        if use_llm:
            payload = self._analyze_with_llm(block, packet, snapshot, chapter_map, sentence_map)
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
                "narrative_momentum": "",
                "summary": plot_summary,
            },
        }

    def _analyze_with_llm(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
        sentence_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
        if hasattr(client, "chat"):
            return ContextualBlockLineProtocolExecutor(client, self.prompt_budget_manager, sentence_map).analyze(
                block,
                packet,
                snapshot,
                chapter_map,
            )
        return self._analyze_with_legacy_json(block, packet, snapshot, chapter_map)

    def _analyze_with_legacy_json(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
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
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            logger.warning("剧情块分析转为规则回退 (%s): %s", block["block_id"], summarize_stage_failure(exc))
            return attach_rule_fallback(self._analyze_offline(block, packet, snapshot), exc)

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
