"""将整本小说切成大致等长的块，用于并行 LLM 文风提取。"""

from __future__ import annotations

import re
from typing import List


_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def chunk_novel(text: str, target_chars: int = 3000, max_chunks: int = 40) -> List[str]:
    """按段落聚合成接近 ``target_chars`` 长度的块。

    - 段落优先（不拆分单个段落）
    - 总块数受 ``max_chunks`` 限制：如果原文很长，会先按段落聚成块，再均匀抽样保留前 N 块。
    """
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(text) if p.strip()]
    if not paragraphs:
        return [text]

    chunks: List[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        if buf and buf_len + len(para) > target_chars:
            chunks.append("\n\n".join(buf))
            buf = [para]
            buf_len = len(para)
        else:
            buf.append(para)
            buf_len += len(para)
    if buf:
        chunks.append("\n\n".join(buf))

    if len(chunks) > max_chunks:
        # Uniform sampling preserving head and tail
        step = len(chunks) / max_chunks
        sampled = [chunks[int(i * step)] for i in range(max_chunks)]
        return sampled
    return chunks
