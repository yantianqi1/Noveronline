"""文风提取 — 把整本小说切块、并行 LLM 提炼局部风格特征，再聚合成结构化
``writing_style`` 资产，写入全局资产库。"""

from .runner import StyleExtractor, run_style_extraction

__all__ = ["StyleExtractor", "run_style_extraction"]
