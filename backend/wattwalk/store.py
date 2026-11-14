"""Audit folder read and write. Owner: Person 3.

TEMPORARY until Person 3 delivers: a minimal implementation of the canonical store functions
(shared/contracts/README.md section 5) so Person 2's vision and inventory code can run and be tested
before the shared baseline exists. Replace this file with Person 3's version; do not extend it.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from . import config
from .contracts import ModelCall, Observation, Question

T = TypeVar("T", bound=BaseModel)
_LOCK = threading.RLock()


def _root(sid: str) -> Path:
    return Path(config.AUDITS_DIR) / sid


def audit_path(sid: str, *parts: str) -> Path:
    """Path inside audits/<sid>/; creates parent folders."""
    path = _root(sid).joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


def read(sid: str, name: str, model: type[T] | None = None, default=None):
    path = _root(sid) / name
    if not path.exists():
        return default
    data = json.loads(path.read_text(encoding="utf-8"))
    if model is None:
        return data
    if isinstance(data, list):
        return [model.model_validate(d) for d in data]
    return model.model_validate(data)


def write(sid: str, name: str, obj) -> None:
    """Atomic write (temp file + rename)."""
    path = audit_path(sid, name)
    with _LOCK:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_dump(obj), f, indent=2)
        os.replace(tmp, path)


def observations(sid: str) -> list[Observation]:
    return read(sid, "observations.json", Observation, default=[])


def append_observations(sid: str, obs: list[Observation]) -> None:
    with _LOCK:
        current = observations(sid)
        write(sid, "observations.json", sorted(current + list(obs), key=lambda o: o.id))


def apply_resolve(sid: str, result) -> None:
    """Replace the updated observation, append new ones, record the question."""
    with _LOCK:
        current = {o.id: o for o in observations(sid)}
        if result.observation is not None:
            current[result.observation.id] = result.observation
        for o in result.new_observations:
            current[o.id] = o
        write(sid, "observations.json", sorted(current.values(), key=lambda o: o.id))
        if result.question is not None:
            qs = [q for q in read(sid, "questions.json", Question, default=[]) if q.question_id != result.question.question_id]
            write(sid, "questions.json", qs + [result.question])


def append_model_calls(sid: str, calls: list[ModelCall]) -> None:
    with _LOCK:
        current = read(sid, "model_calls.json", ModelCall, default=[])
        write(sid, "model_calls.json", current + list(calls))


def reset(sid: str) -> None:
    shutil.rmtree(_root(sid), ignore_errors=True)
