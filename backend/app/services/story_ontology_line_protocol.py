"""小说本体的行协议执行器。"""

from __future__ import annotations

from typing import Any, Dict, List

from .seed_line_protocol import parse_csv_list, parse_kv_line, protocol_lines
from .story_ontology_protocol_prompts import build_story_ontology_protocol_prompt


class StoryOntologyLineProtocolExecutor:
    def __init__(self, client):
        self.client = client

    def generate(self, user_message: str) -> Dict[str, Any]:
        entity_lines = self._call_subtask("entity_types", user_message)
        edge_lines = self._call_subtask("edge_types", user_message)
        entity_types = [self._entity_type(line) for line in entity_lines]
        edge_types, summary, focus = self._edge_payload(edge_lines)
        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "analysis_summary": summary,
            "story_focus": focus,
            "generation_mode": "line_protocol",
        }

    def _call_subtask(self, task: str, user_message: str) -> List[str]:
        messages = [
            {"role": "system", "content": build_story_ontology_protocol_prompt(task)},
            {"role": "user", "content": f"## 子任务\n{task}\n\n{user_message}"},
        ]
        previous = ""
        for attempt in range(3):
            response = self.client.chat(messages=messages, temperature=max(0.1, 0.3 - attempt * 0.05), max_tokens=2400)
            try:
                return protocol_lines(response)
            except ValueError:
                previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合行协议。只重新输出合法记录行，不要解释。"}]
        raise ValueError(f"{task} 子任务连续三次未返回合法行协议")

    def _entity_type(self, line: str) -> Dict[str, Any]:
        payload = parse_kv_line(line, record_type="ENTITY_TYPE", required_keys=("name", "description", "attributes", "examples"))
        return {
            "name": payload["name"],
            "description": payload["description"],
            "attributes": self._attributes(payload["attributes"]),
            "examples": parse_csv_list(payload["examples"]),
        }

    def _edge_payload(self, lines: List[str]) -> tuple[List[Dict[str, Any]], str, List[str]]:
        edge_types: List[Dict[str, Any]] = []
        summary = ""
        focus: List[str] = []
        for line in lines:
            record_type = line.split("|", 1)[0].strip()
            if record_type == "EDGE_TYPE":
                payload = parse_kv_line(line, record_type="EDGE_TYPE", required_keys=("name", "description", "source_targets", "attributes"))
                edge_types.append(
                    {
                        "name": payload["name"],
                        "description": payload["description"],
                        "source_targets": self._source_targets(payload["source_targets"]),
                        "attributes": self._attributes(payload["attributes"]),
                    }
                )
                continue
            if record_type == "SUMMARY":
                summary = parse_kv_line(line, record_type="SUMMARY", required_keys=("text",))["text"]
                continue
            focus.append(parse_kv_line(line, record_type="FOCUS", required_keys=("text",))["text"])
        return edge_types, summary, focus

    def _attributes(self, value: str) -> List[Dict[str, str]]:
        if not value.strip():
            return []
        items: List[Dict[str, str]] = []
        for item in value.split(";"):
            parts = [part.strip() for part in item.split(":", 2)]
            if len(parts) != 3 or not parts[0]:
                continue
            items.append({"name": parts[0], "type": parts[1], "description": parts[2]})
        return items

    def _source_targets(self, value: str) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        for item in value.split(";"):
            if ">" not in item:
                continue
            source, target = [part.strip() for part in item.split(">", 1)]
            if source and target:
                items.append({"source": source, "target": target})
        return items
