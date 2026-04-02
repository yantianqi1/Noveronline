"""块内事实提取的行协议执行器。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .local_block_fact_protocol_prompts import build_local_block_protocol_prompt
from .local_block_fact_support import build_anchor_context, build_fingerprint_context, build_skeleton_context, extract_aliases, extract_world_rules
from .seed_line_protocol import (
    LineProtocolError,
    chapter_id_for_refs,
    evidence_spans,
    parse_csv_list,
    parse_kv_line,
    parse_positive_int,
    parse_sentence_ref_list,
    protocol_lines,
    sentence_texts,
)


SUMMARY_TASK = "threads"
SUBTASKS = ("events", "entities", "relationships", SUMMARY_TASK)


class LocalBlockFactLineProtocolExecutor:
    def __init__(self, client, prompt_budget_manager, sentence_map: Dict[str, Dict[str, object]]):
        self.client = client
        self.prompt_budget_manager = prompt_budget_manager
        self.sentence_map = sentence_map

    def extract(
        self,
        block: Dict[str, Any],
        owned: Sequence[Dict[str, Any]],
        context: Sequence[Dict[str, Any]],
        skeleton: Dict[str, Any] | None,
        blocks: Sequence[Dict[str, Any]],
        anchors: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        valid_sentence_ids = set(block.get("owned_sentence_ids", []) + block.get("context_sentence_ids", []))
        prompt_context = self._prompt_context(block, owned, context, skeleton, blocks, anchors)
        event_lines = self._call_subtask("events", prompt_context)
        entity_lines = self._call_subtask("entities", prompt_context)
        relationship_lines = self._call_subtask("relationships", prompt_context)
        thread_lines = self._call_subtask(SUMMARY_TASK, prompt_context)
        events = self._event_records(event_lines, valid_sentence_ids)
        entities = self._entity_records(entity_lines, valid_sentence_ids)
        relationships = self._relationship_records(relationship_lines, valid_sentence_ids)
        threads, summary_text, summary_refs = self._thread_and_summary_records(thread_lines, valid_sentence_ids)
        return {
            "block_id": block["block_id"],
            "owned_chapters": list(block["owned_chapter_ids"]),
            "context_chapters": list(block["context_chapter_ids"]),
            "local_events": events,
            "local_entities": entities,
            "local_relationship_changes": relationships,
            "local_threads": threads,
            "unresolved_refs": extract_aliases(f"{self._joined_text(owned)}\n{self._joined_text(context)}")["ambiguities"],
            "local_summary": summary_text or "；".join(item["summary"] for item in events[:2]),
            "local_summary_sentence_refs": summary_refs,
            "evidence_spans": evidence_spans(summary_refs or self._union_refs(events), self.sentence_map),
            "world_rules": extract_world_rules(self._joined_text(owned)),
            "generation_mode": "line_protocol",
        }

    def _call_subtask(self, task: str, prompt_context: str) -> List[str]:
        messages = [
            {"role": "system", "content": build_local_block_protocol_prompt(task)},
            {"role": "user", "content": f"## 子任务\n{task}\n\n{prompt_context}"},
        ]
        previous = ""
        for attempt in range(3):
            response = self.client.chat(messages=messages, temperature=max(0.1, 0.25 - attempt * 0.05), max_tokens=2200)
            try:
                return protocol_lines(response)
            except LineProtocolError:
                previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合行协议。只重新输出合法记录行，不要解释。"}]
        raise LineProtocolError(f"{task} 子任务连续三次未返回合法行协议")

    def _event_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> List[Dict[str, Any]]:
        records = []
        for index, line in enumerate(lines, start=1):
            payload = parse_kv_line(line, record_type="EVENT", required_keys=("summary", "characters", "organizations", "sentence_refs"))
            refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
            chapter_id = chapter_id_for_refs(refs, self.sentence_map)
            records.append(
                {
                    "event_id": f"{chapter_id}_event_{index:02d}",
                    "chapter_id": chapter_id,
                    "summary": payload["summary"],
                    "characters": parse_csv_list(payload["characters"]),
                    "organizations": parse_csv_list(payload["organizations"]),
                    "sentence_refs": refs,
                    "evidence": sentence_texts(refs, self.sentence_map, limit=3),
                }
            )
        return records

    def _entity_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> List[Dict[str, Any]]:
        records = []
        for line in lines:
            payload = parse_kv_line(line, record_type="ENTITY", required_keys=("name", "entity_type", "aliases", "summary", "importance_tier", "sentence_refs"))
            refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
            records.append(
                {
                    "name": payload["name"],
                    "entity_type": payload["entity_type"],
                    "aliases": parse_csv_list(payload["aliases"]),
                    "summary": payload["summary"],
                    "importance_tier": payload["importance_tier"],
                    "organization_type": "organization",
                    "sentence_refs": refs,
                    "evidence": sentence_texts(refs, self.sentence_map, limit=3),
                }
            )
        return records

    def _relationship_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> List[Dict[str, Any]]:
        records = []
        for line in lines:
            payload = parse_kv_line(line, record_type="REL", required_keys=("source", "target", "change", "weight", "sentence_refs"))
            refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
            records.append(
                {
                    "source": payload["source"],
                    "target": payload["target"],
                    "change": payload["change"],
                    "weight": parse_positive_int(payload["weight"]),
                    "chapter_id": chapter_id_for_refs(refs, self.sentence_map),
                    "sentence_refs": refs,
                    "evidence": sentence_texts(refs, self.sentence_map, limit=3),
                }
            )
        return records

    def _thread_and_summary_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> tuple[List[Dict[str, Any]], str, List[str]]:
        threads: List[Dict[str, Any]] = []
        summary_text = ""
        summary_refs: List[str] = []
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "THREAD":
                payload = parse_kv_line(line, record_type="THREAD", required_keys=("thread_key", "status", "summary", "sentence_refs"))
                refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
                threads.append(
                    {
                        "thread_key": payload["thread_key"],
                        "status": payload["status"],
                        "summary": payload["summary"],
                        "chapter_id": chapter_id_for_refs(refs, self.sentence_map),
                        "sentence_refs": refs,
                    }
                )
                continue
            payload = parse_kv_line(line, record_type="SUMMARY", required_keys=("text", "sentence_refs"))
            summary_text = payload["text"]
            summary_refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
        return threads, summary_text, summary_refs

    def _prompt_context(
        self,
        block: Dict[str, Any],
        owned: Sequence[Dict[str, Any]],
        context: Sequence[Dict[str, Any]],
        skeleton: Dict[str, Any] | None,
        blocks: Sequence[Dict[str, Any]],
        anchors: Sequence[Dict[str, Any]],
    ) -> str:
        return self.prompt_budget_manager.build_prompt(
            {
                "块信息": (
                    f"## 当前块\nblock_id: {block['block_id']}\n"
                    f"owned_chapters: {block['owned_chapter_ids']}\n"
                    f"context_chapters: {block['context_chapter_ids']}"
                ),
                "主块句子": f"## 主块句子\n{self._sentence_catalog(block.get('owned_sentence_ids', []))}",
                "上下文句子": f"## 上下文句子\n{self._sentence_catalog(block.get('context_sentence_ids', [])) or '无'}",
                "骨架": f"## 骨架角色\n{build_skeleton_context(block, skeleton)}",
                "锚点": f"## 前情锚点\n{build_anchor_context(block, anchors)}",
                "指纹": f"## 前文块章节指纹\n{build_fingerprint_context(block, blocks, skeleton)}",
            }
        )

    def _sentence_catalog(self, sentence_ids: Sequence[str]) -> str:
        return "\n".join(
            f"[{sentence_id}] {self.sentence_map[sentence_id]['text']}"
            for sentence_id in sentence_ids
            if sentence_id in self.sentence_map
        )

    def _joined_text(self, chapters: Sequence[Dict[str, Any]]) -> str:
        return "\n\n".join(str(item.get("content") or "") for item in chapters)

    def _union_refs(self, events: Sequence[Dict[str, Any]]) -> List[str]:
        refs: List[str] = []
        for item in events:
            for ref in item.get("sentence_refs", []):
                if ref not in refs:
                    refs.append(ref)
        return refs
