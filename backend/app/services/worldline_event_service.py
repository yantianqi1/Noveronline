"""Worldline event adopt/edit/query service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.worldline import WorldEvent, WorldlineSession


class WorldlineEventService:
    """Manages candidate -> canon/rejected transitions and event edits."""

    def __init__(self, store, branch_service=None):
        self.store = store
        self.branch_service = branch_service

    def adopt_events(
        self,
        session: WorldlineSession,
        container_dir: str,
        event_ids: List[str],
        action: str,
    ) -> Dict[str, Any]:
        """Batch adopt or reject candidate events.

        action: "canon" or "rejected"
        Returns dict with adopted/rejected counts and recalculated world state.
        """
        if action not in ("canon", "rejected"):
            raise ValueError("action must be 'canon' or 'rejected'")
        if not event_ids:
            raise ValueError("event_ids must not be empty")

        branch = session.branches[0]
        changed_count = 0
        for event in branch.timeline:
            if event.event_id in event_ids and event.status == "candidate":
                event.status = action
                changed_count += 1

        if changed_count == 0:
            raise ValueError("No matching candidate events found")

        session.updated_at = datetime.now().isoformat()
        self.store.save_session(container_dir, session)

        return {
            "action": action,
            "changed_count": changed_count,
            "event_ids": event_ids,
        }

    def edit_event(
        self,
        session: WorldlineSession,
        container_dir: str,
        event_id: str,
        consequence: str,
    ) -> Dict[str, Any]:
        """Edit a candidate event's summary/consequence, then mark as canon."""
        branch = session.branches[0]
        target_event = None
        for event in branch.timeline:
            if event.event_id == event_id:
                target_event = event
                break

        if not target_event:
            raise ValueError(f"Event not found: {event_id}")
        if target_event.status != "candidate":
            raise ValueError(f"Only candidate events can be edited, current status: {target_event.status}")

        target_event.summary = consequence.strip()
        target_event.status = "canon"
        session.updated_at = datetime.now().isoformat()
        self.store.save_session(container_dir, session)

        return {
            "event_id": event_id,
            "status": "canon",
            "summary": target_event.summary,
        }

    def list_candidate_events(
        self,
        session: WorldlineSession,
        step: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List all candidate events, optionally filtered by step."""
        branch = session.branches[0]
        candidates = []
        for event in branch.timeline:
            if event.status != "candidate":
                continue
            if step is not None and event.step != step:
                continue
            candidates.append(event.to_dict())
        return candidates

    def list_canon_events(
        self,
        session: WorldlineSession,
    ) -> List[Dict[str, Any]]:
        """List all canon events ordered by step."""
        branch = session.branches[0]
        return [
            event.to_dict()
            for event in branch.timeline
            if event.status == "canon"
        ]
