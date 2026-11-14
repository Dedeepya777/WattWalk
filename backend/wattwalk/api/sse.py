"""Server-sent events for GET /audits/{sid}/events (plan H.4). Owner: Person 3."""
from __future__ import annotations

from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from ..agent import context
from ..agent.events import HEARTBEAT_S, subscribe_stored


async def _gen(sid: str, from_seq: int, heartbeat_s: float) -> AsyncIterator[str]:
    bus = context.bus_for(sid)
    source = bus.subscribe(from_seq, heartbeat_s) if bus is not None else subscribe_stored(sid, from_seq)
    async for ev in source:
        if ev is None:
            yield ": keepalive\n\n"
            continue
        yield f"data: {ev.model_dump_json()}\n\n"
        if ev.type == "done":
            return


def stream(sid: str, from_seq: int = 0, speed: float = 1.0, heartbeat_s: float = HEARTBEAT_S) -> StreamingResponse:
    ctx = context.active(sid)
    if ctx is not None and ctx.mode == "replay" and speed and speed > 0:
        ctx.replay_speed = speed
    return StreamingResponse(_gen(sid, from_seq, heartbeat_s), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
