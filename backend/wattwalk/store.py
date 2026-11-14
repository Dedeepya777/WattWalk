"""Audit store: JSON files per audit under config.AUDITS_DIR/{sid}/. Owner: Person 3.

All writes are atomic (temp file in the same folder, then os.replace). A per-sid lock serialises
read-modify-write helpers so the agent thread and API handlers never interleave updates.
Canonical signatures: shared/contracts/README.md section 5.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from . import config
from .contracts import ModelCall, Observation, Question

T = TypeVar("T")

_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_locks_guard = threading.Lock()


def lock(sid: str) -> threading.RLock:
    with _locks_guard:
        return _locks[sid]


def _check_sid(sid: str) -> None:
    if not sid or sid in (".", "..", "cache") or any(c in sid for c in "/\\:") or sid.startswith("."):
        raise ValueError(f"invalid sid {sid!r}")


def audit_dir(sid: str) -> Path:
    _check_sid(sid)
    return config.AUDITS_DIR / sid


def exists(sid: str) -> bool:
    return audit_dir(sid).is_dir()


def audit_path(sid: str, *parts: str) -> Path:
    """Path inside the audit folder; creates parent folders. Used for crops and per-audit caches."""
    p = audit_dir(sid).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        # os.replace can transiently fail on Windows if a reader holds the file; retry briefly.
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                threading.Event().wait(0.01)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write(sid: str, name: str, obj) -> None:
    """Atomic JSON write of a pydantic model, list of models or plain JSON value."""
    path = audit_path(sid, name)
    if isinstance(obj, str) and not name.endswith(".json"):
        write_text_atomic(path, obj)
    else:
        write_text_atomic(path, json.dumps(_to_jsonable(obj), indent=2, ensure_ascii=False))


def read(sid: str, name: str, model: type[T] | Any | None = None, default=None):
    """Read a JSON file from the audit folder. With model (a class or e.g. list[Asset]) the data is validated."""
    path = audit_dir(sid) / name
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    if not name.endswith(".json"):
        return text
    data = json.loads(text)
    if model is None:
        return data
    return TypeAdapter(model).validate_python(data)


def read_text(sid: str, name: str) -> str | None:
    path = audit_dir(sid) / name
    return path.read_text(encoding="utf-8") if path.exists() else None


def observations(sid: str) -> list[Observation]:
    return sorted(
        read(sid, "observations.json", list[Observation], default=[]),
        key=lambda o: o.id,
    )


def append_observations(sid: str, obs: list[Observation]) -> None:
    with lock(sid):
        current = observations(sid)
        known = {o.id for o in current}
        for o in obs:
            if o.id in known:
                current = [o if c.id == o.id else c for c in current]
            else:
                current.append(o)
                known.add(o.id)
        write(sid, "observations.json", sorted(current, key=lambda o: o.id))


def upsert_question(sid: str, q: Question) -> None:
    with lock(sid):
        qs = read(sid, "questions.json", list[Question], default=[])
        qs = [x for x in qs if x.question_id != q.question_id] + [q]
        qs.sort(key=lambda x: x.question_id)
        write(sid, "questions.json", qs)


def questions(sid: str) -> list[Question]:
    return read(sid, "questions.json", list[Question], default=[])


def apply_resolve(sid: str, result) -> None:
    """Replace the updated observation, append new ones, record the question (ResolveResult from Person 2)."""
    with lock(sid):
        updates = []
        if getattr(result, "observation", None) is not None:
            updates.append(result.observation)
        updates.extend(getattr(result, "new_observations", None) or [])
        if updates:
            append_observations(sid, updates)
        q = getattr(result, "question", None)
        if q is not None:
            # The ask callback already stored the authoritative status; keep a later status if present.
            existing = {x.question_id: x for x in questions(sid)}.get(q.question_id)
            if existing is None or existing.status == "open":
                upsert_question(sid, q)


def append_model_calls(sid: str, calls: list[ModelCall]) -> None:
    if not calls:
        return
    with lock(sid):
        current = read(sid, "model_calls.json", list[ModelCall], default=[])
        write(sid, "model_calls.json", current + list(calls))


def reset(sid: str) -> None:
    """Remove the audit folder. Caches live in config.CACHE_DIR (audits/cache) and are kept."""
    with lock(sid):
        d = audit_dir(sid)
        if d.exists():
            shutil.rmtree(d)
