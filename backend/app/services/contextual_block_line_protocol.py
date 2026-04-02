"""剧情块分析的行协议执行器。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .contextual_block_protocol_prompts import build_contextual_block_protocol_prompt
from .seed_line_protocol import (
    chapter_id_for_refs,
    parse_csv_list,
    parse_kv_line,
    parse_sentence_ref_list,
    protocol_lines,
    sentence_texts,
)


SUBTASKS = ("plot_summary", "state_updates", "thread_updates")


class ContextualBlockLineProtocolExecutor:
    def __init__(self, client, prompt_budget_manager, sentence_map: Dict[str, Dict[str, object]]):
        self.client = client
        self.prompt_budget_manager = prompt_budget_manager
        self.sentence_map = sentence_map

    def analyze(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        valid_sentence_ids = set(block.get("owned_sentence_ids", []) + block.get("context_sentence_ids", []))
        prompt_context = self._prompt_context(block, packet, snapshot, chapter_map)
        summary_lines = self._call_subtask("plot_summary", prompt_context)
        state_lines = self._call_subtask("state_updates", prompt_context)
        thread_lines = self._call_subtask("thread_updates", prompt_context)
        plot_summary, plot_refs = self._summary_record(summary_lines, valid_sentence_ids)
        char_updates, rel_updates, end_state = self._state_records(state_lines, valid_sentence_ids)
        thread_updates = self._thread_records(thread_lines, valid_sentence_ids)
        return {
            "block_id": block["block_id"],
            "plot_summary": plot_summary,
            "plot_summary_sentence_refs": plot_refs,
            "character_state_updates": char_updates,
            "relationship_updates": rel_updates,
            "thread_updates": thread_updates,
            "block_end_state": end_state,
            "generation_mode": "line_protocol",
        }

    def _call_subtask(self, task: str, prompt_context: str) -> List[str]:
        messages = [
            {"role": "system", "content": build_contextual_block_protocol_prompt(task)},
            {"role": "user", "content": f"## 子任务\n{task}\n\n{prompt_context}"},
        ]
        previous = ""
        for attempt in range(3):
            response = self.client.chat(messages=messages, temperature=max(0.1, 0.25 - attempt * 0.05), max_tokens=2200)
            try:
                return protocol_lines(response)
            except ValueError:
                previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合行协议。只重新输出合法记录行，不要解释。"}]
        raise ValueError(f"{task} 子任务连续三次未返回合法行协议")

    def _summary_record(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> tuple[str, List[str]]:
        if not lines:
            return "", []
        payload = parse_kv_line(lines[0], record_type="SUMMARY", required_keys=("text", "sentence_refs"))
        refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
        return payload["text"], refs

    def _state_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        char_updates: List[Dict[str, Any]] = []
        rel_updates: List[Dict[str, Any]] = []
        end_state = {"focus_characters": [], "focus_organizations": [], "open_threads": [], "narrative_momentum": "", "summary": "", "sentence_refs": []}
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "CHAR_STATE":
                payload = parse_kv_line(line, record_type="CHAR_STATE", required_keys=("name", "state", "sentence_refs"))
                refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
                char_updates.append({"name": payload["name"], "state": payload["state"], "sentence_refs": refs, "evidence": sentence_texts(refs, self.sentence_map, limit=2)})
                continue
            if record_type == "REL_STATE":
                payload = parse_kv_line(line, record_type="REL_STATE", required_keys=("source", "target", "state", "sentence_refs"))
                refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
                rel_updates.append({"source": payload["source"], "target": payload["target"], "state": payload["state"], "sentence_refs": refs, "evidence": sentence_texts(refs, self.sentence_map, limit=2)})
                continue
            payload = parse_kv_line(line, record_type="END_STATE", required_keys=("focus_characters", "focus_organizations", "open_threads", "narrative_momentum", "summary", "sentence_refs"))
            refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
            end_state = {
                "focus_characters": parse_csv_list(payload["focus_characters"]),
                "focus_organizations": parse_csv_list(payload["focus_organizations"]),
                "open_threads": parse_csv_list(payload["open_threads"]),
                "narrative_momentum": payload["narrative_momentum"],
                "summary": payload["summary"],
                "sentence_refs": refs,
            }
        return char_updates, rel_updates, end_state

    def _thread_records(self, lines: Sequence[str], valid_sentence_ids: Sequence[str]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for line in lines:
            payload = parse_kv_line(line, record_type="THREAD_UPDATE", required_keys=("thread_key", "status", "summary", "sentence_refs"))
            refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=valid_sentence_ids)
            records.append(
                {
                    "thread_key": payload["thread_key"],
                    "status": payload["status"],
                    "summary": payload["summary"],
                    "chapter_id": chapter_id_for_refs(refs, self.sentence_map),
                    "sentence_refs": refs,
                }
            )
        return records

    def _prompt_context(
        self,
        block: Dict[str, Any],
        packet: Dict[str, Any],
        snapshot: Dict[str, Any],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> str:
        owned_text = self._chapter_text(block.get("owned_chapter_ids", []), chapter_map)
        context_text = self._chapter_text(block.get("context_chapter_ids", []), chapter_map)
        return self.prompt_budget_manager.build_prompt(
            {
                "块信息": f"## 块信息\nblock_id: {block['block_id']}",
                "前情快照": f"## 前情快照\n{snapshot}",
                "局部事实": f"## 局部事实\n{packet}",
                "主块句子": f"## 主块句子\n{self._sentence_catalog(block.get('owned_sentence_ids', []))}",
                "上下文句子": f"## 上下文句子\n{self._sentence_catalog(block.get('context_sentence_ids', [])) or '无'}",
                "原文辅助": f"## 主块正文\n{owned_text}\n\n## 边界上下文\n{context_text or '无'}",
            }
        )

    def _sentence_catalog(self, sentence_ids: Sequence[str]) -> str:
        return "\n".join(
            f"[{sentence_id}] {self.sentence_map[sentence_id]['text']}"
            for sentence_id in sentence_ids
            if sentence_id in self.sentence_map
        )

    def _chapter_text(self, chapter_ids: Sequence[str], chapter_map: Dict[str, Dict[str, Any]]) -> str:
        return "\n\n".join(
            f"### {chapter_map[item].get('title', item)}\n{chapter_map[item]['content']}"
            for item in chapter_ids
            if item in chapter_map
        )
