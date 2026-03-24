"""记忆 subject 归一化工具。"""

from __future__ import annotations

import re
from typing import List


def normalize_memory_subject(text: str) -> str:
    compact = re.sub(r"\s+", "", str(text or ""))
    return compact[:64] or "general"


def memory_tokens(text: str) -> List[str]:
    return [
        item.strip()
        for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,8}", str(text or ""))
        if item.strip()
    ]
