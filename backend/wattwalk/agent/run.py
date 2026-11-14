"""Run loop (plan 12.1, H.1). Owner: Person 3."""
from __future__ import annotations

import asyncio
import base64
import logging
import shutil
from datetime import datetime, timezone

from .. import config, health_registry, store
from ..contracts import AuditStatus, Error, ErrorBody
from ..errors import AuditCancelled, UpstreamError
from . import context
from .context import Mode, RunContext
from .events import EventBus

log = logging.getLogger("wattwalk.run")

# Files that belong to one run and are cleared before a new run of the same sid.
RUN_SCOPED = ["events.jsonl", "agent_state.json", "router_state.json", "verify.json", "view_tasks.json"]


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


# A 1x1 grey JPEG written as the crop and roof image of the illustrative fixture run, so links resolve.
PLACEHOLDER_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


def fixture_available(sid: str) -> bool:
    """A fixture run is possible for the illustrative apartment, or for a real sid whose owners
    committed both fixtures/live/<sid>/geometry.json (Person 1) and observations.json (Person 2)."""
    if sid == config.FIXTURE_SID:
        return True
    d = config.FIXTURES_DIR / "live" / sid
    return (d / "geometry.json").is_file() and (d / "observations.json").is_file()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_running(sid: str) -> bool:
    return context.active(sid) is not None


def current_status(sid: str) -> AuditStatus | None:
    return store.read(sid, "status.json", AuditStatus)


def _error(code: str, message: str, retryable: bool, details: dict | None = None) -> Error:
    return Error(error=ErrorBody(code=code, message=message, retryable=retryable, details=details or {}))


def _prepare_fixture(sid: str) -> None:
    store.reset(sid)
    store.audit_dir(sid).mkdir(parents=True, exist_ok=True)
    if sid == config.FIXTURE_SID:
        # Illustrative model-call log for the fixture run. Person 2's fixture
        # replay does not append calls while RUN_MODE_OVERRIDE is "fixture", so
        # this stays the authoritative 41-call example.
        shutil.copy(config.EXAMPLES_DIR / "model_calls.json", store.audit_path(sid, "model_calls.json"))
        # Fixture crop and roof links must resolve without provider imagery.
        import json

        for item in json.loads((config.EXAMPLES_DIR / "observations.json").read_text(encoding="utf-8")):
            path = store.audit_path(sid, item["crop_ref"])
            if not path.exists():
                path.write_bytes(PLACEHOLDER_JPEG)
        store.audit_path(sid, "vexcel", "ortho.jpg").write_bytes(PLACEHOLDER_JPEG)


async def start_run(sid: str, mode: Mode) -> AuditStatus:
    from ..api import replay  # late import: api depends on agent

    if is_running(sid):
        raise Conflict(sid)
    if mode == "fixture":
        if not fixture_available(sid):
            raise NotFound(f"No fixture exists for sid {sid}.")
    replay_meta = None
    if mode == "replay":
        replay_meta = replay.load_meta(sid)
        if replay_meta is None:
            raise NotFound(f"No recorded replay exists for sid {sid}.")

    if mode == "fixture":
        _prepare_fixture(sid)
    elif mode == "replay":
        store.reset(sid)
    for name in RUN_SCOPED:
        p = store.audit_dir(sid) / name
        if p.exists():
            p.unlink()
    store.audit_dir(sid).mkdir(parents=True, exist_ok=True)

    status = AuditStatus(sid=sid, status="running", mode=mode, started_at=now(), finished_at=None, error=None,
                         replay_of=replay_meta["recorded_at"] if replay_meta else None)
    ctx = RunContext(sid=sid, mode=mode, bus=EventBus(sid))
    if not context.register(ctx):
        raise Conflict(sid)
    store.write(sid, "status.json", status)
    if mode != "replay":
        store.write(sid, "run_modes.json", run_modes(mode))
    ctx.task = asyncio.create_task(_run(ctx, replay_meta))
    return status


def run_modes(mode: Mode) -> dict:
    """The modes a run actually used (a fixture run forces fixture data and vision and the scripted agent)."""
    if mode == "fixture":
        return {"data_mode": "fixture", "vision_mode": "fixture", "agent_mode": "scripted"}
    return {"data_mode": config.DATA_MODE, "vision_mode": config.VISION_MODE, "agent_mode": config.AGENT_MODE}


def replay_label(meta: dict) -> str:
    """Prefix of the first replay event: when it was recorded and with which modes."""
    return (f"Replay of run recorded at {meta['recorded_at']} (data {meta.get('data_mode', 'unknown')}, "
            f"vision {meta.get('vision_mode', 'unknown')}, agent {meta.get('agent_mode', 'unknown')}): ")


async def _run(ctx: RunContext, replay_meta: dict | None) -> None:
    from ..api import replay

    sid, mode, bus = ctx.sid, ctx.mode, ctx.bus
    token = config.RUN_MODE_OVERRIDE.set("fixture" if mode == "fixture" else None)
    final, err = "completed", None
    try:
        if mode == "replay":
            bus.emit("system", "status", replay_label(replay_meta) + "Audit started (mode replay)",
                     {"status": "running", "replay_of": replay_meta["recorded_at"]})
            await replay.play(ctx, replay_meta)
        else:
            bus.emit("system", "status", f"Audit started (mode {mode})", {"status": "running"})
            if mode == "fixture" or config.AGENT_MODE == "scripted":
                from . import scripted
                await asyncio.to_thread(scripted.run, ctx)
            else:
                from . import deep
                await asyncio.to_thread(deep.run, ctx)
    except AuditCancelled:
        final = "cancelled"
    except asyncio.CancelledError:
        final = "cancelled"
    except UpstreamError as e:
        final, err = "failed", _error(e.code, e.message, e.retryable, {"integration": e.integration})
        if mode == "live" and e.integration in health_registry.INTEGRATIONS:
            health_registry.record(e.integration, False, e.message)
    except Exception as e:  # noqa: BLE001
        log.exception("audit %s failed", sid)
        final, err = "failed", _error("internal", (str(e) or type(e).__name__)[:300], False)
    finally:
        config.RUN_MODE_OVERRIDE.reset(token)
        if ctx.cancel.is_set() and final == "completed":
            final = "cancelled"
        try:
            if err:
                data = {"code": err.error.code, **({"integration": err.error.details["integration"]}
                                                   if "integration" in err.error.details else {})}
                bus.emit("system", "error", err.error.message[:200], data)
            summary = {"completed": "Audit completed", "cancelled": "Audit cancelled"}.get(
                final, f"Audit failed: {err.error.code if err else 'internal'}")
            cur = store.read(sid, "status.json", AuditStatus)
            if cur is not None:
                store.write(sid, "status.json", cur.model_copy(update={"status": final, "finished_at": now(), "error": err}))
            bus.emit("system", "done", summary, {"status": final})
        finally:
            context.release(sid)


async def cancel_run(sid: str) -> AuditStatus:
    ctx = context.active(sid)
    if ctx is None:
        st = current_status(sid)
        if st is None:
            raise NotFound(sid)
        return st
    ctx.cancel.set()
    if ctx.mode == "replay" and ctx.task is not None:
        ctx.task.cancel()  # replay waits on asyncio.sleep; tools in worker threads check the flag
    # Wait briefly so the response usually already says cancelled (the loop stops within one tool call).
    for _ in range(40):
        if context.active(sid) is None:
            break
        await asyncio.sleep(0.05)
    return current_status(sid)


def reset(sid: str) -> AuditStatus:
    if is_running(sid):
        raise Conflict(sid)
    mode = (current_status(sid).mode if store.exists(sid) and current_status(sid) else "live")
    store.reset(sid)
    context.forget(sid)
    return AuditStatus(sid=sid, status="idle", mode=mode)
