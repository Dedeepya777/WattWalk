"""Rule-based stand-in for the Bedrock planner model, so Deep Agents wiring is testable offline.

It follows the planner and subagent prompts (plan E.3, E.4) literally: which agent it is playing is
read from the system prompt, and the next tool call from the previous tool result. It reports token
usage so the ModelCall logger is exercised. It is a test double, never used in the demo.
"""
from __future__ import annotations

import itertools
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ids = itertools.count()


def _call(name: str, args: dict | None = None) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": f"call_{next(_ids)}", "type": "tool_call"}],
                     usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})


def _say(text: str) -> AIMessage:
    return AIMessage(content=text, usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


REPORT = """# WattWalk audit (planner)

## Summary
Copied from tool results: {plan}

## Findings with evidence
See inventory.json (visible in scan).

## Unknowns and next steps
Bulb types need verification.

## Recommended package
{plan}

## Assumptions
All assumed for calculation (unverified defaults).

## Coverage
{walk}
"""


class RulePlanner(BaseChatModel):
    try_forbidden_write: bool = True

    @property
    def _llm_type(self) -> str:
        return "rule-planner"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _next(self, messages) -> AIMessage:
        system = " ".join(m.content for m in messages if isinstance(m, SystemMessage) and isinstance(m.content, str))
        calls = [tc["name"] for m in messages if isinstance(m, AIMessage) for tc in (m.tool_calls or [])]
        results = [m for m in messages if isinstance(m, ToolMessage)]
        last = str(results[-1].content) if results else ""

        if "Call load_building once" in system:
            return _call("load_building") if "load_building" not in calls else _say(f"Layers loaded. {last}")
        if "You walk one apartment scan" in system:
            if "list_rooms" not in calls:
                return _call("list_rooms")
            if "build_inventory_tool" in calls:
                return _say(last)
            if calls[-1] in ("list_rooms", "inspect_next_view") and "No pending views" not in last:
                return _call("inspect_next_view")
            if "All observations resolved" not in last:
                return _call("resolve_next")
            return _call("build_inventory_tool")
        if "Call plan_upgrades" in system:
            return _call("plan_upgrades", {"budget_usd": 5000, "objective": "max_bill", "role": "owner"}) \
                if "plan_upgrades" not in calls else _say(last)
        if "Call verify_audit_tool once" in system:
            return _call("verify_audit_tool") if "verify_audit_tool" not in calls else _say(last)

        # planner
        tasks = [m for m in messages if isinstance(m, AIMessage) for tc in (m.tool_calls or []) if tc["name"] == "task"]
        if "write_todos" not in calls:
            return _call("write_todos", {"todos": [{"content": t, "status": "pending"} for t in
                                                   ["building context", "walk rooms", "plan upgrades", "verify", "write report"]]})
        order = ["exterior_analyst", "walker", "retrofit_planner", "verifier"]
        if len(tasks) < len(order):
            sub = order[len(tasks)]
            return _call("task", {"description": f"Do your job for this audit ({sub})", "subagent_type": sub})
        if self.try_forbidden_write and calls.count("write_file") == 0:
            return _call("write_file", {"file_path": "/inventory.json", "content": "[]"})
        if calls.count("write_file") < (2 if self.try_forbidden_write else 1):
            walk = next((str(r.content) for r in results if "assets" in str(r.content)), "")
            plan = next((str(r.content) for r in results if "kWh/yr" in str(r.content)), "")
            return _call("write_file", {"file_path": "/agent/report.md", "content": REPORT.format(plan=plan, walk=walk)})
        return _say("Audit complete; report written to /agent/report.md.")
