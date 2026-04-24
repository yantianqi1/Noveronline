"""One-click buttons for the writer workbench (§4 of W-3 plan).

Each runner drives an ``AgentLoop`` with a hard-coded system prompt and a
whitelist of read + ``propose_*`` tools. Runners never write the database —
all writes go through user-initiated card adoption on the frontend.
"""

from .base import OneClickRunner, OneClickResult
from .chapter_continuer import ChapterContinuerRunner
from .lexicon_cleaner import LexiconCleanerRunner
from .outline_completer import OutlineCompleterRunner
from .relationship_filler import RelationshipFillerRunner
from .word_aligner import WordAlignerRunner

__all__ = [
    "OneClickRunner",
    "OneClickResult",
    "ChapterContinuerRunner",
    "LexiconCleanerRunner",
    "OutlineCompleterRunner",
    "RelationshipFillerRunner",
    "WordAlignerRunner",
]
