"""实体消歧的行协议解析器。"""

from __future__ import annotations

from typing import Dict

from .seed_line_protocol import parse_kv_line, protocol_lines


class EntityResolutionLineProtocolExecutor:
    def __init__(self, client):
        self.client = client

    def decide(self, system_prompt: str, user_prompt: str) -> Dict[str, object]:
        messages = [
            {"role": "system", "content": system_prompt + "\n只允许输出一行协议：DECISION|merge=true或false|canonical_name=...|confidence=0.0-1.0|reason=..."},
            {"role": "user", "content": user_prompt},
        ]
        previous = ""
        for _ in range(3):
            response = self.client.chat(messages=messages, temperature=0.1, max_tokens=320)
            lines = protocol_lines(response)
            if lines:
                payload = parse_kv_line(lines[0], record_type="DECISION", required_keys=("merge", "canonical_name", "confidence", "reason"))
                return {
                    "merge": payload["merge"].lower() == "true",
                    "canonical_name": payload["canonical_name"],
                    "confidence": float(payload["confidence"] or 0),
                    "reason": payload["reason"],
                }
            previous = response
            messages = messages + [{"role": "assistant", "content": previous}, {"role": "user", "content": "上一条回复不符合协议。只重新输出一行 DECISION 记录。"}]
        raise ValueError("实体消歧连续三次未返回合法行协议")
