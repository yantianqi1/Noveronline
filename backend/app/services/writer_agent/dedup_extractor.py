"""Post-scene LLM pattern extractor — populates ``dedup_index``.

After each scene or chapter is committed, this service reads the prose and
asks a small LLM to surface the surface-level patterns most at risk of being
subconsciously reused in the next generation (stock opening phrases, figurative
fragments, POV action tics, sentence starters, scene skeletons). Results are
persisted through :class:`DedupIndexRepository`; the writer orchestrator picks
them up on the next run and injects them as anti-repetition constraints.

The extractor is best-effort:

* LLM module binding missing → silent no-op (feature degrades gracefully).
* JSON parse failure → warn, no-op.
* Empty content → no-op.

Never raise to the caller — :class:`PostProcessor` must not fail scene commits
because of a dedup-extraction hiccup.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from app.database import get_engine
from app.repositories.dedup_index_repo import PATTERN_TYPES, DedupIndexRepository
from app.services.llm_router import LlmRouter

from .prompts import build_dedup_extractor_prompt, build_dedup_extractor_user_message

logger = logging.getLogger(__name__)

_MAX_PROSE_CHARS = 12000  # Cap input so a runaway chapter doesn't blow the prompt budget
_PER_TYPE_CAP = 10


# The extractor returns the keys as plural nouns (opening_phrases, ...); the
# dedup_index stores them singular (opening_phrase, ...). Keep mapping here so
# the prompt stays readable while the repo stays consistent with PATTERN_TYPES.
_KEY_MAP: dict[str, str] = {
    "opening_phrases": "opening_phrase",
    "figurative_phrases": "figurative_phrase",
    "action_verbs": "action_verb",
    "sentence_starters": "sentence_starter",
    "scene_templates": "scene_template",
}


class DedupExtractor:
    """Single-call LLM wrapper that extracts and persists pattern hits."""

    def __init__(self, llm_router: LlmRouter | None = None, repo: DedupIndexRepository | None = None):
        self.router = llm_router or LlmRouter()
        self.repo = repo or DedupIndexRepository(get_engine())

    async def extract_and_save(
        self,
        project_id: str,
        chapter_order: int,
        scene_id: str | None,
        content: str,
        *,
        scene_order: int | None = None,
    ) -> dict[str, int]:
        """Run one extraction pass and persist hits.

        Returns a ``{pattern_type: count_written}`` dict for logging. Never
        raises — failures log a warning and return an empty dict so the
        caller can continue its main flow.
        """
        if not project_id or not content:
            return {}

        trimmed = content.strip()
        if not trimmed:
            return {}
        if len(trimmed) > _MAX_PROSE_CHARS:
            trimmed = trimmed[:_MAX_PROSE_CHARS]

        try:
            client = await self.router.build_async_client("writer_dedup_extractor")
        except ValueError:
            logger.info(
                "dedup_extractor skipped: module writer_dedup_extractor not bound "
                "(project=%s chapter=%s)",
                project_id,
                chapter_order,
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("dedup_extractor client build failed: %s", exc)
            return {}

        messages = [
            {"role": "system", "content": build_dedup_extractor_prompt()},
            {"role": "user", "content": build_dedup_extractor_user_message(chapter_order, scene_order, trimmed)},
        ]
        try:
            raw = await client.chat_json_value(messages, temperature=0.1, max_tokens=1500)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dedup_extractor LLM call failed: %s", exc)
            return {}

        patterns = self._normalize(raw)
        if not patterns:
            return {}

        try:
            self.repo.add_patterns(project_id, chapter_order, scene_id, patterns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dedup_extractor persist failed: %s", exc)
            return {}

        written_summary = {ptype: len(texts) for ptype, texts in patterns.items() if texts}
        if written_summary:
            logger.info(
                "dedup_extractor saved patterns project=%s chapter=%s scene=%s types=%s",
                project_id,
                chapter_order,
                scene_id,
                written_summary,
            )
        return written_summary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _normalize(cls, raw: Any) -> dict[str, dict[str, int]]:
        """Map the LLM's plural-keyed JSON into repo-friendly {type: {text: count}}.

        Ignores unknown keys, dedupes by text (case-sensitive), caps each
        bucket at :data:`_PER_TYPE_CAP` so malformed responses can't flood
        the index. Missing or non-dict inputs short-circuit to empty.
        """
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, int]] = {ptype: {} for ptype in PATTERN_TYPES}
        for plural, ptype in _KEY_MAP.items():
            values = raw.get(plural)
            if not isinstance(values, (list, tuple)):
                continue
            seen: set[str] = set()
            for item in cls._iter_strings(values):
                if item in seen:
                    continue
                seen.add(item)
                out[ptype][item] = 1
                if len(out[ptype]) >= _PER_TYPE_CAP:
                    break
        # Drop empty buckets to keep downstream logs quiet
        return {k: v for k, v in out.items() if v}

    @staticmethod
    def _iter_strings(values: Iterable[Any]) -> Iterable[str]:
        for v in values:
            if isinstance(v, str):
                cleaned = v.strip()
                if 2 <= len(cleaned) <= 80:
                    yield cleaned
