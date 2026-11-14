"""Subagent definitions for the Deep Agents planner (plan 12.3, E.4). Owner: Person 3."""
from __future__ import annotations

from .prompts import EXTERIOR_ANALYST_PROMPT, RETROFIT_PLANNER_PROMPT, VERIFIER_PROMPT, WALKER_PROMPT

# name -> (description given to the planner, prompt template, tool names)
SUBAGENTS = {
    "exterior_analyst": (
        "Loads CoStar, EBEWE and Vexcel context for the building and reports mismatches (address, year) instead of hiding them.",
        EXTERIOR_ANALYST_PROMPT, ["load_building"]),
    "walker": (
        "Walks the scan room by room, inspects chosen panoramas, resolves uncertain findings with the cheapest next step, records coverage.",
        WALKER_PROMPT, ["list_rooms", "inspect_next_view", "resolve_next", "build_inventory_tool"]),
    "retrofit_planner": (
        "Chooses an upgrade package with the deterministic optimizer and explains trade-offs.",
        RETROFIT_PLANNER_PROMPT, ["plan_upgrades"]),
    "verifier": (
        "Checks evidence links, duplicates, assumptions and totals before the report is final.",
        VERIFIER_PROMPT, ["verify_audit_tool"]),
}


# Deep Agents adds a default "general-purpose" subagent unless one is supplied. The default has none of
# the audit tools, and small planner models tend to pick it, so the audit never ran. Ours replaces it:
# described as a fallback, but able to do the whole audit in the scripted order if it is chosen anyway.
GENERAL_PURPOSE_PROMPT = """You are the fallback audit worker for apartment scan sid {sid}. Use the tools, in this order:
1. load_building once. 2. list_rooms once. 3. inspect_next_view until it reports no pending views.
4. resolve_next until it reports all observations resolved. 5. build_inventory_tool once.
6. plan_upgrades once (budget 5000, objective max_bill, role owner). 7. verify_audit_tool once.
Report what each tool returned. Never invent numbers or describe images yourself."""


def build_subagents(sid: str, lc_tools: dict) -> list[dict]:
    specialists = [
        {"name": name, "description": desc, "system_prompt": prompt.format(sid=sid),
         "tools": [lc_tools[t] for t in tool_names]}
        for name, (desc, prompt, tool_names) in SUBAGENTS.items()
    ]
    fallback = {
        "name": "general-purpose",
        "description": "Fallback only. Prefer exterior_analyst, walker, retrofit_planner and verifier.",
        "system_prompt": GENERAL_PURPOSE_PROMPT.format(sid=sid),
        "tools": list(lc_tools.values()),
    }
    return specialists + [fallback]
