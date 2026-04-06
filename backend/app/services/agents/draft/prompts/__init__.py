"""Writer / Reviewer prompt 模块化拼装。"""

from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES
from .anti_cliche import ANTI_CLICHE_RULES
from .dialogue import DIALOGUE_RULES
from .pacing import PACING_RULES
from .reviewer import REVIEWER_PROMPT


def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return "\n\n".join([
        WRITER_BASE_PROMPT,
        PROSE_QUALITY_RULES,
        ANTI_CLICHE_RULES,
        DIALOGUE_RULES,
        PACING_RULES,
    ])


def assemble_reviewer_prompt() -> str:
    """返回 Reviewer prompt。"""
    return REVIEWER_PROMPT
