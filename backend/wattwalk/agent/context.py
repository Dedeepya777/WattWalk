"""Per-run state shared by the run loop, tools, ask callback and API. Owner: Person 3."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Literal, Optional

from ..errors import AuditCancelled
from .events import EventBus

Mode = Literal["live", "replay", "fixture"]


@dataclass
class RunContext:
    sid: str
    mode: Mode
    bus: EventBus
    cancel: threading.Event = field(default_factory=threading.Event)
    task: Optional[asyncio.Task] = None
    replay_speed: float = 1.0
    current_agent: str = "planner"

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise AuditCancelled(f"audit {self.sid} cancelled")

    def emit(self, agent: str, type: str, summary: str, data: Optional[dict] = None):
        return self.bus.emit(agent, type, summary, data)


_lock = threading.Lock()
_active: dict[str, RunContext] = {}   # running audits
_buses: dict[str, EventBus] = {}      # last bus per sid (kept after the run for SSE readers)


def register(ctx: RunContext) -> bool:
    with _lock:
        if ctx.sid in _active:
            return False
        _active[ctx.sid] = ctx
        _buses[ctx.sid] = ctx.bus
        return True


def release(sid: str) -> None:
    with _lock:
        _active.pop(sid, None)


def active(sid: str) -> Optional[RunContext]:
    with _lock:
        return _active.get(sid)


def bus_for(sid: str) -> Optional[EventBus]:
    with _lock:
        return _buses.get(sid)


def forget(sid: str) -> None:
    with _lock:
        _buses.pop(sid, None)
