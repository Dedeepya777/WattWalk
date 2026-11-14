"""Router: the cheapest useful next action for one observation (plan 8.4). Owner: Person 2.

Rules are evaluated in order and the first match wins. Each action is tried at most once per
observation and R1 or R8 always finalize, so at most 5 actions run per observation.
"""
from __future__ import annotations

from ..contracts import Observation
from .prompts import KEY_ATTR
from .types import MAX_ACTIONS_PER_OBSERVATION, Action, RouterState, Signals


def key_attr(label: str) -> str | None:
    return KEY_ATTR.get(label)


def key_unknown(obs: Observation) -> bool:
    key = key_attr(obs.label)
    if key is None:
        return False
    attr = obs.attrs.get(key)
    return attr is None or attr.value is None


def next_action(obs: Observation, state: RouterState, signals: Signals) -> Action:
    tried = set(state.tried.get(obs.id, []))
    if len(state.tried.get(obs.id, [])) >= MAX_ACTIONS_PER_OBSERVATION:
        return "leave_unknown"  # defensive: the ladder below cannot exceed this anyway
    can_escalate = "escalate_large" not in tried and not signals.large_cap_reached

    # R1: nothing unresolved and no disagreement
    if not signals.key_unknown and not signals.disagreement:
        return "accept"
    # R2: image quality issue, try another panorama first
    if signals.quality_issue and "neighbor_view" not in tried and signals.neighbor_exists:
        return "neighbor_view"
    # R3: observations of the same object disagree
    if signals.disagreement and can_escalate:
        return "escalate_large"
    if signals.key_unknown:
        # R4: closer look with the small model
        if "hires_crop" not in tried:
            return "hires_crop"
        # R5: labels the benchmark marks hard go to the large model
        if signals.hard_label and can_escalate:
            return "escalate_large"
        # R6: escalate unless escalation already failed for this (label, attribute) in this audit
        if can_escalate and not signals.escalation_failed:
            return "escalate_large"
        # R7: ask the user once per (label, attribute)
        if signals.user_answerable and not signals.asked and "ask_user" not in tried:
            return "ask_user"
    # R8
    return "leave_unknown"
