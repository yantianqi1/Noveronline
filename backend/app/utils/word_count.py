"""Character counting utilities tuned for Chinese narrative text.

``count_cjk_chars`` counts *meaningful* characters (excluding whitespace) to
approximate how Chinese readers perceive 字数 — matching the convention used
by mainstream online novel sites where punctuation and full-width spaces are
usually included but whitespace and line breaks are not.
"""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_CHARS = set("，。！？、；：“”‘’「」『』（）《》【】…—·,.!?;:\"'()<>[]")


def count_cjk_chars(text: str | None) -> int:
    """Return the character count used as 字数.

    Excludes all whitespace (ASCII + full-width) but keeps punctuation so the
    result aligns with editor word-count displays for Chinese prose.
    """
    if not text:
        return 0
    stripped = _WHITESPACE_RE.sub("", text)
    return len(stripped)


def count_cjk_chars_strict(text: str | None) -> int:
    """Stricter count that excludes whitespace *and* common punctuation.

    Useful for quality signals (e.g. "actual narrative characters") but not
    for user-facing 字数 targets.
    """
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace() and ch not in _PUNCT_CHARS)
