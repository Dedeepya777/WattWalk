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


def build_subagents(sid: str, lc_tools: dict) -> list[dict]:
    return [
        {"name": name, "description": desc, "system_prompt": prompt.format(sid=sid),
         "tools": [lc_tools[t] for t in tool_names]}
        for name, (desc, prompt, tool_names) in SUBAGENTS.items()
    ]
