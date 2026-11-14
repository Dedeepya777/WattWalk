"""Vision CLI (Appendix A.3). Owner: Person 2.

    python -m wattwalk.vision.cli inspect --sid <sid> --pano <pano> [--save-fixture]
    python -m wattwalk.vision.cli walk --sid <sid> [--save-fixture] [--reset]

walk runs plan_views + inspect_view + resolve and prints a table; no agent, no API.
Questions are asked on the terminal with the 30 s timeout.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import sys
from collections import Counter

from .. import config, store
from ..contracts import Question
from ..inventory import build_inventory, compute_coverage
from ..data.matterport import get_geometry
from .state import forget_reservations, load_state
from .walk import coverage_inputs, inspect_view, pending_observation_ids, plan_views, resolve


def terminal_ask(q: Question) -> str | None:
    timeout = config.TIMEOUTS_S["ask_user"]
    print(f"\n? {q.text}  choices: {', '.join(q.choices)}  ({timeout} s)")
    if not sys.stdin.isatty():
        print("  (no terminal; question expires)")
        return None
    if os.name == "nt":  # Windows: select() does not work on the console, so no timeout here
        answer = input("  answer: ").strip().lower()
        return answer if answer in q.choices else None
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        print("  expired")
        return None
    answer = sys.stdin.readline().strip().lower()
    return answer if answer in q.choices else None


def _print_obs(observations) -> None:
    print(f"{'obs':6} {'pano':6} {'face':4} {'label':14} {'anchor':24} attributes")
    for o in observations:
        anchor = f"({o.anchor.x}, {o.anchor.y}, {o.anchor.z})" if o.anchor else "none"
        attrs = ", ".join(f"{k}={a.value if a.value is not None else '?'}" for k, a in o.attrs.items())
        print(f"{o.id:6} {o.pano_id:6} {o.face:<4} {o.label:14} {anchor:24} {attrs}")


def _save_fixture(sid: str) -> None:
    if sid == config.FIXTURE_SID:
        print("not saving: fixtureUnitA is the shared example fixture")
        return
    folder = config.FIXTURES_DIR / "live" / sid
    folder.mkdir(parents=True, exist_ok=True)
    obs = [o.model_dump(mode="json") for o in store.observations(sid)]
    (folder / "observations.json").write_text(json.dumps(obs, indent=2), encoding="utf-8")
    meta = {"rejected_faces": [r.model_dump() for r in load_state(sid).rejected_faces]}
    (folder / "vision_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"saved {len(obs)} observations to {folder} (crops stay in audits/, never committed)")


def cmd_inspect(args) -> None:
    geometry = get_geometry(args.sid)
    pano = next((p for p in geometry.panos if p.id == args.pano), None)
    if pano is None:
        sys.exit(f"unknown pano {args.pano}")
    result = inspect_view(args.sid, geometry, pano.room_id, pano.id)
    store.append_observations(args.sid, result.observations)
    print(f"faces inspected {result.faces_inspected}, rejected {result.faces_rejected}, model calls {result.calls}")
    _print_obs(result.observations)
    if args.save_fixture:
        _save_fixture(args.sid)


def cmd_walk(args) -> None:
    sid = args.sid
    if args.reset:
        store.reset(sid)
        forget_reservations(sid)
    geometry = get_geometry(sid)
    tasks = plan_views(geometry)
    print(f"mode {config.effective_vision_mode()}; {len(tasks)} views planned")
    for t in tasks:
        r = inspect_view(sid, geometry, t.room_id, t.pano_id)
        store.append_observations(sid, r.observations)
        print(f"  {t.pano_id} ({t.reason}, room {t.room_id}): {len(r.observations)} detections, "
              f"faces rejected {r.faces_rejected}")
    actions: Counter[str] = Counter()
    for oid in pending_observation_ids(sid):
        while True:
            rr = resolve(sid, geometry, oid, terminal_ask)
            store.apply_resolve(sid, rr)
            actions[rr.action] += 1
            print(f"  {oid}: {rr.action:15} {rr.summary}")
            if rr.final:
                break
    observations = store.observations(sid)
    inventory = build_inventory(observations)
    reviewed, rejected, partial = coverage_inputs(sid, geometry)
    coverage = compute_coverage(geometry, observations, inventory, reviewed, rejected, partial)
    calls = store.read(sid, "model_calls.json", default=[]) or []
    by_tier = Counter((c["kind"], c["model_tier"]) for c in calls)
    print()
    _print_obs(observations)
    print(f"\n{len(observations)} observations -> {len(inventory)} assets; router actions {dict(actions)}")
    print(f"model calls {len(calls)}: {dict(by_tier)}; large calls {load_state(sid).large_calls}")
    print(f"coverage: rooms {coverage.rooms_reviewed}/{coverage.rooms_total}, faces rejected {coverage.faces_rejected}, "
          f"attrs known {coverage.attrs_known} unknown {coverage.attrs_unknown}, not visible {coverage.not_visible}")
    if args.save_fixture:
        _save_fixture(sid)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m wattwalk.vision.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="inspect one panorama")
    p.add_argument("--sid", required=True)
    p.add_argument("--pano", required=True)
    p.add_argument("--save-fixture", action="store_true")
    p.set_defaults(fn=cmd_inspect)
    w = sub.add_parser("walk", help="plan views, inspect them and resolve every observation")
    w.add_argument("--sid", required=True)
    w.add_argument("--save-fixture", action="store_true")
    w.add_argument("--reset", action="store_true", help="delete audits/<sid>/ first")
    w.set_defaults(fn=cmd_walk)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
