"""Event bus: in-memory fan-out plus append to audits/{sid}/events.jsonl. Owner: Person 3.

emit() is thread-safe (tools run in worker threads); subscribe() is an async iterator used by SSE.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import AsyncIterator, Optional

from .. import store
from ..contracts import Event

HEARTBEAT_S = 15.0


class EventBus:
    def __init__(self, sid: str):
        self.sid = sid
        self._t0 = time.monotonic()
        self._lock = threading.Lock()
        self._events: list[Event] = []
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []
        self.closed = False
        path = store.audit_path(sid, "events.jsonl")
        path.write_text("", encoding="utf-8")

    def emit(self, agent: str, type: str, summary: str, data: Optional[dict] = None, t_s: Optional[float] = None) -> Event:
        with self._lock:
            if self.closed:
                raise RuntimeError("event bus closed")
            if len(summary) > 200:
                summary = summary[:197] + "..."
            ev = Event(
                seq=len(self._events),
                t_s=round(t_s if t_s is not None else time.monotonic() - self._t0, 2),
                sid=self.sid, agent=agent, type=type, summary=summary, data=data or {},
            )
            self._events.append(ev)
            with open(store.audit_path(self.sid, "events.jsonl"), "a", encoding="utf-8", newline="\n") as f:
                f.write(ev.model_dump_json() + "\n")
            if type == "done":
                self.closed = True
            waiters, self._waiters = self._waiters, []
        for loop, flag in waiters:
            try:
                loop.call_soon_threadsafe(flag.set)
            except RuntimeError:  # loop closed
                pass
        return ev

    @property
    def events(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    async def subscribe(self, from_seq: int = 0, heartbeat_s: float = HEARTBEAT_S) -> AsyncIterator[Optional[Event]]:
        """Yields stored events with seq >= from_seq, then live ones; yields None as a heartbeat."""
        nxt = max(from_seq, 0)
        loop = asyncio.get_running_loop()
        while True:
            flag = asyncio.Event()
            with self._lock:
                pending = self._events[nxt:]
                closed = self.closed
                if not pending and not closed:
                    self._waiters.append((loop, flag))
            for ev in pending:
                yield ev
                nxt = ev.seq + 1
                if ev.type == "done":
                    return
            if pending:
                continue
            if closed:
                return
            try:
                await asyncio.wait_for(flag.wait(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield None


def stored_events(sid: str) -> list[Event]:
    text = store.read_text(sid, "events.jsonl") or ""
    return [Event.model_validate_json(line) for line in text.splitlines() if line.strip()]


async def subscribe_stored(sid: str, from_seq: int = 0) -> AsyncIterator[Optional[Event]]:
    """Used when no bus is in memory (for example after a server restart): stored events only."""
    for ev in stored_events(sid):
        if ev.seq >= from_seq:
            yield ev


def dumps(ev: Event) -> str:
    return json.dumps(ev.model_dump(mode="json"), ensure_ascii=False)
