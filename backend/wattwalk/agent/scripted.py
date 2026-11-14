"""Scripted agent (plan 12.5, H.2): the same tools in a fixed order, no model calls. Owner: Person 3."""
from __future__ import annotations

from .. import store
from . import tools
from .context import RunContext

TODO = ["building context", "walk rooms", "plan upgrades", "verify", "write report"]


def run(ctx: RunContext) -> None:
    sid = ctx.sid
    ctx.emit("planner", "todo", "Plan: building context, walk rooms, plan upgrades, verify, report (scripted)",
             {"todo": TODO, "scripted": True})
    store.write(sid, "agent/todo.md", "\n".join(f"- [ ] {t}" for t in TODO) + "\n")
    tools.load_building(ctx)
    tools.list_rooms(ctx)
    while "No pending views" not in tools.inspect_next_view(ctx):
        ctx.check_cancel()
    while "All observations resolved" not in tools.resolve_next(ctx):
        ctx.check_cancel()
    tools.build_inventory_tool(ctx)
    tools.plan_upgrades(ctx, 5000, "max_bill", "owner")
    tools.verify_audit_tool(ctx)
    ctx.check_cancel()
    report = tools.template_report(sid)
    store.write(sid, "report.md", report)
    store.write(sid, "agent/report.md", report)
    store.write(sid, "agent/todo.md", "\n".join(f"- [x] {t}" for t in TODO) + "\n")
    ctx.emit("planner", "status", "Report written (template, scripted agent)", {"report": "report.md"})
