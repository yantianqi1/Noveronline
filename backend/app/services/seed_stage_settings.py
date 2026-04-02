"""第一阶段种子分析相关设置。"""

from __future__ import annotations

import os


def _read_positive_int(name: str, default: str) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} 必须是大于 0 的整数，当前值为 {value}")
    return value


SEED_STAGE_MAX_WORKERS = _read_positive_int("SEED_STAGE_MAX_WORKERS", "20")
BLOCK_BATCH_SIZE = _read_positive_int("BLOCK_BATCH_SIZE", "50")
LLM_CONCURRENT_LIMIT = _read_positive_int("LLM_CONCURRENT_LIMIT", "4")
ANCHOR_INTERVAL = _read_positive_int("ANCHOR_INTERVAL", "5")
MAX_PROMPT_INPUT_CHARS = _read_positive_int("MAX_PROMPT_INPUT_CHARS", "24000")
