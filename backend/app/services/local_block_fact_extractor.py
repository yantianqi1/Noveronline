"""块级局部事实提取服务。"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .local_block_fact_line_protocol import LocalBlockFactLineProtocolExecutor
from .local_block_fact_prompts import LOCAL_BLOCK_SYSTEM_PROMPT
from .local_block_fact_support import (
    build_anchor_context,
    build_chapter_text,
    build_fingerprint_context,
    build_skeleton_context,
    extract_aliases,
    extract_world_rules,
    split_sentences,
)
from .novel_seed_analyzer import NovelSeedAnalyzer
from .prompt_budget_manager import PromptBudgetManager
from .sentence_atlas_builder import build_sentence_atlas, build_sentence_map
from .seed_llm_retry import call_with_seed_llm_retry
from .seed_llm_payload_normalizer import normalize_local_block_payload
from .seed_stage_fallback_support import attach_rule_fallback, should_use_rule_fallback, summarize_stage_failure
from .seed_stage_settings import BLOCK_BATCH_SIZE, LLM_CONCURRENT_LIMIT, SEED_STAGE_MAX_WORKERS


SUMMARY_SENTENCE_COUNT = 2
MAX_LOCAL_CHARACTER_ENTITY_COUNT = 12
MAX_LOCAL_ORGANIZATION_ENTITY_COUNT = 8
MAX_LOCAL_RELATIONSHIP_CHANGE_COUNT = 20
logger = logging.getLogger(__name__)


class LocalBlockFactExtractor:
    """提取块内可证实的事件、实体、关系与线索。"""

    MODULE_KEY = "local_block_facts"

    def __init__(
        self,
        analyzer: Optional[NovelSeedAnalyzer] = None,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
        prompt_budget_manager: Optional[PromptBudgetManager] = None,
        max_workers: int = SEED_STAGE_MAX_WORKERS,
        block_batch_size: int = BLOCK_BATCH_SIZE,
        llm_concurrent_limit: int = LLM_CONCURRENT_LIMIT,
    ):
        self.analyzer = analyzer or NovelSeedAnalyzer()
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()
        self.prompt_budget_manager = prompt_budget_manager or PromptBudgetManager()
        self.max_workers = max_workers
        self.block_batch_size = block_batch_size
        self.llm_concurrent_limit = llm_concurrent_limit

    def extract_blocks(
        self,
        blocks: Sequence[Dict[str, Any]],
        chapters: Sequence[Dict[str, Any]],
        use_llm: bool,
        skeleton: Optional[Dict[str, Any]] = None,
        anchors: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        sentence_atlas: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if sentence_atlas is None:
            _, sentence_atlas = build_sentence_atlas(chapters)
        chapter_map = {item["chapter_id"]: item for item in chapters}
        sentence_map = build_sentence_map(sentence_atlas)
        packets: List[Dict[str, Any]] = []
        for batch in self._block_batches(blocks):
            if not use_llm:
                packets.extend(
                    self._extract_batch(
                        batch,
                        chapter_map,
                        use_llm,
                        progress_callback,
                        skeleton,
                        blocks,
                        anchors or {},
                    )
                )
                continue
            packets.extend(
                self._extract_batch(
                    batch,
                    chapter_map,
                    use_llm,
                    progress_callback,
                    skeleton,
                    blocks,
                    anchors or {},
                    sentence_map=sentence_map,
                )
            )
        packets.sort(key=lambda item: item["block_id"])
        return {"block_count": len(packets), "packets": packets}

    def _block_batches(self, blocks: Sequence[Dict[str, Any]]) -> List[Sequence[Dict[str, Any]]]:
        return [
            blocks[index:index + self.block_batch_size]
            for index in range(0, len(blocks), self.block_batch_size)
        ]

    def _extract_batch(
        self,
        batch: Sequence[Dict[str, Any]],
        chapter_map: Dict[str, Dict[str, Any]],
        use_llm: bool,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]],
        skeleton: Optional[Dict[str, Any]],
        blocks: Sequence[Dict[str, Any]],
        anchors: Dict[str, Any],
        sentence_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        packets: List[Dict[str, Any]] = []
        client = self._resolve_llm_client() if use_llm else None
        active_sentence_map = sentence_map or {}
        worker_limit = self._worker_limit(use_llm, len(batch), client)
        with ThreadPoolExecutor(max_workers=min(worker_limit, max(len(batch), 1))) as executor:
            futures = [
                executor.submit(
                    self._extract_block,
                    block,
                    chapter_map,
                    active_sentence_map,
                    use_llm,
                    progress_callback,
                    skeleton,
                    blocks,
                    anchors,
                    client,
                )
                for block in batch
            ]
            for future in as_completed(futures):
                packets.append(future.result())
        return packets

    def _resolve_llm_client(self) -> LLMClient:
        return self.llm_client or self.llm_router.build_client(self.MODULE_KEY)

    def _worker_limit(self, use_llm: bool, batch_size: int, client: Optional[LLMClient]) -> int:
        if not use_llm:
            return self.max_workers
        client_limit = int(getattr(client, "max_concurrency", self.llm_concurrent_limit) or self.llm_concurrent_limit)
        return max(1, min(batch_size, self.llm_concurrent_limit, client_limit))

    def _extract_block(
        self,
        block: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
        sentence_map: Dict[str, Dict[str, Any]],
        use_llm: bool,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]],
        skeleton: Optional[Dict[str, Any]],
        blocks: Sequence[Dict[str, Any]],
        anchors: Dict[str, Any],
        client: Optional[LLMClient],
    ) -> Dict[str, Any]:
        if progress_callback:
            progress_callback("start", block)
        owned = [chapter_map[item] for item in block["owned_chapter_ids"]]
        context = [chapter_map[item] for item in block["context_chapter_ids"]]
        if use_llm:
            payload = self._extract_with_llm(
                block,
                owned,
                context,
                skeleton,
                blocks,
                anchors.get("anchors", []),
                sentence_map,
                client,
            )
        else:
            payload = self._extract_offline(block, owned, context, sentence_map)
        if progress_callback:
            progress_callback("complete", block)
        return payload

    def _extract_offline(
        self,
        block: Dict[str, Any],
        owned: Sequence[Dict[str, Any]],
        context: Sequence[Dict[str, Any]],
        sentence_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        owned_text = "\n\n".join(item["content"] for item in owned)
        context_text = "\n\n".join(item["content"] for item in context)
        analysis = self.analyzer.analyze_text(owned_text)
        alias_data = extract_aliases(owned_text + "\n" + context_text)
        local_entities = self._build_entities(analysis, alias_data)
        local_events = [self._chapter_event(item) for item in owned]
        local_threads = [self._thread_from_event(item) for item in local_events]
        local_summary = " ".join(item["summary"] for item in local_events[:SUMMARY_SENTENCE_COUNT]).strip()
        return {
            "block_id": block["block_id"],
            "owned_chapters": list(block["owned_chapter_ids"]),
            "context_chapters": list(block["context_chapter_ids"]),
            "local_events": local_events,
            "local_entities": local_entities,
            "local_relationship_changes": self._relationship_changes(analysis),
            "local_threads": local_threads,
            "unresolved_refs": alias_data["ambiguities"],
            "local_summary": local_summary or "当前块未提炼出明确主线。",
            "local_summary_sentence_refs": self._refs_from_chapters(owned),
            "evidence_spans": self._evidence_spans(local_events),
            "world_rules": extract_world_rules(owned_text),
        }

    def _extract_with_llm(
        self,
        block: Dict[str, Any],
        owned: Sequence[Dict[str, Any]],
        context: Sequence[Dict[str, Any]],
        skeleton: Optional[Dict[str, Any]],
        blocks: Sequence[Dict[str, Any]],
        anchors: Sequence[Dict[str, Any]],
        sentence_map: Dict[str, Dict[str, Any]],
        client: Optional[LLMClient],
    ) -> Dict[str, Any]:
        if client is None:
            raise ValueError("LLM 模式缺少可用客户端")
        if hasattr(client, "chat"):
            return LocalBlockFactLineProtocolExecutor(client, self.prompt_budget_manager, sentence_map).extract(
                block,
                owned,
                context,
                skeleton,
                blocks,
                anchors,
            )
        return self._extract_with_legacy_json(block, owned, context, skeleton, blocks, anchors, client)

    def _extract_with_legacy_json(
        self,
        block: Dict[str, Any],
        owned: Sequence[Dict[str, Any]],
        context: Sequence[Dict[str, Any]],
        skeleton: Optional[Dict[str, Any]],
        blocks: Sequence[Dict[str, Any]],
        anchors: Sequence[Dict[str, Any]],
        client: Optional[LLMClient],
    ) -> Dict[str, Any]:
        try:
            owned_text = build_chapter_text(owned)
            context_text = build_chapter_text(context)
            skeleton_context = build_skeleton_context(block, skeleton)
            anchor_context = build_anchor_context(block, anchors)
            fingerprint_context = build_fingerprint_context(block, blocks, skeleton)
            user_message = self.prompt_budget_manager.build_prompt(
                {
                    "骨架角色列表": f"## 全文角色/组织骨架（正则预扫描结果，供参考）\n{skeleton_context}\n\nblock_id: {block['block_id']}\nowned_chapters: {block['owned_chapter_ids']}\ncontext_chapters: {block['context_chapter_ids']}",
                    "锚点世界状态": f"## 前情锚点摘要\n{anchor_context}",
                    "章节指纹": f"## 前文块章节指纹\n{fingerprint_context}",
                    "主块正文": f"## 主块正文\n{owned_text}",
                    "上下文章节": f"## 上下文章节\n{context_text or '无'}",
                }
            )
            payload = call_with_seed_llm_retry(
                lambda: client.chat_json_value(
                    messages=[
                        {"role": "system", "content": LOCAL_BLOCK_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                ),
                stage_label="块内事实提取",
                target_label=block["block_id"],
            )
            payload = normalize_json_object(payload, "块内局部事实提取")
            analysis = self.analyzer.analyze_text(owned_text)
            normalized = normalize_local_block_payload(
                payload,
                analysis,
                block["owned_chapter_ids"],
            )
            normalized["block_id"] = block["block_id"]
            normalized["owned_chapters"] = list(block["owned_chapter_ids"])
            normalized["context_chapters"] = list(block["context_chapter_ids"])
            return normalized
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            logger.warning("块内事实提取转为规则回退 (%s): %s", block["block_id"], summarize_stage_failure(exc))
            return attach_rule_fallback(self._extract_offline(block, owned, context), exc)

    def _chapter_event(self, chapter: Dict[str, Any]) -> Dict[str, Any]:
        sentences = split_sentences(chapter["content"])
        analysis = self.analyzer.analyze_text(chapter["content"])
        summary = "；".join(sentences[:SUMMARY_SENTENCE_COUNT]) or chapter.get("title", chapter["chapter_id"])
        sentence_refs = list(chapter.get("sentence_ids", [])[:SUMMARY_SENTENCE_COUNT])
        return {
            "event_id": f"{chapter['chapter_id']}_event",
            "chapter_id": chapter["chapter_id"],
            "summary": summary,
            "characters": [item["name"] for item in analysis["characters"][:6]],
            "organizations": [item["name"] for item in analysis["organizations"][:4]],
            "sentence_refs": sentence_refs,
            "evidence": [item for item in sentences[:SUMMARY_SENTENCE_COUNT]],
        }

    def _build_entities(self, analysis: Dict[str, Any], alias_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        alias_map = alias_data["aliases"]
        characters = [
            {
                "name": item["name"],
                "entity_type": "character",
                "aliases": sorted(alias_map.get(item["name"], [])),
                "summary": item.get("profile_summary", ""),
                "importance_tier": item.get("importance_tier", "supporting"),
                "sentence_refs": [],
                "evidence": item.get("evidence", [])[:3],
            }
            for item in analysis["characters"][:MAX_LOCAL_CHARACTER_ENTITY_COUNT]
        ]
        organizations = [
            {
                "name": item["name"],
                "entity_type": "organization",
                "aliases": [],
                "summary": item.get("summary", ""),
                "importance_tier": item.get("importance_tier", "major"),
                "organization_type": item.get("organization_type", "organization"),
                "sentence_refs": [],
                "evidence": item.get("evidence", [])[:3],
            }
            for item in analysis["organizations"][:MAX_LOCAL_ORGANIZATION_ENTITY_COUNT]
        ]
        return characters + organizations

    def _relationship_changes(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "change": item.get("relation_type", "co_occurrence"),
                "weight": item.get("weight", 1),
                "sentence_refs": [],
                "evidence": item.get("evidence", [])[:3],
            }
            for item in analysis["relations"][:MAX_LOCAL_RELATIONSHIP_CHANGE_COUNT]
            if item.get("source") and item.get("target")
        ]

    def _thread_from_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "thread_key": event["summary"][:40],
            "status": "open",
            "summary": event["summary"],
            "chapter_id": event["chapter_id"],
            "sentence_refs": list(event.get("sentence_refs", [])),
        }

    def _evidence_spans(self, local_events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        spans = []
        for event in local_events:
            for snippet in event.get("evidence", [])[:2]:
                spans.append({"chapter_id": event["chapter_id"], "snippet": snippet})
        return spans[:12]

    def _refs_from_chapters(self, chapters: Sequence[Dict[str, Any]]) -> List[str]:
        refs: List[str] = []
        for chapter in chapters:
            for sentence_id in chapter.get("sentence_ids", [])[:2]:
                if sentence_id not in refs:
                    refs.append(sentence_id)
        return refs[:4]
