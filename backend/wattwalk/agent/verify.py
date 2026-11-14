"""Audit verifier (plan 12.7): ten consistency checks over the audit folder. Owner: Person 3."""
from __future__ import annotations

import importlib
import json
import math

from pydantic import ValidationError

from .. import config, store
from ..contracts import Asset, Building, Coverage, Observation, PlanResponse
from . import providers as P

SAME_OBJECT_M = 0.5  # fallback same-object distance until Person 2's dedupe test is importable


def _same_object_fn():
    try:
        mod = importlib.import_module("wattwalk.inventory.dedupe")
        return getattr(mod, "same_object", None)
    except ImportError:
        return None


def _dist(a, b) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _attr_problems(owner: str, attrs: dict) -> list[str]:
    out = []
    for k, v in attrs.items():
        if (v.value is None) != (v.source == "needs_verification"):
            out.append(f"{owner}.{k}: value {v.value!r} with source {v.source} breaks the null-iff-needs_verification rule")
    return out


def verify_audit(sid: str) -> list[str]:
    problems: list[str] = []
    try:
        obs = store.read(sid, "observations.json", list[Observation], default=[])
        inv = store.read(sid, "inventory.json", list[Asset])
        cov = store.read(sid, "coverage.json", Coverage)
        plan_default = store.read(sid, "plan_default.json", PlanResponse)
        building = store.read(sid, "building.json", Building)
        rooms = store.read(sid, "rooms.json", default=None)
    except (ValidationError, json.JSONDecodeError) as e:
        return [f"audit files do not match the contracts: {str(e)[:180]}"]
    if inv is None:
        return ["inventory.json missing"]
    obs_by_id = {o.id: o for o in obs}

    # 1 evidence links: every observation id exists and belongs to one asset only
    owner: dict[str, str] = {}
    ids = [a.id for a in inv]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"asset id {dup} appears more than once")
    for a in inv:
        for oid in a.observation_ids:
            if oid not in obs_by_id:
                problems.append(f"{a.id} references missing observation {oid}")
            elif oid in owner and owner[oid] != a.id:
                problems.append(f"observation {oid} belongs to both {owner[oid]} and {a.id}")
            elif oid in owner:
                problems.append(f"observation {oid} listed twice under the same asset id {a.id}")
            owner[oid] = a.id

    # 2 no two assets would merge under the dedupe rule
    same = _same_object_fn()
    for i, a in enumerate(inv):
        for b in inv[i + 1:]:
            if a.label != b.label or a.scope != b.scope:
                continue
            if same is not None:
                try:
                    if same(a, b):
                        problems.append(f"{a.id} and {b.id} look like the same {a.label}")
                    continue
                except TypeError:
                    pass
            if a.room_id == b.room_id and a.anchor and b.anchor and _dist(a.anchor, b.anchor) < SAME_OBJECT_M:
                problems.append(f"{a.id} and {b.id} look like the same {a.label} (anchors {_dist(a.anchor, b.anchor):.2f} m apart)")

    # 3 Attr invariant
    for a in inv:
        problems += _attr_problems(a.id, a.attrs)
    if building:
        problems += _attr_problems("building", {k: getattr(building, k) for k in ("year_built", "units", "asking_rent_usd_month", "unit_floor_area_m2")})

    # 4 upgrade lines link to assets with an applicable label
    upgrades = {u["id"]: u for u in json.loads((config.CONTRACTS_DIR / "upgrades.json").read_text(encoding="utf-8"))["upgrades"]}
    inv_by_id = {a.id: a for a in inv}
    if plan_default is None:
        problems.append("plan_default.json missing")
    else:
        for line in plan_default.upgrades:
            spec = upgrades.get(line.upgrade_id)
            if spec is None:
                problems.append(f"upgrade {line.upgrade_id} is not in upgrades.json")
                continue
            if not line.asset_ids:
                problems.append(f"upgrade {line.upgrade_id} links to no asset")
            for aid in line.asset_ids:
                if aid not in inv_by_id:
                    problems.append(f"upgrade {line.upgrade_id} references missing asset {aid}")
                elif inv_by_id[aid].label not in spec["applies_to"]:
                    problems.append(f"upgrade {line.upgrade_id} references {aid} ({inv_by_id[aid].label}), not in applies_to")

        # 5 recompute the default plan
        if building is not None:
            try:
                again = P.plan(sid, inv, building, plan_default.request)
                if again.totals != plan_default.totals:
                    problems.append("stored default plan totals differ from a fresh engine run")
            except Exception as e:  # noqa: BLE001 - reported, not raised
                problems.append(f"engine could not recompute the default plan: {str(e)[:120]}")

        # 6 line kWh sums to the total
        s = sum(u.kwh_saved_yr for u in plan_default.upgrades)
        tol = 0.1 * max(len(plan_default.upgrades), 1)
        if abs(s - plan_default.totals.kwh_saved_yr) > tol + 1e-9:
            problems.append(f"line kWh sum {s:.1f} differs from total {plan_default.totals.kwh_saved_yr:.1f}")

        # 7 assumptions exist
        known = set(json.loads((config.CONTRACTS_DIR / "assumptions.json").read_text(encoding="utf-8"))["assumptions"])
        for au in plan_default.assumptions_used:
            if au.key not in known:
                problems.append(f"assumption {au.key} is not in assumptions.json")

    # 8 coverage counts
    if cov is None:
        problems.append("coverage.json missing")
    else:
        k = sum(1 for a in inv for v in a.attrs.values() if v.value is not None)
        u = sum(1 for a in inv for v in a.attrs.values() if v.value is None)
        checks = [("assets_unique", cov.assets_unique, len(inv)), ("observations_total", cov.observations_total, len(obs)),
                  ("attrs_known", cov.attrs_known, k), ("attrs_unknown", cov.attrs_unknown, u)]
        if rooms is not None:
            checks.append(("rooms_total", cov.rooms_total, len(rooms)))
        for name, got, want in checks:
            if got != want:
                problems.append(f"coverage {name} is {got} but the audit has {want}")

    # 9 unknown attributes have a next step
    for a in inv:
        if any(v.value is None for v in a.attrs.values()) and not a.next_step.strip():
            problems.append(f"{a.id} has unknown attributes but no next_step")

    # 10 crops exist
    for o in obs:
        if not (store.audit_dir(sid) / o.crop_ref).is_file():
            problems.append(f"crop {o.crop_ref} for {o.id} is missing")
    return problems
