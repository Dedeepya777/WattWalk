"""Per-audit vision bookkeeping: router state, id allocation, model-call logging. Owner: Person 2.

All audit files go through store.read/write (router_state.json) and store.append_model_calls.
"""
from __future__ import annotations

import re
import threading
from collections import defaultdict

from .. import config, store
from ..contracts import ModelCall
from .types import RouterState

_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_reserved_obs: dict[str, int] = {}
_guard = threading.Lock()


def lock(sid: str) -> threading.RLock:
    with _guard:
        return _locks[sid]


def _num(identifier: str) -> int:
    m = re.search(r"(\d+)$", identifier)
    return int(m.group(1)) if m else 0


def load_state(sid: str) -> RouterState:
    return store.read(sid, "router_state.json", RouterState, default=None) or RouterState()


def save_state(sid: str, state: RouterState) -> None:
    store.write(sid, "router_state.json", state)


def next_observation_ids(sid: str, n: int) -> list[str]:
    """Allocate n new observation ids (o001, o002, ...), counting ids already handed out but not yet stored."""
    with lock(sid):
        highest = max([_num(o.id) for o in store.observations(sid)] + [_reserved_obs.get(sid, 0)])
        ids = [f"o{highest + i + 1:03d}" for i in range(n)]
        if n:
            _reserved_obs[sid] = highest + n
        return ids


def forget_reservations(sid: str) -> None:
    """Call after store.reset(sid) so numbering restarts at o001."""
    with _guard:
        _reserved_obs.pop(sid, None)


def log_calls(sid: str, calls: list[ModelCall]) -> None:
    """Assign c-ids after the highest existing one and append to model_calls.json."""
    if not calls:
        return
    # In an API-driven fixture run, Person 3 copies the illustrative
    # model_calls.json; do not append a second set of simulated vision calls.
    if config.RUN_MODE_OVERRIDE.get() == "fixture":
        return
    with lock(sid):
        existing = store.read(sid, "model_calls.json", default=[]) or []
        highest = max([_num(c["id"]) for c in existing] + [0])
        numbered = [c.model_copy(update={"id": f"c{highest + i + 1:03d}"}) for i, c in enumerate(calls)]
        store.append_model_calls(sid, numbered)


def next_question_id(sid: str) -> str:
    existing = store.read(sid, "questions.json", default=[]) or []
    highest = max([_num(q["question_id"]) for q in existing] + [0])
    return f"q{highest + 1:03d}"
