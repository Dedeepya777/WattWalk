"""Vision types (plan 7.13 and Appendix A.3). Owner: Person 2."""
from __future__ import annotations

from typing import Callable, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ..contracts import BBox, Observation, Question

Action = Literal["accept", "hires_crop", "neighbor_view", "escalate_large", "ask_user", "leave_unknown"]
FINAL_ACTIONS: frozenset[str] = frozenset({"accept", "leave_unknown"})
MAX_ACTIONS_PER_OBSERVATION = 5
MAX_LARGE_CALLS_PER_AUDIT = 5


class ViewTask(BaseModel):
    """One planned panorama inspection."""
    room_id: Optional[str]  # None only in the no-rooms fallback
    pano_id: str
    reason: Literal["best_view", "second_view_large_room", "neighbor_view", "no_rooms_fallback"]


class InspectResult(BaseModel):
    observations: list[Observation]  # new observations created by this inspection
    faces_inspected: list[int]       # faces sent to a model
    faces_rejected: list[int]        # faces rejected by the quality check
    calls: int                       # model calls made


class ResolveResult(BaseModel):
    observation_id: str
    action: Action
    observation: Optional[Observation] = None  # updated observation (None if unchanged)
    new_observations: list[Observation] = Field(default_factory=list)  # created by a neighbor view
    question: Optional[Question] = None
    final: bool                      # True when no further action will be taken for this observation
    summary: str = Field(max_length=200)  # one line for the event log


AskFn = Callable[[Question], Optional[str]]  # supplied by Person 3; blocks up to 30 s; answer or None


class RawDetection(BaseModel):
    """A validated detection from one face, bbox already scaled to face pixels."""
    label: str
    bbox: BBox
    attrs: dict[str, Union[str, float, int, None]]  # None means the model said "unknown"


class RejectedFace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pano_id: str
    face: int
    reason: str  # e.g. "too dark (brightness 31)"


class RouterState(BaseModel):
    """Persisted in audits/<sid>/router_state.json (Appendix A.3, plus Person 2 bookkeeping fields)."""
    tried: dict[str, list[str]] = Field(default_factory=dict)
    escalation_failed: list[list[str]] = Field(default_factory=list)  # [label, attr] pairs
    asked: list[list[str]] = Field(default_factory=list)              # [label, attr] pairs
    large_calls: int = 0
    final: list[str] = Field(default_factory=list)                    # observation ids finalized
    inspected: dict[str, list[int]] = Field(default_factory=dict)     # pano id -> faces sent to a model
    rejected_faces: list[RejectedFace] = Field(default_factory=list)
    consecutive_failures: int = 0


class Signals(BaseModel):
    """Measured routing signals (plan 8.4.1). Never model self-reported confidence."""
    quality_issue: bool = False
    key_unknown: bool = False
    disagreement: bool = False
    hard_label: bool = False
    neighbor_exists: bool = False
    user_answerable: bool = False
    escalation_failed: bool = False  # for this (label, key attribute) in this audit
    asked: bool = False              # a question was already asked for this (label, key attribute)
    large_cap_reached: bool = False
