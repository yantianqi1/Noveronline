"""剧情锚点的行协议执行器。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .anchor_point_protocol_prompts import ANCHOR_POINT_PROTOCOL_PROMPT
from .seed_line_protocol import parse_kv_line, parse_positive_int, parse_sentence_ref_list, protocol_lines


class AnchorPointLineProtocolExecutor:
    def __init__(self, client, sentence_map: Dict[str, Dict[str, object]], valid_sentence_ids: Sequence[str]):
        self.client = client
        self.sentence_map = sentence_map
        self.valid_sentence_ids = list(valid_sentence_ids)

    def build(self, user_prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": ANCHOR_POINT_PROTOCOL_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        previous = ""
        for _ in range(3):
            response = self.client.chat(messages=messages, temperature=0.15, max_tokens=2200)
            try:
                lines = protocol_lines(response)
                if not lines:
                    raise ValueError("空响应")
                return self._world_state(lines)
            except Exception:
                previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合协议。只重新输出合法记录行。"}]
        raise ValueError("剧情锚点连续三次未返回合法行协议")

    def _world_state(self, lines: Sequence[str]) -> Dict[str, Any]:
        world_state = {
            "active_characters": [],
            "active_organizations": [],
            "key_relationships": [],
            "open_plot_threads": [],
            "recent_events_summary": "",
            "recent_events_sentence_refs": [],
        }
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "ACTIVE_CHARACTER":
                payload = parse_kv_line(line, record_type="ACTIVE_CHARACTER", required_keys=("name", "status", "last_action", "sentence_refs"))
                world_state["active_characters"].append({**payload, "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            if record_type == "ACTIVE_ORG":
                payload = parse_kv_line(line, record_type="ACTIVE_ORG", required_keys=("name", "status", "key_change", "sentence_refs"))
                world_state["active_organizations"].append({**payload, "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            if record_type == "KEY_REL":
                payload = parse_kv_line(line, record_type="KEY_REL", required_keys=("source", "target", "state", "since_chapter", "sentence_refs"))
                world_state["key_relationships"].append({**payload, "since_chapter": parse_positive_int(payload["since_chapter"], default=1), "sentence_refs": parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)})
                continue
            if record_type == "OPEN_THREAD":
                payload = parse_kv_line(line, record_type="OPEN_THREAD", required_keys=("text", "sentence_refs"))
                world_state["open_plot_threads"].append(payload["text"])
                continue
            payload = parse_kv_line(line, record_type="RECENT_EVENTS", required_keys=("text", "sentence_refs"))
            world_state["recent_events_summary"] = payload["text"]
            world_state["recent_events_sentence_refs"] = parse_sentence_ref_list(payload["sentence_refs"], valid_sentence_ids=self.valid_sentence_ids)
        return world_state
