"""User questions for the ask_user router action (plan 8.4.2, rule R7, decision D21). Owner: Person 2."""
from __future__ import annotations

from ..contracts import Attr, ModelGeometry, Observation, Question
from ..inventory import build_inventory
from .prompts import KEY_ATTR, VOCAB

_NOUN = {"bulb_type": "bulb", "thermostat_type": "thermostat"}


def _room_words(geometry: ModelGeometry, room_id: str | None) -> str:
    for room in geometry.rooms:
        if room.id == room_id:
            return room.label.lower()
    return "apartment"


def _asset_id_for(obs: Observation, all_obs: list[Observation]) -> str:
    for asset in build_inventory(all_obs):
        if obs.id in asset.observation_ids:
            return asset.id
    return "a_" + obs.id


def make_question(question_id: str, obs: Observation, all_obs: list[Observation], geometry: ModelGeometry) -> Question:
    attr = KEY_ATTR[obs.label]
    room = _room_words(geometry, obs.room_id)
    noun = _NOUN.get(attr, attr.replace("_", " "))
    thing = obs.label.replace("_", " ")
    text = (f"What type of {noun} is in the {room} {thing}?" if noun != thing
            else f"What type of {noun} is in the {room}?")
    return Question(question_id=question_id, asset_id=_asset_id_for(obs, all_obs), attr=attr, text=text,
                    choices=list(VOCAB[obs.label][attr]) + ["unknown"], status="open", answer=None)


def apply_answer(obs: Observation, question: Question, answer: str | None) -> tuple[Observation, Question]:
    """Apply an answer (or a timeout) to the asked observation only (plan 8.4.3, Answers)."""
    attr = question.attr
    current = obs.attrs.get(attr) or Attr(value=None, source="needs_verification", note="", evidence_obs_ids=[obs.id])
    allowed = VOCAB[obs.label][attr]
    updated = obs.model_copy(deep=True)
    if answer is not None and answer in allowed:
        updated.attrs[attr] = Attr(value=answer, source="provided_by_user",
                                   note=f"answered by user ({question.question_id})", evidence_obs_ids=[obs.id])
        q = question.model_copy(update={"status": "answered", "answer": answer})
    elif answer is not None:
        updated.attrs[attr] = current.model_copy(update={"note": _join(current.note, "user answered unknown")})
        q = question.model_copy(update={"status": "answered", "answer": answer})
    else:
        updated.attrs[attr] = current.model_copy(update={"note": _join(current.note, "user question expired")})
        q = question.model_copy(update={"status": "expired", "answer": None})
    return updated, q


def _join(note: str, extra: str) -> str:
    return f"{note}; {extra}" if note else extra
