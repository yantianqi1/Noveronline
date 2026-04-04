"""ReadingNotesManager — three-tier reading notes for sequential novel reading.

Maintains core_facts / relationship_graph / plot_state across segment reads.
Merge protocol: lists always accumulate (never overwrite); status changes are
tracked in history; world-rule facts are deduplicated by exact fact text.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional


class ReadingNotesManager:
    """Manages a three-tier ReadingNotes structure during sequential reading.

    Parameters
    ----------
    arc_interval:
        Number of uncovered segments that triggers an arc-summary request.
    volume_arc_threshold:
        Number of arcs accumulated before a volume-summary is requested.
    """

    def __init__(self, arc_interval: int = 5, volume_arc_threshold: int = 10) -> None:
        self.arc_interval = arc_interval
        self.volume_arc_threshold = volume_arc_threshold

        self.all_segment_summaries: List[Dict] = []
        self._arc_cursor: int = 0  # index into all_segment_summaries; how many are covered by arcs

        self.notes: Dict = self._empty_notes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_notes() -> Dict:
        return {
            "core_facts": {
                "characters": {},
                "organizations": {},
                "world_rules": [],
                "key_locations": {},
                "consistency_notes": [],
            },
            "relationship_graph": [],
            "plot_state": {
                "arc_summaries": [],
                "volume_summaries": [],
                "recent_segment_summaries": [],
                "open_threads": [],
                "resolved_threads": [],
                "narrative_phase": "",
            },
        }

    @staticmethod
    def _empty_character() -> Dict:
        return {
            "aliases": [],
            "status": "",
            "identity": "",
            "first_seen": "",
            "personality_traits": [],
            "speech_style": "",
            "verbal_habits": [],
            "goals": [],
            "key_actions": [],
            "knowledge_gained": [],
            "quote_examples": [],
            "segments_seen": [],
            "status_history": [],
        }

    @staticmethod
    def _empty_organization() -> Dict:
        return {
            "type": "",
            "status": "",
            "members_mentioned": [],
            "purpose": "",
            "first_seen": "",
            "segments_seen": [],
        }

    @staticmethod
    def _extend_unique(target: list, additions: list) -> None:
        """Append items not already in target (by equality)."""
        for item in additions:
            if item not in target:
                target.append(item)

    # ------------------------------------------------------------------
    # Character merging
    # ------------------------------------------------------------------

    def merge_character_updates(self, updates: List[Dict], segment_id: str) -> None:
        """Accumulate character data from a segment extraction.

        Traits, aliases, actions, quotes, goals, knowledge all accumulate.
        Status changes are recorded in status_history.
        """
        chars = self.notes["core_facts"]["characters"]
        for update in updates:
            name = update.get("name")
            if not name:
                continue
            if name not in chars:
                chars[name] = self._empty_character()
            c = chars[name]

            # Scalar fields — set only if not yet populated (first_seen, identity, speech_style)
            # or if explicitly provided (speech_style can be refined)
            if update.get("first_seen") and not c["first_seen"]:
                c["first_seen"] = update["first_seen"]
            if update.get("identity") and not c["identity"]:
                c["identity"] = update["identity"]
            if update.get("speech_style"):
                c["speech_style"] = update["speech_style"]

            # Status with history tracking
            new_status = update.get("status")
            if new_status and new_status != c["status"]:
                if c["status"]:  # record transition (not initial assignment)
                    c["status_history"].append(
                        {"status": new_status, "segment_id": segment_id}
                    )
                c["status"] = new_status
            elif new_status and not c["status"]:
                c["status"] = new_status

            # List fields — accumulate unique
            self._extend_unique(c["aliases"], update.get("aliases", []))
            self._extend_unique(c["personality_traits"], update.get("personality_traits", []))
            self._extend_unique(c["goals"], update.get("goals", []))
            self._extend_unique(c["key_actions"], update.get("key_actions", []))
            self._extend_unique(c["knowledge_gained"], update.get("knowledge_gained", []))
            self._extend_unique(c["quote_examples"], update.get("quote_examples", []))
            self._extend_unique(c.setdefault("verbal_habits", []), update.get("verbal_habits", []))

            if segment_id not in c["segments_seen"]:
                c["segments_seen"].append(segment_id)

    # ------------------------------------------------------------------
    # Organization merging
    # ------------------------------------------------------------------

    def merge_organization(self, name: str, data: Dict, segment_id: str) -> None:
        """Create or update an organization entry."""
        orgs = self.notes["core_facts"]["organizations"]
        if name not in orgs:
            orgs[name] = self._empty_organization()
        org = orgs[name]

        if data.get("type") and not org["type"]:
            org["type"] = data["type"]
        if data.get("status"):
            org["status"] = data["status"]
        if data.get("purpose") and not org["purpose"]:
            org["purpose"] = data["purpose"]
        if data.get("first_seen") and not org["first_seen"]:
            org["first_seen"] = data["first_seen"]

        self._extend_unique(org["members_mentioned"], data.get("members_mentioned", []))

        if segment_id not in org["segments_seen"]:
            org["segments_seen"].append(segment_id)

    # ------------------------------------------------------------------
    # Relationship graph
    # ------------------------------------------------------------------

    def merge_relationship_changes(self, changes: List[Dict], segment_id: str) -> None:
        """Append relationship events to the graph."""
        for change in changes:
            entry = {
                "source": change.get("source", ""),
                "target": change.get("target", ""),
                "relation": change.get("relation", ""),
                "previous_state": change.get("previous_state", ""),
                "trigger": change.get("trigger", ""),
                "evidence": change.get("evidence", ""),
                "segment_id": segment_id,
            }
            self.notes["relationship_graph"].append(entry)

    # ------------------------------------------------------------------
    # World building
    # ------------------------------------------------------------------

    def merge_world_building(self, facts: List[Dict]) -> None:
        """Add world-rule facts, deduplicated by exact fact text."""
        existing_facts = {r["fact"] for r in self.notes["core_facts"]["world_rules"]}
        for item in facts:
            fact_text = item.get("fact", "")
            if fact_text and fact_text not in existing_facts:
                self.notes["core_facts"]["world_rules"].append(
                    {"fact": fact_text, "evidence": item.get("evidence", "")}
                )
                existing_facts.add(fact_text)

    # ------------------------------------------------------------------
    # Plot threads
    # ------------------------------------------------------------------

    def merge_plot_threads(self, threads: List[Dict], segment_id: str = "") -> None:
        """Add opened/progressed threads; move resolved ones to resolved_threads."""
        open_threads = self.notes["plot_state"]["open_threads"]
        resolved_threads = self.notes["plot_state"].setdefault("resolved_threads", [])
        for thread in threads:
            t_name = thread.get("thread", "")
            status = thread.get("status", "open")
            if status == "resolved":
                # Move to resolved_threads instead of deleting
                resolved_entry = deepcopy(thread)
                resolved_entry["resolved_segment_id"] = segment_id
                resolved_threads.append(resolved_entry)
                self.notes["plot_state"]["open_threads"] = [
                    t for t in open_threads if t.get("thread") != t_name
                ]
                open_threads = self.notes["plot_state"]["open_threads"]
            else:
                existing = next((t for t in open_threads if t.get("thread") == t_name), None)
                if existing:
                    existing.update(thread)
                else:
                    open_threads.append(deepcopy(thread))

    def merge_consistency_notes(self, notes: List[str], segment_id: str = "") -> None:
        """Append consistency notes (contradictions/logic issues) found in a segment."""
        cn_list = self.notes["core_facts"].setdefault("consistency_notes", [])
        for note_text in notes:
            if note_text and note_text.strip():
                cn_list.append({"note": note_text.strip(), "segment_id": segment_id})

    # ------------------------------------------------------------------
    # Narrative phase
    # ------------------------------------------------------------------

    def update_narrative_phase(self, phase: str) -> None:
        self.notes["plot_state"]["narrative_phase"] = phase

    # ------------------------------------------------------------------
    # Segment summaries
    # ------------------------------------------------------------------

    def add_segment_summary(self, segment_id: str, summary: str) -> None:
        """Add summary to all_segment_summaries; keep only last 2 in recent."""
        entry = {"segment_id": segment_id, "summary": summary}
        self.all_segment_summaries.append(entry)
        recent = self.notes["plot_state"]["recent_segment_summaries"]
        recent.append(entry)
        # Keep rotating window of last 2
        if len(recent) > 2:
            self.notes["plot_state"]["recent_segment_summaries"] = recent[-2:]

    # ------------------------------------------------------------------
    # Arc summaries
    # ------------------------------------------------------------------

    def needs_arc_summary(self) -> bool:
        """True when there are >= arc_interval uncovered segment summaries."""
        uncovered = len(self.all_segment_summaries) - self._arc_cursor
        return uncovered >= self.arc_interval

    def pending_arc_segments(self) -> List[Dict]:
        """Return all segment summaries not yet covered by any arc."""
        return self.all_segment_summaries[self._arc_cursor:]

    def add_arc_summary(self, arc_id: str, summary: str, covered_segments: List[Dict]) -> None:
        """Record an arc summary and advance the cursor."""
        self.notes["plot_state"]["arc_summaries"].append(
            {
                "arc_id": arc_id,
                "summary": summary,
                "covered_segments": covered_segments,
            }
        )
        self._arc_cursor += len(covered_segments)

    # ------------------------------------------------------------------
    # Volume summaries
    # ------------------------------------------------------------------

    def needs_volume_summary(self) -> bool:
        """True when accumulated arcs reach volume_arc_threshold."""
        return len(self.notes["plot_state"]["arc_summaries"]) >= self.volume_arc_threshold

    def add_volume_summary(self, volume_id: str, summary: str, covered_arcs: List[str]) -> None:
        self.notes["plot_state"]["volume_summaries"].append(
            {"volume_id": volume_id, "summary": summary, "covered_arcs": covered_arcs}
        )

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def assemble_context(self) -> str:
        """Build a text context block for the next LLM call.

        Adaptive length:
        - short novel (< 10 segments): include all characters and recent summaries
        - medium (10–50): summarise characters briefly, include arc summaries
        - long (50+): volume summaries + recent arcs + brief character list
        """
        lines: List[str] = []
        total_segs = len(self.all_segment_summaries)

        # --- Characters ---
        chars = self.notes["core_facts"]["characters"]
        if chars:
            lines.append("=== Characters ===")
            for name, c in chars.items():
                parts = [name]
                if c.get("status"):
                    parts.append(f"[{c['status']}]")
                if c.get("identity"):
                    parts.append(c["identity"])
                # Adaptive trait inclusion — always keep some voice fingerprint
                if total_segs < 10:
                    if c.get("personality_traits"):
                        parts.append("traits: " + ", ".join(c["personality_traits"][:5]))
                    if c.get("speech_style"):
                        parts.append(f"voice: {c['speech_style']}")
                elif total_segs < 50:
                    if c.get("personality_traits"):
                        parts.append("traits: " + ", ".join(c["personality_traits"][:3]))
                    if c.get("speech_style"):
                        parts.append(f"voice: {c['speech_style']}")
                else:
                    if c.get("speech_style"):
                        parts.append(f"voice: {c['speech_style']}")
                lines.append("  " + " | ".join(parts))

        # --- World rules (always include, they're compact) ---
        world_rules = self.notes["core_facts"]["world_rules"]
        if world_rules:
            lines.append("=== World Rules ===")
            for r in world_rules:
                lines.append(f"  - {r['fact']}")

        # --- Open threads ---
        open_threads = self.notes["plot_state"]["open_threads"]
        if open_threads:
            lines.append("=== Open Threads ===")
            for t in open_threads:
                lines.append(f"  [{t.get('status','open')}] {t.get('thread','')} — {t.get('detail','')}")

        # --- Summaries (adaptive) ---
        if total_segs >= 50:
            vol_sums = self.notes["plot_state"]["volume_summaries"]
            if vol_sums:
                lines.append("=== Volume Summaries ===")
                for v in vol_sums:
                    lines.append(f"  [{v['volume_id']}] {v['summary']}")
            arc_sums = self.notes["plot_state"]["arc_summaries"][-3:]
            if arc_sums:
                lines.append("=== Recent Arc Summaries ===")
                for a in arc_sums:
                    lines.append(f"  [{a['arc_id']}] {a['summary']}")
        elif total_segs >= 10:
            arc_sums = self.notes["plot_state"]["arc_summaries"]
            if arc_sums:
                lines.append("=== Arc Summaries ===")
                for a in arc_sums:
                    lines.append(f"  [{a['arc_id']}] {a['summary']}")

        # Always include recent segments
        recent = self.notes["plot_state"]["recent_segment_summaries"]
        if recent:
            lines.append("=== Recent Segments ===")
            for s in recent:
                lines.append(f"  [{s['segment_id']}] {s['summary']}")

        # Narrative phase
        phase = self.notes["plot_state"]["narrative_phase"]
        if phase:
            lines.append(f"=== Narrative Phase: {phase} ===")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialise full state to JSON."""
        state = {
            "arc_interval": self.arc_interval,
            "volume_arc_threshold": self.volume_arc_threshold,
            "all_segment_summaries": self.all_segment_summaries,
            "_arc_cursor": self._arc_cursor,
            "notes": self.notes,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "ReadingNotesManager":
        """Deserialise from JSON, restoring all state."""
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        mgr = cls(
            arc_interval=state.get("arc_interval", 5),
            volume_arc_threshold=state.get("volume_arc_threshold", 10),
        )
        mgr.all_segment_summaries = state.get("all_segment_summaries", [])
        mgr._arc_cursor = state.get("_arc_cursor", 0)
        mgr.notes = state.get("notes", cls._empty_notes())
        return mgr
