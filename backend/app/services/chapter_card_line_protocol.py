"""章节卡的行协议执行器。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .chapter_card_protocol_prompts import build_chapter_card_protocol_prompt
from .seed_line_protocol import parse_kv_line, parse_sentence_ref_list, protocol_lines


class ChapterCardLineProtocolExecutor:
    def __init__(self, client, sentence_ids: Sequence[str]):
        self.client = client
        self.valid_sentence_ids = list(sentence_ids)

    def generate(self, user_prompt: str) -> Dict[str, Any]:
        summary_lines = self._call_subtask("summary", user_prompt)
        event_lines = self._call_subtask("events_threads", user_prompt)
        entity_lines = self._call_subtask("entities_states", user_prompt)
        payload = self._summary_payload(summary_lines)
        payload["key_events"], payload["open_threads"] = self._event_payload(event_lines)
        (
            payload["character_state_updates"],
            payload["relationship_updates"],
            payload["key_entities"],
        ) = self._entity_payload(entity_lines)
        return payload

    def _call_subtask(self, task: str, user_prompt: str) -> List[str]:
        messages = [
            {"role": "system", "content": build_chapter_card_protocol_prompt(task)},
            {"role": "user", "content": f"## 子任务\n{task}\n\n{user_prompt}"},
        ]
        previous = ""
        for attempt in range(3):
            response = self.client.chat(messages=messages, temperature=max(0.1, 0.25 - attempt * 0.05), max_tokens=1800)
            try:
                lines = protocol_lines(response)
                if task == "summary":
                    self._summary_payload(lines)
                elif task == "events_threads":
                    self._event_payload(lines)
                else:
                    self._entity_payload(lines)
                return lines
            except Exception:
                previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合行协议。只重新输出合法记录行，不要解释。"}]
        raise ValueError(f"{task} 子任务连续三次未返回合法行协议")

    def _summary_payload(self, lines: Sequence[str]) -> Dict[str, Any]:
        payload = parse_kv_line(lines[0], record_type="SUMMARY", required_keys=("summary_text", "start_anchor", "end_anchor", "timeline_note", "sentence_refs"))
        refs = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)
        return {
            "summary_text": payload["summary_text"],
            "start_anchor": payload["start_anchor"],
            "end_anchor": payload["end_anchor"],
            "timeline_note": payload["timeline_note"],
            "summary_sentence_refs": refs,
        }

    def _event_payload(self, lines: Sequence[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        events: List[Dict[str, Any]] = []
        threads: List[Dict[str, Any]] = []
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "EVENT":
                payload = parse_kv_line(line, record_type="EVENT", required_keys=("summary", "sentence_refs"))
                events.append({"summary": payload["summary"], "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            payload = parse_kv_line(line, record_type="THREAD", required_keys=("thread_key", "summary", "sentence_refs"))
            threads.append({"thread_key": payload["thread_key"], "summary": payload["summary"], "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
        return events, threads

    def _entity_payload(self, lines: Sequence[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        states: List[Dict[str, Any]] = []
        relations: List[Dict[str, Any]] = []
        entities: List[Dict[str, Any]] = []
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "CHAR_STATE":
                payload = parse_kv_line(line, record_type="CHAR_STATE", required_keys=("name", "state", "summary", "sentence_refs"))
                states.append({"name": payload["name"], "state": payload["state"], "summary": payload["summary"], "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            if record_type == "REL_STATE":
                payload = parse_kv_line(line, record_type="REL_STATE", required_keys=("source", "target", "state", "summary", "sentence_refs"))
                relations.append({"source": payload["source"], "target": payload["target"], "state": payload["state"], "summary": payload["summary"], "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            payload = parse_kv_line(line, record_type="ENTITY", required_keys=("name", "entity_type"))
            entities.append({"name": payload["name"], "entity_type": payload["entity_type"]})
        return states, relations, entities
