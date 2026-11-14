"""Replay of recorded runs (plan 12.8, D18). Owner: Person 3.

Record:   python -m wattwalk.api.replay promote <sid> [--force]
          copies audits/<sid>/events.jsonl and the audit JSON/Markdown files (no images) into
          demo/replays/<sid>/ and stores recorded_at = the run's started_at.
Playback: POST /audits/<sid> {"mode": "replay"}. Status mode is replay with replay_of = recorded_at,
          the first event summary starts with "Replay of run recorded at", events keep their original
          spacing (divided by ?speed= on the events endpoint), observations appear progressively at each
          finding event, and all snapshot files are copied when the replay finishes.
A replay is never presented as live.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from .. import config, store
from ..contracts import AuditStatus, Event, Observation

SNAPSHOT_SKIP = {"status.json", "events.jsonl", "agent_state.json"}


def replay_dir(sid: str) -> Path:
    store._check_sid(sid)
    return config.DEMO_DIR / "replays" / sid


def load_meta(sid: str) -> dict | None:
    d = replay_dir(sid)
    if not (d / "events.jsonl").exists() or not (d / "meta.json").exists():
        return None
    return json.loads((d / "meta.json").read_text(encoding="utf-8"))


def has_replay(sid: str) -> bool:
    return (replay_dir(sid) / "events.jsonl").exists()


def promote(sid: str, force: bool = False) -> Path:
    st = store.read(sid, "status.json", AuditStatus)
    if st is None:
        raise SystemExit(f"No audit for {sid} in {config.AUDITS_DIR}")
    if not force and (st.status != "completed" or st.mode != "live"):
        raise SystemExit(f"Only completed live runs are promoted (status {st.status}, mode {st.mode}); use --force to override")
    src, dst = store.audit_dir(sid), replay_dir(sid)
    if dst.exists():
        shutil.rmtree(dst)
    snap = dst / "audit_snapshot"
    snap.mkdir(parents=True)
    shutil.copy(src / "events.jsonl", dst / "events.jsonl")
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if p.is_file() and p.suffix in (".json", ".md") and rel.as_posix() not in SNAPSHOT_SKIP:
            (snap / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, snap / rel)
    meta = {"sid": sid, "recorded_at": st.started_at, "recorded_mode": st.mode, "finished_at": st.finished_at}
    (dst / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dst


def _copy_snapshot(sid: str) -> None:
    snap = replay_dir(sid) / "audit_snapshot"
    for p in snap.rglob("*"):
        if p.is_file():
            rel = p.relative_to(snap)
            target = store.audit_path(sid, *rel.parts)
            store.write_text_atomic(target, p.read_text(encoding="utf-8"))


async def play(ctx, meta: dict) -> None:
    sid = ctx.sid
    d = replay_dir(sid)
    recorded = [Event.model_validate_json(l) for l in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    snap_obs_path = d / "audit_snapshot" / "observations.json"
    snap_obs = {o["id"]: o for o in json.loads(snap_obs_path.read_text(encoding="utf-8"))} if snap_obs_path.exists() else {}
    # Static context the UI needs to draw the plan as soon as the walk starts.
    for name in ("geometry.json", "rooms.json", "panos.json"):
        p = d / "audit_snapshot" / name
        if p.exists():
            store.write_text_atomic(store.audit_path(sid, name), p.read_text(encoding="utf-8"))
    shown: list[str] = []
    prev_t = 0.0
    for ev in recorded:
        if ev.seq == 0 and ev.type == "status":
            continue  # the run loop already emitted the labeled replay start
        if ev.type == "done":
            break  # the run loop emits its own done
        ctx.check_cancel()
        delay = max(ev.t_s - prev_t, 0.0) / max(ctx.replay_speed, 0.01)
        prev_t = ev.t_s
        if delay:
            await asyncio.sleep(delay)
        ctx.check_cancel()
        if ev.type == "finding":
            for oid in ev.data.get("observation_ids", []):
                if oid in snap_obs and oid not in shown:
                    shown.append(oid)
            store.write(sid, "observations.json", [Observation.model_validate(snap_obs[o]) for o in shown])
        if ev.type == "question":
            # Recorded questions are shown, never re-asked: the recorded outcome follows in the log.
            data = {**ev.data, "replay": True}
        else:
            data = ev.data
        ctx.bus.emit(ev.agent, ev.type, ev.summary, data, t_s=ev.t_s)
    _copy_snapshot(sid)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wattwalk.api.replay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("promote", help="record a finished live run as a replay")
    pr.add_argument("sid")
    pr.add_argument("--force", action="store_true", help="allow non-live or non-completed runs (still labeled replay)")
    args = ap.parse_args(argv)
    if args.cmd == "promote":
        dst = promote(args.sid, args.force)
        print(f"Replay recorded in {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
