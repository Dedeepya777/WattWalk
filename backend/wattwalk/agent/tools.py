"""The seven agent tools (plan 12.4). Owner: Person 3.

Thin wrappers over the canonical functions: check the cancel flag, call the owner's module through
agent.providers, write results through the store, emit events, and return a short summary
(at most 600 characters). Used directly by the scripted agent and wrapped as LangChain tools by deep.py.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from pydantic import TypeAdapter

from .. import config, health_registry, store
from ..contracts import Asset, Building, CorrectionRequest, ModelGeometry, PlanRequest, PlanResponse
from . import providers as P
from .ask import make_ask_fn
from .context import RunContext

MAX_SUMMARY = 600
MAX_RESOLVE_ACTIONS = 5

TOOL_AGENT = {
    "load_building": "exterior_analyst",
    "list_rooms": "walker",
    "inspect_next_view": "walker",
    "resolve_next": "walker",
    "build_inventory_tool": "walker",
    "plan_upgrades": "retrofit_planner",
    "verify_audit_tool": "verifier",
}


def _short(text: str) -> str:
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 3] + "..."


def _state(sid: str) -> dict:
    return store.read(sid, "agent_state.json", default=None) or {
        "next_view": 0, "reviewed": {}, "faces_rejected": 0, "partial_rooms": {},
        "resolved": [], "resolve_actions": {},
    }


def _save_state(sid: str, st: dict) -> None:
    store.write(sid, "agent_state.json", st)


def geometry(sid: str) -> ModelGeometry:
    g = store.read(sid, "geometry.json", ModelGeometry)
    if g is None:
        raise RuntimeError("geometry.json missing; load_building must run first")
    return g


def building(sid: str) -> Building:
    b = store.read(sid, "building.json", Building)
    if b is None:
        raise RuntimeError("building.json missing; load_building must run first")
    return b


def _room_label(g: ModelGeometry, room_id: Optional[str]) -> str:
    return next((r.label for r in g.rooms if r.id == room_id), room_id or "No room")


def _labels(obs) -> str:
    c = Counter(o.label for o in obs)
    return ", ".join(f"{n} {lab.replace('_', ' ')}s" if n > 1 else lab.replace("_", " ") for lab, n in c.items())


def _money(x: float) -> str:
    return f"${x:,.0f}"


_LAYER_TO_INTEGRATION = {"matterport": "matterport", "costar": "costar_kit", "vexcel": "vexcel", "ebewe": "ebewe"}


def _record_layers(b: Building) -> None:
    """Feed the outcome of a live run's real provider calls into the health registry."""
    if config.effective_data_mode() == "fixture":
        return
    for layer, st in b.layer_status.model_dump().items():
        if st in ("live", "unavailable") and layer in _LAYER_TO_INTEGRATION:
            health_registry.record(_LAYER_TO_INTEGRATION[layer], st == "live", f"live audit: layer {st}")


# ----------------------------------------------------------------------------- tools
def load_building(ctx: RunContext) -> str:
    sid, agent = ctx.sid, TOOL_AGENT["load_building"]
    ctx.check_cancel()
    ctx.emit(agent, "tool_call", f"load_building({sid})", {"tool": "load_building"})
    g = P.get_geometry(sid)
    store.write(sid, "geometry.json", g)
    store.write(sid, "rooms.json", g.rooms)
    store.write(sid, "panos.json", g.panos)
    ctx.check_cancel()
    b = P.get_building(sid, g)
    store.write(sid, "building.json", b)
    _record_layers(b)
    parts = []
    if b.year_built.value is not None:
        parts.append(f"Built {b.year_built.value}")
    if b.units.value is not None:
        parts.append(f"{b.units.value} units")
    parts.append(b.city)
    text = ", ".join(parts)
    if b.ebewe:
        text += f"; EBEWE site EUI {b.ebewe.site_eui_kbtu_ft2} kBtu/ft2 ({b.ebewe.program_year})"
    missing = [k for k, v in b.layer_status.model_dump().items() if v == "unavailable"]
    if missing:
        text += "; unavailable layers: " + ", ".join(missing)
        ctx.emit(agent, "error", f"Building layers unavailable: {', '.join(missing)}", {"code": "upstream_unavailable"})
    text += f"; geometry {len(g.rooms)} rooms, {len(g.panos)} panoramas ({g.status})"
    ctx.emit(agent, "tool_result", text, {"tool": "load_building", "layer_status": b.layer_status.model_dump()})
    return _short(text)


def list_rooms(ctx: RunContext) -> str:
    sid, agent = ctx.sid, TOOL_AGENT["list_rooms"]
    ctx.check_cancel()
    ctx.emit(agent, "tool_call", f"list_rooms({sid})", {"tool": "list_rooms"})
    g = geometry(sid)
    tasks = P.plan_views(g)
    store.write(sid, "view_tasks.json", tasks)
    st = _state(sid)
    st["next_view"] = 0
    _save_state(sid, st)
    lines = ["# Walk plan", ""] + [f"- [ ] {_room_label(g, t.room_id)} ({t.pano_id}, {t.reason})" for t in tasks]
    store.write(sid, "agent/plan.md", "\n".join(lines) + "\n")
    text = f"{len(g.rooms)} rooms, {len(g.panos)} panoramas, {len(tasks)} planned views"
    ctx.emit(agent, "todo", "Plan: " + ", ".join(f"{_room_label(g, t.room_id)} {t.pano_id}" for t in tasks),
             {"todo": [f"{_room_label(g, t.room_id)} ({t.pano_id})" for t in tasks]})
    ctx.emit(agent, "tool_result", text, {"tool": "list_rooms", "views": len(tasks)})
    return text


def _tasks(sid: str):
    return TypeAdapter(list[P.ViewTask]).validate_python(store.read(sid, "view_tasks.json", default=[]))


def inspect_next_view(ctx: RunContext) -> str:
    sid, agent = ctx.sid, TOOL_AGENT["inspect_next_view"]
    ctx.check_cancel()
    tasks = _tasks(sid)
    st = _state(sid)
    i = st["next_view"]
    if i >= len(tasks):
        return "No pending views"
    t = tasks[i]
    g = geometry(sid)
    label = _room_label(g, t.room_id)
    ctx.emit(agent, "tool_call", f"inspect_next_view({t.room_id}, {t.pano_id})",
             {"tool": "inspect_next_view", "room_id": t.room_id, "pano_id": t.pano_id})
    r = P.inspect_view(sid, g, t.room_id, t.pano_id)
    ctx.check_cancel()  # discard a late result after cancellation (plan 4.8)
    store.append_observations(sid, r.observations)
    st = _state(sid)
    st["next_view"] = i + 1
    key = t.room_id or "_none"
    st["reviewed"].setdefault(key, [])
    if t.pano_id not in st["reviewed"][key]:
        st["reviewed"][key].append(t.pano_id)
    st["faces_rejected"] += len(r.faces_rejected)
    if r.faces_rejected and t.room_id:
        st["partial_rooms"][t.room_id] = f"{len(r.faces_rejected)} of 4 faces rejected by the quality check at {t.pano_id}"
    _save_state(sid, st)
    _tick_plan(sid, i)
    pending = len(tasks) - (i + 1)
    found = _labels(r.observations) if r.observations else "no energy-relevant assets"
    text = f"{label} {t.pano_id}: {found}; {len(r.faces_rejected)} faces rejected; {pending} pending views"
    if r.observations:
        ctx.emit(agent, "finding", f"{label}: {found}",
                 {"observation_ids": [o.id for o in r.observations], "room_id": t.room_id, "pano_id": t.pano_id})
    ctx.emit(agent, "tool_result", text, {"tool": "inspect_next_view", "observations": len(r.observations),
                                          "faces_rejected": len(r.faces_rejected), "pending": pending})
    return _short(text)


def _tick_plan(sid: str, index: int) -> None:
    text = store.read_text(sid, "agent/plan.md")
    if not text:
        return
    lines, n = text.splitlines(), -1
    for j, line in enumerate(lines):
        if line.startswith("- ["):
            n += 1
            if n == index:
                lines[j] = line.replace("- [ ]", "- [x]", 1)
    store.write(sid, "agent/plan.md", "\n".join(lines) + "\n")


def resolve_next(ctx: RunContext) -> str:
    sid, agent = ctx.sid, TOOL_AGENT["resolve_next"]
    ctx.check_cancel()
    st = _state(sid)
    done = set(st["resolved"])
    pending = sorted(o.id for o in store.observations(sid) if o.id not in done)
    if not pending:
        return "All observations resolved"
    oid = pending[0]
    ctx.emit(agent, "tool_call", f"resolve_next({oid})", {"tool": "resolve_next", "observation_id": oid})
    rr = P.resolve(sid, geometry(sid), oid, make_ask_fn(ctx, agent))
    ctx.check_cancel()
    store.apply_resolve(sid, rr)
    st = _state(sid)
    n = st["resolve_actions"].get(oid, 0) + 1
    st["resolve_actions"][oid] = n
    forced = not rr.final and n >= MAX_RESOLVE_ACTIONS
    if rr.final or forced:
        st["resolved"].append(oid)
    _save_state(sid, st)
    remaining = len([o for o in store.observations(sid) if o.id not in set(st["resolved"])])
    summary = rr.summary + (" (stopped after 5 actions)" if forced else "")
    ctx.emit(agent, "tool_result", summary, {"tool": "resolve_next", "action": rr.action, "observation_id": oid,
                                             "final": rr.final or forced, "unresolved": remaining})
    return _short(f"{summary}; {remaining} unresolved")


def rebuild_inventory(sid: str) -> list[Asset]:
    """build_inventory from observations, then re-apply stored corrections in order (plan 7.12.10)."""
    obs = store.observations(sid)
    inv = P.build_inventory(obs)
    for c in store.read(sid, "corrections.json", list[CorrectionRequest], default=[]):
        inv, _ = P.apply_correction(inv, obs, c)
    return inv


def coverage_for(sid: str, inv: list[Asset]):
    st = _state(sid)
    reviewed = {k: v for k, v in st["reviewed"].items() if k != "_none"}
    rejected = st["faces_rejected"]
    partial = st["partial_rooms"]
    # Prefer Person 2's coverage inputs when the real vision module is present:
    # it carries the rejection reason and the "no other panorama" wording from
    # router_state.json, which is the coverage contract.
    try:
        from ..vision.walk import coverage_inputs as real_coverage_inputs

        reviewed, rejected, partial = real_coverage_inputs(sid, geometry(sid))
    except Exception:
        pass
    return P.compute_coverage(geometry(sid), store.observations(sid), inv, reviewed,
                              rejected, partial)


def build_inventory_tool(ctx: RunContext) -> str:
    sid, agent = ctx.sid, TOOL_AGENT["build_inventory_tool"]
    ctx.check_cancel()
    ctx.emit(agent, "tool_call", f"build_inventory_tool({sid})", {"tool": "build_inventory_tool"})
    obs = store.observations(sid)
    inv = rebuild_inventory(sid)
    cov = coverage_for(sid, inv)
    shares = P.heat_shares(geometry(sid).rooms, inv, building(sid))
    store.write(sid, "inventory.json", inv)
    store.write(sid, "coverage.json", cov)
    store.write(sid, "heat_shares.json", shares)
    partial = [r.room_label.lower() for r in cov.rooms if r.status == "partial"]
    text = f"{len(obs)} observations -> {len(inv)} assets; {cov.attrs_unknown} unknown attributes"
    if partial:
        text += "; partial: " + ", ".join(partial)
    ctx.emit(agent, "tool_result", text, {"tool": "build_inventory_tool", "assets_unique": len(inv),
                                          "attrs_unknown": cov.attrs_unknown})
    return _short(text)


def plan_summary(p: PlanResponse) -> str:
    t = p.totals
    ex = "; ".join(f"{e.upgrade_id} {e.reason_code}" for e in p.excluded) or "none"
    return (f"{len(p.upgrades)} upgrades ({', '.join(u.upgrade_id for u in p.upgrades) or 'none'}), "
            f"{_money(t.cost_low_usd)} to {_money(t.cost_high_usd)}, {t.kwh_saved_yr:.1f} kWh/yr, "
            f"${t.bill_saved_usd_yr:,.2f}/yr; excluded: {ex}")


def plan_upgrades(ctx: RunContext, budget_usd: float = 5000, objective: str = "max_bill", role: str = "owner") -> str:
    sid, agent = ctx.sid, TOOL_AGENT["plan_upgrades"]
    ctx.check_cancel()
    ctx.emit(agent, "tool_call", f"plan_upgrades(budget {budget_usd:g}, {objective}, {role})", {"tool": "plan_upgrades"})
    inv = store.read(sid, "inventory.json", list[Asset])
    if inv is None:
        raise RuntimeError("inventory.json missing; build_inventory_tool must run first")
    req = PlanRequest(budget_usd=budget_usd, objective=objective, role=role)
    p = P.plan(sid, inv, building(sid), req)
    store.write(sid, "plan_default.json", p)
    text = plan_summary(p)
    ctx.emit(agent, "tool_result", text[:200], {"tool": "plan_upgrades", "upgrades": len(p.upgrades)})
    return _short(text)


def verify_audit_tool(ctx: RunContext) -> str:
    from .verify import verify_audit

    sid, agent = ctx.sid, TOOL_AGENT["verify_audit_tool"]
    ctx.check_cancel()
    ctx.emit(agent, "tool_call", f"verify_audit_tool({sid})", {"tool": "verify_audit_tool"})
    problems = verify_audit(sid)
    store.write(sid, "verify.json", {"problems": problems})
    text = "0 problems" if not problems else f"{len(problems)} problems: " + "; ".join(problems)
    ctx.emit(agent, "tool_result", text[:200], {"tool": "verify_audit_tool", "problems": len(problems)})
    return _short(text)


def template_report(sid: str) -> str:
    """Report written from files only (no model). Used by the scripted agent and as the Deep Agents fallback."""
    b = store.read(sid, "building.json", Building)
    inv = store.read(sid, "inventory.json", list[Asset], default=[])
    cov = store.read(sid, "coverage.json")
    p = store.read(sid, "plan_default.json", PlanResponse)
    problems = (store.read(sid, "verify.json", default={}) or {}).get("problems", [])
    out = [f"# WattWalk audit: {b.address if b else sid}", ""]
    out += ["## Summary", ""]
    if cov:
        out.append(f"{cov['assets_unique']} unique assets from {cov['observations_total']} observations; "
                   f"{cov['panos_reviewed']} of {cov['panos_total']} panoramas and {cov['rooms_reviewed']} of "
                   f"{cov['rooms_total']} rooms reviewed (source: visible in scan).")
    if b:
        facts = [f"year built {b.year_built.value} ({b.year_built.source.replace('_', ' ')})"] if b.year_built.value else []
        if b.ebewe:
            facts.append(f"LA EBEWE site EUI {b.ebewe.site_eui_kbtu_ft2} kBtu/ft2 in {b.ebewe.program_year} (reported in data)")
        if facts:
            out.append("Building: " + "; ".join(facts) + ".")
    out += ["", "## Findings with evidence", ""]
    for a in inv:
        known = ", ".join(f"{k} {v.value} ({v.source.replace('_', ' ')})" for k, v in a.attrs.items() if v.value is not None)
        out.append(f"- {a.id}: {a.label.replace('_', ' ')} in {a.room_id or 'building'}; observations "
                   f"{', '.join(a.observation_ids)}" + (f"; {known}" if known else ""))
    out += ["", "## Unknowns and next steps", ""]
    unk = [(a, k) for a in inv for k, v in a.attrs.items() if v.value is None]
    out += [f"- {a.id} {k} (needs verification): {a.next_step or 'no next step recorded'}" for a, k in unk] or ["- none"]
    out += ["", "## Recommended package", ""]
    if p:
        r = p.request
        out.append(f"Request: {r.role}, budget ${r.budget_usd:,.0f}, objective {r.objective}.")
        for u in p.upgrades:
            out.append(f"- {u.name}: ${u.cost_low_usd:,.0f} to ${u.cost_high_usd:,.0f}, {u.kwh_saved_yr:.1f} kWh/yr, "
                       f"${u.bill_saved_usd_yr:,.2f}/yr ({u.evidence_level.replace('_', ' ')})")
        t = p.totals
        out.append(f"Total: ${t.cost_low_usd:,.0f} to ${t.cost_high_usd:,.0f}; {t.kwh_saved_yr:.1f} kWh/yr; "
                   f"${t.bill_saved_usd_yr:,.2f}/yr.")
        out += [f"- Excluded {e.upgrade_id}: {e.reason}" for e in p.excluded]
    out += ["", "## Assumptions", ""]
    if p:
        out += [f"- {a.key} = {a.value:g} {a.unit} ({a.status.replace('_', ' ')})" for a in p.assumptions_used]
        out += [f"- Note: {n}" for n in p.notes]
    out += ["", "## Coverage", ""]
    if cov:
        for r in cov["rooms"]:
            out.append(f"- {r['room_label']}: {r['status']}" + (f" ({'; '.join(r['notes'])})" if r["notes"] else ""))
        if cov["not_visible"]:
            out.append("- Not visible anywhere: " + ", ".join(cov["not_visible"]))
    out += ["", f"Verifier: {'0 problems' if not problems else '; '.join(problems)}", ""]
    return "\n".join(out)
