"""Pydantic schemas for story-graph LLM bond/thread generation."""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ._base import AllowExtraBase


class GraphBondGenerateRequest(AllowExtraBase):
    node_uuids: List[str] = Field(..., min_length=2, max_length=6)
    generate_bonds: bool = True
    generate_threads: bool = True


class GeneratedBond(AllowExtraBase):
    source_name: str
    target_name: str
    relation_type: str = ""
    description: str = ""
    trust_level: Optional[float] = None
    power_dynamic: str = ""
    history: str = ""
    conflict_trigger: str = ""
    persisted: bool = False
    relation_id: Optional[str] = None
    skip_reason: str = ""


class GeneratedPlotThread(AllowExtraBase):
    thread_key: str
    detail: str = ""
    status: str = "open"
    involved_names: List[str] = Field(default_factory=list)
    persisted: bool = False
    thread_id: Optional[str] = None
    linked_entity_ids: List[str] = Field(default_factory=list)
    skip_reason: str = ""


class GraphBondGenerateResponse(AllowExtraBase):
    bonds: List[GeneratedBond] = Field(default_factory=list)
    plot_threads: List[GeneratedPlotThread] = Field(default_factory=list)
    unmapped_names: List[str] = Field(default_factory=list)
    selected_nodes: List[dict] = Field(default_factory=list)
