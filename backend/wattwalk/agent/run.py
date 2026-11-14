"""Run loop (plan 12.1, H.1). Owner: Person 3."""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone

from .. import config, store
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

        from .providers import PLACEHOLDER_JPEG

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
        from .providers import fixture_files_present
        if not fixture_files_present(sid):
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
    ctx.task = asyncio.create_task(_run(ctx, replay_meta))
    return status


async def _run(ctx: RunContext, replay_meta: dict | None) -> None:
    from ..api import replay

    sid, mode, bus = ctx.sid, ctx.mode, ctx.bus
    token = config.RUN_MODE_OVERRIDE.set("fixture" if mode == "fixture" else None)
    final, err = "completed", None
    try:
        if mode == "replay":
            bus.emit("system", "status",
                     f"Replay of run recorded at {replay_meta['recorded_at']}: Audit started (mode replay)",
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
