"""Fixture vision mode (plan 8.3.6). Owner: Person 2.

inspect_view returns the fixture observations of a pano (as they looked before routing) with no
model calls; resolve replays the recorded router decisions (high-res crop for the lights, one
escalation for o007, one question for the bedroom light). After every observation is resolved the
stored observations equal the fixture's observations.json exactly.

Observation ids are the fixture's own ids, so the result matches observations.json id for id.
Model calls are logged with the illustrative token counts of shared/examples/model_calls.json so
the model-call counter and summary behave as in a real run; the audit itself is labeled fixture.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .. import config, store
from ..contracts import ModelCall, ModelGeometry, Observation
from .detect import now_iso
from .prompts import KEY_ATTR, NON_VISUAL
from .questions import apply_answer, make_question
from .state import load_state, lock, log_calls, next_question_id, save_state
from .types import AskFn, InspectResult, RejectedFace, ResolveResult

HIRES_NOTE = "bulb hidden inside fixture; high-res crop did not resolve"
ESCALATED_NOTE = "unresolved after high-res crop and large model"
INITIAL_NOTE = "not clearly visible at 2k"
# p05 face 4 is rejected in the fixture run (plan 4.6.2: brightness 31, below 40).
FIXTURE_REJECTED = {config.FIXTURE_SID: [RejectedFace(pano_id="p05", face=4, reason="too dark (brightness 31)")]}


def _fixture_dir(sid: str) -> Path:
    return config.EXAMPLES_DIR if sid == config.FIXTURE_SID else config.FIXTURES_DIR / "live" / sid


@lru_cache(maxsize=8)
def _final_observations(sid: str) -> tuple[Observation, ...]:
    path = _fixture_dir(sid) / "observations.json"
    if not path.exists():
        raise ValueError("no vision fixture for sid")
    return tuple(Observation.model_validate(o) for o in json.loads(path.read_text(encoding="utf-8")))


def _rejected(sid: str) -> list[RejectedFace]:
    if sid in FIXTURE_REJECTED:
        return FIXTURE_REJECTED[sid]
    meta = _fixture_dir(sid) / "vision_meta.json"
    if meta.exists():
        return [RejectedFace.model_validate(r) for r in json.loads(meta.read_text(encoding="utf-8")).get("rejected_faces", [])]
    return []


@lru_cache(maxsize=1)
def _call_templates() -> dict[tuple[str, str], ModelCall]:
    calls = [ModelCall.model_validate(c) for c in json.loads((config.EXAMPLES_DIR / "model_calls.json").read_text(encoding="utf-8"))]
    templates: dict[tuple[str, str], ModelCall] = {}
    for c in calls:
        if c.agent == "walker":
            templates.setdefault((c.kind, c.model_tier), c)
    return templates


def _call(kind: str, tier: str) -> ModelCall:
    return _call_templates()[(kind, tier)].model_copy(update={"id": "c000", "at": now_iso()})


def script(final: Observation) -> list[str]:
    """Recorded router actions for one fixture observation (plan 4.6.2)."""
    key = KEY_ATTR.get(final.label)
    if key and final.attrs.get(key) is not None and final.attrs[key].value is None:
        return ["hires_crop", "escalate_large", "ask_user", "leave_unknown"] if final.escalated else ["hires_crop", "leave_unknown"]
    if any((final.label, k) in NON_VISUAL and a.value is None for k, a in final.attrs.items()) and not key:
        return ["leave_unknown"]  # e.g. refrigerator age: never visually determinable
    return ["accept"]


def initial(final: Observation) -> Observation:
    """The observation as inspect_view first produced it, before any router action."""
    steps = script(final)
    obs = final.model_copy(deep=True)
    key = KEY_ATTR.get(final.label)
    if "hires_crop" in steps and key:
        obs.attrs[key] = obs.attrs[key].model_copy(update={"note": INITIAL_NOTE})
    if final.escalated:
        small = _call_templates()[("detect", "small")].model_id
        obs = obs.model_copy(update={"model_id": small, "model_tier": "small", "escalated": False})
    return obs


def inspect_view(sid: str, geometry: ModelGeometry, room_id: str | None, pano_id: str) -> InspectResult:
    finals = [o for o in _final_observations(sid) if o.pano_id == pano_id]
    rejected = [r for r in _rejected(sid) if r.pano_id == pano_id]
    inspected = [f for f in (1, 2, 3, 4) if f not in {r.face for r in rejected}]
    with lock(sid):
        state = load_state(sid)
        known = {(r.pano_id, r.face) for r in state.rejected_faces}
        state.rejected_faces += [r for r in rejected if (r.pano_id, r.face) not in known]
        state.inspected[pano_id] = inspected
        save_state(sid, state)
    log_calls(sid, [_call("detect", "small") for _ in inspected])
    return InspectResult(observations=[initial(o) for o in finals], faces_inspected=inspected,
                         faces_rejected=[r.face for r in rejected], calls=len(inspected))


def resolve(sid: str, geometry: ModelGeometry, observation_id: str, ask: AskFn) -> ResolveResult:
    finals = {o.id: o for o in _final_observations(sid)}
    if observation_id not in finals:
        raise ValueError(f"unknown observation {observation_id!r} in vision fixture")
    final = finals[observation_id]
    all_obs = store.observations(sid)
    current = next((o for o in all_obs if o.id == observation_id), None) or initial(final)
    key = KEY_ATTR.get(final.label)

    with lock(sid):
        state = load_state(sid)
        if observation_id in state.final:
            return ResolveResult(observation_id=observation_id, action="accept", final=True, summary=f"{observation_id} already final")
        tried = state.tried.setdefault(observation_id, [])
        answered = key is not None and tried and current.attrs[key].value is not None
        steps = script(final)
        action = "accept" if answered else (steps[len(tried)] if len(tried) < len(steps) else "leave_unknown")
        tried.append(action)

        question = None
        if action == "accept":
            result = ResolveResult(observation_id=observation_id, action=action, final=True, summary=f"{observation_id} accepted")
        elif action == "leave_unknown":
            result = ResolveResult(observation_id=observation_id, action=action, observation=final.model_copy(deep=True), final=True,
                                   summary=f"{observation_id} left unknown ({key or 'attributes'} needs verification)")
        elif action == "hires_crop":
            log_calls(sid, [_call("attr", "small")])
            note = HIRES_NOTE
            obs = current.model_copy(deep=True)
            obs.attrs[key] = obs.attrs[key].model_copy(update={"note": note})
            result = ResolveResult(observation_id=observation_id, action=action, observation=obs, final=False,
                                   summary=f"{observation_id} high-res crop (small model): {key} still unknown")
        elif action == "escalate_large":
            log_calls(sid, [_call("attr", "large")])
            state.large_calls += 1
            if [final.label, key] not in state.escalation_failed:
                state.escalation_failed.append([final.label, key])
            obs = current.model_copy(update={"model_id": final.model_id, "model_tier": "large", "escalated": True}, deep=True)
            obs.attrs[key] = obs.attrs[key].model_copy(update={"note": ESCALATED_NOTE})
            result = ResolveResult(observation_id=observation_id, action=action, observation=obs, final=False,
                                   summary=f"{observation_id} escalated to large model: {key} still unknown")
        else:  # ask_user
            if [final.label, key] not in state.asked:
                state.asked.append([final.label, key])
            question = make_question(next_question_id(sid), current, all_obs, geometry)
            result = None
        if action in ("accept", "leave_unknown"):
            state.final.append(observation_id)
        save_state(sid, state)

    if question is not None:  # outside the lock: ask blocks up to 30 s
        try:
            answer = ask(question)
        except Exception:
            answer = None
        obs, question = apply_answer(current, question, answer)
        word = f"answered '{question.answer}'" if question.status == "answered" else "expired without an answer"
        result = ResolveResult(observation_id=observation_id, action="ask_user", observation=obs, question=question,
                               final=False, summary=f"Question {question.question_id} {word}")
    return result
