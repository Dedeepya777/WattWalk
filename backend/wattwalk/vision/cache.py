"""LLM response cache (plan 8.3.5). Owner: Person 2.

Key: SHA-1 of model id + prompt text + image bytes, so a prompt change invalidates old entries.
Stored under audits/cache/llm/<key>.json (gitignored).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from .. import config


def cache_key(key_parts: tuple) -> str:
    h = hashlib.sha1()
    for part in key_parts:
        h.update(part if isinstance(part, bytes) else str(part).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _path(key: str) -> Path:
    return Path(config.CACHE_DIR) / "llm" / f"{key}.json"


def cached_call(key_parts: tuple, fn: Callable[[], tuple[str, dict]], enabled: bool = True) -> tuple[str, dict, bool]:
    """Return (text, usage, cache_hit). fn performs the real call and returns (text, usage)."""
    path = _path(cache_key(key_parts))
    if enabled and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["text"], data.get("usage", {}), True
    text, usage = fn()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"text": text, "usage": usage}, f)
        os.replace(tmp, path)
    return text, usage, False
