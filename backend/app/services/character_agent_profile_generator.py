"""Character Agent Profile Generator.

Generates structured agent profiles for important characters using reading notes
accumulated by ReadingNotesManager. Profiles include personality, speech patterns,
relationships, capabilities, knowledge boundaries and motivations.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from .character_agent_prompts import build_character_profile_prompt
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager

logger = logging.getLogger(__name__)

MODULE_KEY = "character_agent_profile"
DEFAULT_IMPORTANCE_THRESHOLD = 2  # Minimum segment appearances


class CharacterAgentProfileGenerator:
    """Generate agent profiles for all important characters.

    Parameters
    ----------
    llm_router:
        Router used to build an LLM client for the ``character_agent_profile``
        module key.  If *None*, a default :class:`LlmRouter` is created.
    importance_threshold:
        Minimum number of segments a character must appear in to be included.
        Defaults to :data:`DEFAULT_IMPORTANCE_THRESHOLD`.
    max_workers:
        Maximum threads for concurrent LLM calls.
    """

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        importance_threshold: int = DEFAULT_IMPORTANCE_THRESHOLD,
        max_workers: int = 10,
    ) -> None:
        self.llm_router = llm_router or LlmRouter()
        self.importance_threshold = importance_threshold
        self.max_workers = max_workers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        manager: ReadingNotesManager,
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """Generate agent profiles for all important characters.

        Parameters
        ----------
        manager:
            A populated :class:`ReadingNotesManager` instance.
        use_llm:
            When *False*, build minimal offline profiles from reading notes data
            directly without calling an LLM.
        progress_callback:
            Optional callable receiving ``(event_name, payload)`` progress events:
            - ``"profiles_start"`` — ``{"total": N}``
            - ``"profile_done"``  — ``{"name": ..., "completed": ..., "total": ...}``

        Returns
        -------
        dict
            ``{"profiles": {name: profile_dict}, "profile_count": int}``
        """
        characters = manager.notes["core_facts"]["characters"]
        important_names = self._select_important_characters(characters)

        if progress_callback:
            progress_callback("profiles_start", {"total": len(important_names)})

        if not use_llm:
            offline = self._offline_profiles(important_names, characters)
            completed = 0
            for name in important_names:
                completed += 1
                if progress_callback:
                    progress_callback(
                        "profile_done",
                        {"name": name, "completed": completed, "total": len(important_names)},
                    )
            return {"profiles": offline, "profile_count": len(offline)}

        story_summary = self._build_story_summary(manager)
        relationship_graph = manager.notes.get("relationship_graph", [])

        profiles: Dict[str, Any] = {}
        client = self.llm_router.build_client(MODULE_KEY)

        def _generate_one(name: str) -> tuple[str, Dict[str, Any]]:
            char_data = characters[name]
            rel_entries = [
                e for e in relationship_graph
                if e.get("source") == name or e.get("target") == name
            ]
            messages = build_character_profile_prompt(
                character_name=name,
                character_data=char_data,
                relationship_entries=rel_entries,
                story_summary=story_summary,
            )
            profile = client.chat_json_value(messages, temperature=0.3, max_tokens=4096)
            return name, profile

        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_name = {}
            for name in important_names:
                if cancel_check is not None:
                    cancel_check()
                future_to_name[executor.submit(_generate_one, name)] = name
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result_name, profile = future.result()
                    profiles[result_name] = profile
                except Exception:
                    logger.exception("Failed to generate profile for character %r", name)
                    profiles[name] = self._minimal_profile(name, characters[name])
                completed += 1
                if progress_callback:
                    progress_callback(
                        "profile_done",
                        {"name": name, "completed": completed, "total": len(important_names)},
                    )

        return {"profiles": profiles, "profile_count": len(profiles)}

    # ------------------------------------------------------------------
    # Character selection
    # ------------------------------------------------------------------

    def _select_important_characters(self, characters: Dict[str, Any]) -> List[str]:
        """Return names of characters with >= threshold segment appearances.

        Results are sorted descending by appearance count (most seen first).
        """
        qualified = [
            (name, len(data.get("segments_seen", [])))
            for name, data in characters.items()
            if len(data.get("segments_seen", [])) >= self.importance_threshold
        ]
        qualified.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in qualified]

    # ------------------------------------------------------------------
    # Offline mode
    # ------------------------------------------------------------------

    def _offline_profiles(
        self, names: List[str], characters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build minimal profiles for all named characters without LLM."""
        return {name: self._minimal_profile(name, characters[name]) for name in names}

    def _minimal_profile(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a minimal profile from reading notes data."""
        aliases = data.get("aliases", [])
        identity = data.get("identity", "") or "暂无记录"
        status = data.get("status", "") or "暂无记录"
        traits = data.get("personality_traits", []) or ["暂无记录"]
        goals = data.get("goals", []) or ["暂无记录"]
        quotes = data.get("quote_examples", []) or ["暂无记录"]
        knowledge = data.get("knowledge_gained", []) or ["暂无记录"]
        speech_style = data.get("speech_style", "") or "暂无记录"

        return {
            "basic_info": {
                "name": name,
                "aliases": aliases,
                "identity": identity,
                "status": status,
            },
            "personality": {
                "core_traits": traits[:5],
                "values": "暂无记录",
                "fears": "暂无记录",
                "decision_pattern": "暂无记录",
            },
            "speech": {
                "style": speech_style,
                "verbal_habits": ["暂无记录"],
                "tone_range": "暂无记录",
                "example_quotes": quotes[:3],
            },
            "relationships": [],
            "capabilities": {
                "skills": ["暂无记录"],
                "limitations": ["暂无记录"],
                "resources": "暂无记录",
            },
            "knowledge_boundary": {
                "knows": knowledge[:5],
                "does_not_know": ["暂无记录"],
                "believes_wrongly": ["暂无记录"],
            },
            "motivation": {
                "ultimate_goal": goals[0] if goals else "暂无记录",
                "current_objective": "暂无记录",
                "internal_conflict": "暂无记录",
            },
        }

    # ------------------------------------------------------------------
    # Story summary helper
    # ------------------------------------------------------------------

    @staticmethod
    def _build_story_summary(manager: ReadingNotesManager) -> str:
        """Combine arc and recent segment summaries into a concise text block."""
        lines: List[str] = []

        arc_summaries = manager.notes["plot_state"].get("arc_summaries", [])
        if arc_summaries:
            lines.append("【弧线摘要】")
            for arc in arc_summaries[-5:]:
                lines.append(f"[{arc['arc_id']}] {arc['summary']}")

        recent = manager.notes["plot_state"].get("recent_segment_summaries", [])
        if recent:
            lines.append("【近期段落摘要】")
            for seg in recent:
                lines.append(f"[{seg['segment_id']}] {seg['summary']}")

        vol_summaries = manager.notes["plot_state"].get("volume_summaries", [])
        if vol_summaries:
            lines.append("【卷摘要】")
            for vol in vol_summaries[-3:]:
                lines.append(f"[{vol['volume_id']}] {vol['summary']}")

        return "\n".join(lines)
