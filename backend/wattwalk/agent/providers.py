"""Single entry point from the agent and API to the other owners' modules. Owner: Person 3.

Each function has the canonical signature from shared/contracts/README.md section 5. It calls the
real implementation when the owner's module is importable, and otherwise falls back to a
TEMPORARY stub that serves shared/examples/ data for the fixture apartment (fixtureUnitA).

TEMPORARY until Person 1 delivers: get_geometry, get_building, plan, heat_shares, explain_template.
TEMPORARY until Person 2 delivers: plan_views, inspect_view, resolve, build_inventory,
compute_coverage, apply_correction, vision types.
Stubs never pretend to be live: they only serve the fixture sid and say so in their errors and notes.
Delete a stub once the real function has landed on main (the real one already wins at import).
"""
from __future__ import annotations

import base64
import importlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field, TypeAdapter

from .. import config, store
from ..contracts import (
    Asset,
    Attr,
    Building,
    CorrectionRequest,
    CorrectionResponse,
    Coverage,
    HeatShare,
    ModelGeometry,
    Observation,
    PlanRequest,
    PlanResponse,
    Question,
    Room,
)


class StubLimitation(RuntimeError):
    """Raised when a temporary stub cannot answer honestly (owner module not integrated yet)."""


def _real(module: str, name: str):
    try:
        return getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        return None


def implementation_status() -> dict[str, str]:
    """'real' or 'stub' per canonical function; shown in the handoff and logs."""
    names = {
        "get_geometry": ("wattwalk.data.matterport", "get_geometry"),
        "get_building": ("wattwalk.data.building", "get_building"),
        "plan": ("wattwalk.engine", "plan"),
        "heat_shares": ("wattwalk.engine", "heat_shares"),
        "explain_template": ("wattwalk.engine", "explain_template"),
        "plan_views": ("wattwalk.vision.walk", "plan_views"),
        "inspect_view": ("wattwalk.vision.walk", "inspect_view"),
        "resolve": ("wattwalk.vision.walk", "resolve"),
        "build_inventory": ("wattwalk.inventory", "build_inventory"),
        "compute_coverage": ("wattwalk.inventory", "compute_coverage"),
        "apply_correction": ("wattwalk.inventory", "apply_correction"),
    }
    return {k: ("real" if _real(*v) else "stub") for k, v in names.items()}


# --------------------------------------------------------------------------- vision types
_types = None
try:
    _types = importlib.import_module("wattwalk.vision.types")
except ImportError:
    pass

if _types is not None and all(hasattr(_types, n) for n in ("ViewTask", "InspectResult", "ResolveResult")):
    ViewTask = _types.ViewTask
    InspectResult = _types.InspectResult
    ResolveResult = _types.ResolveResult
else:  # TEMPORARY until Person 2 delivers vision/types.py (fields from plan section 7.13)

    class ViewTask(BaseModel):  # type: ignore[no-redef]
        room_id: Optional[str]
        pano_id: str
        reason: Literal["best_view", "second_view_large_room", "neighbor_view", "no_rooms_fallback"]

    class InspectResult(BaseModel):  # type: ignore[no-redef]
        observations: list[Observation]
        faces_inspected: list[int]
        faces_rejected: list[int]
        calls: int

    class ResolveResult(BaseModel):  # type: ignore[no-redef]
        observation_id: str
        action: Literal["accept", "hires_crop", "neighbor_view", "escalate_large", "ask_user", "leave_unknown"]
        observation: Optional[Observation] = None
        new_observations: list[Observation] = Field(default_factory=list)
        question: Optional[Question] = None
        final: bool
        summary: str


AskFn = Callable[[Question], Optional[str]]


# --------------------------------------------------------------------------- example data
@lru_cache(maxsize=None)
def _example_text(name: str) -> str:
    return (config.EXAMPLES_DIR / name).read_text(encoding="utf-8")


def _example(name: str):
    return json.loads(_example_text(name))


def _require_fixture_sid(sid: str, who: str) -> None:
    if sid != config.FIXTURE_SID:
        raise StubLimitation(
            f"{who} is not integrated yet; the temporary stub only serves {config.FIXTURE_SID}"
        )


def _canon(obj) -> str:
    return json.dumps(store._to_jsonable(obj), sort_keys=True)


# A 1x1 grey JPEG used as a placeholder crop by the fixture stub, so crop links resolve.
PLACEHOLDER_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


# --------------------------------------------------------------------------- Person 1
def get_geometry(sid: str) -> ModelGeometry:
    fn = _real("wattwalk.data.matterport", "get_geometry")
    if fn:
        return fn(sid)
    _require_fixture_sid(sid, "Person 1 Matterport adapter")
    return ModelGeometry.model_validate(_example("model_geometry.json"))


def get_building(sid: str, geometry: ModelGeometry) -> Building:
    fn = _real("wattwalk.data.building", "get_building")
    if fn:
        return fn(sid, geometry)
    _require_fixture_sid(sid, "Person 1 building adapter")
    return Building.model_validate(_example("building.json"))


@lru_cache(maxsize=1)
def _plan_table() -> dict[tuple[str, str], dict]:
    base_inv = _canon(_example("inventory.json"))
    table: dict[tuple[str, str], dict] = {}
    for req_path in sorted(config.EXAMPLES_DIR.glob("plan_request_*.json")):
        resp_path = req_path.with_name(req_path.name.replace("plan_request_", "plan_response_"))
        req = PlanRequest.model_validate_json(req_path.read_text(encoding="utf-8"))
        table[(base_inv, _canon(req))] = json.loads(resp_path.read_text(encoding="utf-8"))
    corr = _example("correction_response.json")
    table[(_canon(corr["inventory"]), _canon(PlanRequest.model_validate(corr["plan"]["request"])))] = corr["plan"]
    return table


def _scalar_override_keys() -> set[str]:
    a = json.loads((config.CONTRACTS_DIR / "assumptions.json").read_text(encoding="utf-8"))["assumptions"]
    return {k for k, v in a.items() if isinstance(v, dict) and "value" in v} | {"electricity_rate_usd_per_kwh"}


def plan(sid: str, inventory: list[Asset], building: Building, req: PlanRequest) -> PlanResponse:
    fn = _real("wattwalk.engine", "plan")
    if fn:
        return fn(sid, inventory, building, req)
    bad = sorted(set(req.overrides) - _scalar_override_keys())
    if bad:
        raise ValueError(f"overrides: unknown or non-scalar assumption key {bad[0]}")
    _require_fixture_sid(sid, "Person 1 engine")
    table = _plan_table()
    inv, rq = _canon(inventory), _canon(req)
    hit = table.get((inv, rq))
    if hit is None:
        # Inventory differs from the examples (for example an answered question): reuse the example
        # numbers for the same request, but say so in notes so nobody mistakes them for engine output.
        hit = next((v for (i, r), v in table.items() if r == rq and i == _canon(_example("inventory.json"))), None)
        if hit is None:
            raise StubLimitation("Person 1 engine is not integrated yet; the stub only serves the six example plan requests")
        hit = json.loads(json.dumps(hit))
        hit["notes"] = list(hit["notes"]) + ["TEMPORARY stub engine: example numbers; inventory changes are not reflected"]
    return PlanResponse.model_validate(hit)


def heat_shares(rooms: list[Room], inventory: list[Asset], building: Building) -> list[HeatShare]:
    fn = _real("wattwalk.engine", "heat_shares")
    if fn:
        return fn(rooms, inventory, building)
    return TypeAdapter(list[HeatShare]).validate_python(_example("heat_shares.json"))


def explain_template(plan_resp: PlanResponse, upgrade_id: str) -> str:
    fn = _real("wattwalk.engine", "explain_template")
    if fn:
        return fn(plan_resp, upgrade_id)
    ex_req = _example("explain_request.json")
    if upgrade_id == ex_req["upgrade_id"] and _canon(plan_resp.request) == _canon(PlanRequest.model_validate(ex_req["plan_request"])):
        return _example("explain_response.json")["text"]
    line = next(u for u in plan_resp.upgrades if u.upgrade_id == upgrade_id)
    return (
        f"{line.name}: {line.kwh_saved_yr:.1f} kWh/yr, ${line.bill_saved_usd_yr:,.2f} per year; "
        f"cost ${line.cost_low_usd:,.0f} to ${line.cost_high_usd:,.0f}. "
        "(Temporary template until Person 1's explain_template lands.)"
    )


# --------------------------------------------------------------------------- Person 2
def plan_views(geometry: ModelGeometry) -> list[ViewTask]:
    fn = _real("wattwalk.vision.walk", "plan_views")
    if fn:
        return fn(geometry)
    _require_fixture_sid(geometry.sid, "Person 2 view planner")
    tasks = []
    for room in geometry.rooms:
        for i, pid in enumerate(room.pano_ids):
            tasks.append(ViewTask(room_id=room.id, pano_id=pid, reason="best_view" if i == 0 else "second_view_large_room"))
    return tasks


_REJECTED_FACES = {"p05": [2]}  # fixture: bathroom face too dark (coverage.json)


def inspect_view(sid: str, geometry: ModelGeometry, room_id: str, pano_id: str) -> InspectResult:
    fn = _real("wattwalk.vision.walk", "inspect_view")
    if fn:
        return fn(sid, geometry, room_id, pano_id)
    _require_fixture_sid(sid, "Person 2 vision")
    obs = [Observation.model_validate(o) for o in _example("observations.json") if o["pano_id"] == pano_id]
    for o in obs:
        p = store.audit_path(sid, o.crop_ref)
        if not p.exists():
            p.write_bytes(PLACEHOLDER_JPEG)
    rejected = _REJECTED_FACES.get(pano_id, [])
    return InspectResult(observations=obs, faces_inspected=[f for f in (1, 2, 3, 4) if f not in rejected],
                         faces_rejected=rejected, calls=0)


# Fixture router ladder that reproduces the narrative in shared/examples/events.jsonl.
_STUB_LADDER = {
    "o005": ["hires_crop", "leave_unknown"],
    "o006": ["hires_crop", "leave_unknown"],
    "o007": ["hires_crop", "escalate_large", "ask_user"],
    "o008": ["hires_crop", "leave_unknown"],
}
_STUB_QUESTION = {
    "o007": dict(question_id="q001", asset_id="a_o007", attr="bulb_type",
                 text="What type of bulb is in the bedroom ceiling light?",
                 choices=["led", "cfl", "incandescent", "unknown"]),
}


def resolve(sid: str, geometry: ModelGeometry, observation_id: str, ask: AskFn) -> ResolveResult:
    fn = _real("wattwalk.vision.walk", "resolve")
    if fn:
        return fn(sid, geometry, observation_id, ask)
    _require_fixture_sid(sid, "Person 2 router")
    with store.lock(sid):
        state = store.read(sid, "router_state.json", default={"tried": {}})
        tried = state["tried"].setdefault(observation_id, [])
        ladder = _STUB_LADDER.get(observation_id, ["accept"])
        action = ladder[min(len(tried), len(ladder) - 1)]
        tried.append(action)
        store.write(sid, "router_state.json", state)
    final = len(tried) >= len(ladder)
    if action == "ask_user":
        q = Question(status="open", answer=None, **_STUB_QUESTION[observation_id])
        answer = ask(q)
        obs = next(o for o in store.observations(sid) if o.id == observation_id)
        if answer and answer in q.choices and answer != "unknown":
            obs = obs.model_copy(deep=True)
            obs.attrs[q.attr] = Attr(value=answer, source="provided_by_user", note="answered during the walk",
                                     evidence_obs_ids=[observation_id])
            q = q.model_copy(update={"status": "answered", "answer": answer})
            return ResolveResult(observation_id=observation_id, action=action, observation=obs, question=q,
                                 final=True, summary=f"{observation_id}: ask_user, {q.attr} = {answer} (provided by user)")
        q = q.model_copy(update={"status": "expired"})
        return ResolveResult(observation_id=observation_id, action=action, observation=None, question=q, final=True,
                             summary=f"{observation_id}: ask_user, no answer; {q.attr} left unknown")
    outcome = {"accept": "accepted", "hires_crop": "bulb type still not visible", "escalate_large": "bulb type still unknown",
               "leave_unknown": "left unknown with next step"}.get(action, action)
    return ResolveResult(observation_id=observation_id, action=action, observation=None, final=final,
                         summary=f"{observation_id}: {action}, {outcome}")


def build_inventory(observations: list[Observation]) -> list[Asset]:
    fn = _real("wattwalk.inventory", "build_inventory")
    if fn:
        return fn(observations)
    by_id = {o.id: o for o in observations}
    inv = []
    for a in TypeAdapter(list[Asset]).validate_python(_example("inventory.json")):
        if not all(oid in by_id for oid in a.observation_ids):
            continue
        for oid in a.observation_ids:  # carry user answers from observations to the asset
            for k, v in by_id[oid].attrs.items():
                if v.source == "provided_by_user":
                    a.attrs[k] = v
                    a.next_step = ""
        inv.append(a)
    return inv


def _attr_counts(inventory: list[Asset]) -> tuple[int, int]:
    known = sum(1 for a in inventory for v in a.attrs.values() if v.value is not None)
    unknown = sum(1 for a in inventory for v in a.attrs.values() if v.value is None)
    return known, unknown


def compute_coverage(geometry: ModelGeometry, observations: list[Observation], inventory: list[Asset],
                     reviewed: dict[str, list[str]], faces_rejected: int, partial_rooms: dict[str, str]) -> Coverage:
    fn = _real("wattwalk.inventory", "compute_coverage")
    if fn:
        return fn(geometry, observations, inventory, reviewed, faces_rejected, partial_rooms)
    cov = Coverage.model_validate(_example("coverage.json"))
    known, unknown = _attr_counts(inventory)
    return cov.model_copy(update={"assets_unique": len(inventory), "observations_total": len(observations),
                                  "attrs_known": known, "attrs_unknown": unknown, "faces_rejected": faces_rejected})


def apply_correction(inventory: list[Asset], observations: list[Observation], req: CorrectionRequest) -> tuple[list[Asset], list[str]]:
    fn = _real("wattwalk.inventory", "apply_correction")
    if fn:
        return fn(inventory, observations, req)
    ex = _example("correction_request.json")
    if (req.asset_id, req.field, req.value) == (ex["asset_id"], ex["field"], ex["value"]) and \
            _canon(inventory) == _canon(_example("inventory.json")):
        resp = CorrectionResponse.model_validate(_example("correction_response.json"))
        return resp.inventory, resp.changed_asset_ids
    target = next((a for a in inventory if a.id == req.asset_id), None)
    if target is None:
        raise KeyError(req.asset_id)
    if req.field in ("label", "merge_into"):
        raise StubLimitation("label and merge_into corrections need Person 2's apply_correction")
    if req.field not in target.attrs:
        raise ValueError(f"field {req.field} is not an attribute of {target.label}")
    out = []
    for a in inventory:
        if a.id == req.asset_id:
            a = a.model_copy(deep=True)
            a.attrs[req.field] = Attr(value=req.value, source="provided_by_user", note="corrected by user",
                                      evidence_obs_ids=[])
            if all(v.value is not None for v in a.attrs.values()):
                a.next_step = ""
        out.append(a)
    return out, [req.asset_id]


def fixture_files_present(sid: str) -> bool:
    return sid == config.FIXTURE_SID or (config.FIXTURES_DIR / "live" / sid / "geometry.json").exists()


def example_path(name: str) -> Path:
    return config.EXAMPLES_DIR / name
