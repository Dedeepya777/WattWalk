"""Health registry: the outcome of the last real call per integration. Owner: Person 3.

Adapters, probes and the run loop call record() after a real provider call; GET /health reads
status(). In memory, thread-safe, no persistence: after a restart every live integration reports
"unavailable" until a probe (GET /health?probe=1) or a real call succeeds.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_last: dict[str, tuple[bool, str, float]] = {}  # integration -> (ok, detail, unix time)
INTEGRATIONS = ("matterport", "vexcel", "costar_kit", "ebewe", "bedrock")
MAX_AGE_S = 600


def _check(integration: str) -> None:
    if integration not in INTEGRATIONS:
        raise ValueError(f"unknown integration {integration!r}; expected one of {INTEGRATIONS}")


def record(integration: str, ok: bool, detail: str = "") -> None:
    """Store the outcome of a real call (never call this for fixture data)."""
    _check(integration)
    with _lock:
        _last[integration] = (bool(ok), detail[:300], time.time())


def last(integration: str) -> tuple[bool, str, float] | None:
    _check(integration)
    with _lock:
        return _last.get(integration)


def status(integration: str, configured: bool, mode_is_fixture: bool, max_age_s: int = MAX_AGE_S) -> str:
    """'fixture' if the relevant mode is fixture; 'unavailable' if not configured, never tested, last call
    failed, or the last success is older than max_age_s; otherwise 'live'."""
    if mode_is_fixture:
        return "fixture"
    if not configured:
        return "unavailable"
    entry = last(integration)
    if entry is None:
        return "unavailable"
    ok, _, at = entry
    return "live" if ok and time.time() - at <= max_age_s else "unavailable"


def clear() -> None:
    """Forget every outcome (tests)."""
    with _lock:
        _last.clear()
