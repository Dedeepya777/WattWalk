"""Deep Agents planner (plan 12.2 to 12.4). Owner: Person 3.

Built with deepagents.create_deep_agent (deepagents 0.7.x argument names: system_prompt, subagents,
backend, permissions; subagents take tool objects). The planner model is ChatBedrockConverse with
temperature 0, or an OpenRouter model for "openrouter/" ids. Every planner-tier model call is logged as
a ModelCall (tier planner, agent = the calling subagent). Check a model with: python -m wattwalk.agent.deep ping

Agent files: a FilesystemBackend rooted at audits/{sid}/ in virtual mode. The planner may read the
audit files and may write only under /agent/ (todo, notes, report draft). /agent/report.md becomes
the audit's report.md. If the planner skips a required step, the run loop says so in an event and
runs that step itself, so the audit never silently lacks a verifier result.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from .. import config, store
from ..contracts import ModelCall
from . import tools
from .context import RunContext
from .prompts import EXPLAIN_REWORD_PROMPT, PLANNER_PROMPT
from .subagents import build_subagents

log = logging.getLogger("wattwalk.deep")

# Tests (or a demo without Bedrock) may replace this with a factory returning another chat model.
MODEL_FACTORY: Optional[Callable[[], Any]] = None

RECURSION_LIMIT = 400


# The planner model id picks the provider by prefix, like the vision model ids:
#   deepseek/<model>   DeepSeek API (DEEPSEEK_API_KEY in .env, e.g. deepseek/deepseek-flash)
#   gemini/<model>     Google Gemini API (GOOGLE_API_KEY in .env)
#   openrouter/<model> OpenRouter's OpenAI-compatible API (OPENROUTER_API_KEY in .env)
#   anything else      Amazon Bedrock model id (the plan's default)
DEEPSEEK_PREFIX = "deepseek/"
GEMINI_PREFIX = "gemini/"
OPENROUTER_PREFIX = "openrouter/"


def _normalize_deepseek_model(name: str) -> str:
    cleaned = name.removeprefix(DEEPSEEK_PREFIX).strip()
    if cleaned.lower() in ("deepseek-v4.1-flash-1017", "deepseek-v4.1-flash", "deepseek-flash-1017"):
        return "deepseek-flash"
    return cleaned


def make_model(model_id: str | None = None):
    """Planner chat model for the configured (or supplied) model id.

    Bedrock ids use ChatBedrockConverse; deepseek/, gemini/ and openrouter/ ids use their provider.
    """
    if MODEL_FACTORY is not None:
        return MODEL_FACTORY()
    model_id = model_id if model_id is not None else config.PLANNER_MODEL_ID
    if not model_id:
        raise RuntimeError("WATTWALK_PLANNER_MODEL_ID is not set; use WATTWALK_AGENT_MODE=scripted")
    if model_id.startswith(DEEPSEEK_PREFIX) or model_id.lower().startswith("deepseek-"):
        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError("WATTWALK_PLANNER_MODEL_ID is a deepseek/ id but DEEPSEEK_API_KEY is not set")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise RuntimeError("deepseek/ planner ids need the langchain-openai package: pip install langchain-openai") from e

        target = _normalize_deepseek_model(model_id)
        base_url = config.DEEPSEEK_BASE_URL
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return ChatOpenAI(
            model=target,
            base_url=base_url,
            api_key=config.DEEPSEEK_API_KEY,
            temperature=0,
            max_retries=3,
            timeout=120,
        )
    if model_id.startswith(GEMINI_PREFIX):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_id.removeprefix(GEMINI_PREFIX), temperature=0)
    if model_id.startswith(OPENROUTER_PREFIX):
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError("WATTWALK_PLANNER_MODEL_ID is an openrouter/ id but OPENROUTER_API_KEY is not set")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise RuntimeError("openrouter/ planner ids need the langchain-openai package: pip install langchain-openai") from e

        return ChatOpenAI(model=model_id.removeprefix(OPENROUTER_PREFIX), base_url=config.OPENROUTER_BASE_URL,
                          api_key=config.OPENROUTER_API_KEY, temperature=0, max_retries=3, timeout=120,
                          default_headers={"X-Title": "WattWalk"})
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=model_id, region_name=config.AWS_REGION, temperature=0)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SUBAGENT_NAMES = {"exterior_analyst", "walker", "retrofit_planner", "verifier"}


class PlannerCallLogger(BaseCallbackHandler):
    """Appends one ModelCall (tier planner) per chat model call, with token usage when reported.

    The ModelCall agent is the subagent that made the call (LangChain sets metadata lc_agent_name to the
    subagent's name inside a task delegation), otherwise "planner".
    """

    def __init__(self, sid: str, kind: str = "planner"):
        self.sid, self.kind = sid, kind
        self._t0: dict[Any, float] = {}
        self._agent: dict[Any, str] = {}

    def _start(self, run_id, metadata) -> None:
        self._t0[run_id] = time.monotonic()
        name = (metadata or {}).get("lc_agent_name")
        self._agent[run_id] = name if name in SUBAGENT_NAMES else "planner"

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        self._start(run_id, metadata)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):
        self._start(run_id, metadata)

    def on_llm_end(self, response, *, run_id, **kwargs):
        t0 = self._t0.pop(run_id, time.monotonic())
        agent = self._agent.pop(run_id, "planner")
        tin = tout = None
        try:
            msg = response.generations[0][0].message
            usage = getattr(msg, "usage_metadata", None) or {}
            tin, tout = usage.get("input_tokens"), usage.get("output_tokens")
        except (AttributeError, IndexError):
            pass
        store.append_model_calls(self.sid, [ModelCall(
            id=f"mc_planner_{uuid.uuid4().hex[:10]}", agent=agent, kind=self.kind,
            model_id=config.PLANNER_MODEL_ID or "planner-model", model_tier="planner",
            tokens_in=tin, tokens_out=tout, latency_ms=int((time.monotonic() - t0) * 1000), cache_hit=False, at=_now())])


def make_lc_tools(ctx: RunContext) -> dict[str, StructuredTool]:
    def load_building() -> str:
        """Load geometry and building context (CoStar, LA EBEWE, Vexcel, Matterport) for this audit."""
        return tools.load_building(ctx)

    def list_rooms() -> str:
        """Plan which panoramas to inspect, room by room. Call once."""
        return tools.list_rooms(ctx)

    def inspect_next_view() -> str:
        """Inspect the next planned panorama. Call repeatedly until it returns 'No pending views'."""
        return tools.inspect_next_view(ctx)

    def resolve_next() -> str:
        """Resolve the next uncertain observation with the cheapest next step. Call until 'All observations resolved'."""
        return tools.resolve_next(ctx)

    def build_inventory_tool() -> str:
        """Deduplicate observations into the asset inventory and compute coverage. Call once after resolving."""
        return tools.build_inventory_tool(ctx)

    def plan_upgrades(budget_usd: float = 5000, objective: str = "max_bill", role: str = "owner") -> str:
        """Choose the upgrade package with the deterministic optimizer. objective: max_bill, max_kwh, best_value or conservative; role: owner or tenant."""
        return tools.plan_upgrades(ctx, budget_usd, objective, role)

    def verify_audit_tool() -> str:
        """Check evidence links, duplicates, assumptions and totals. Returns '0 problems' or the list."""
        return tools.verify_audit_tool(ctx)

    fns = [load_building, list_rooms, inspect_next_view, resolve_next, build_inventory_tool, plan_upgrades, verify_audit_tool]
    return {f.__name__: StructuredTool.from_function(f) for f in fns}


def build_agent(ctx: RunContext, model=None):
    from deepagents import FilesystemPermission, create_deep_agent
    from deepagents.backends import FilesystemBackend

    lc_tools = make_lc_tools(ctx)
    root = store.audit_dir(ctx.sid)
    (root / "agent").mkdir(parents=True, exist_ok=True)
    return create_deep_agent(
        model=model or make_model(),
        tools=[],
        system_prompt=PLANNER_PROMPT.format(sid=ctx.sid).replace("Write the final report to /report.md",
                                                                   "Write the final report to /agent/report.md and keep notes under /agent/"),
        subagents=build_subagents(ctx.sid, lc_tools),
        backend=FilesystemBackend(root_dir=root, virtual_mode=True),
        permissions=[
            FilesystemPermission(operations=["write"], paths=["/agent/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ],
        name="planner",
    )


def _emit_planner_activity(ctx: RunContext, msg: AIMessage) -> None:
    for call in getattr(msg, "tool_calls", None) or []:
        name, args = call.get("name"), call.get("args") or {}
        if name == "write_todos":
            todos = [t.get("content", str(t)) if isinstance(t, dict) else str(t) for t in args.get("todos", [])]
            ctx.emit("planner", "todo", "Plan: " + ", ".join(todos), {"todo": todos})
            store.write(ctx.sid, "agent/todo.md", "\n".join(
                f"- [{'x' if isinstance(t, dict) and t.get('status') == 'completed' else ' '}] "
                f"{t.get('content', t) if isinstance(t, dict) else t}" for t in args.get("todos", [])) + "\n")
        elif name == "task":
            sub = args.get("subagent_type") or args.get("name") or "subagent"
            ctx.emit("planner", "tool_call", f"delegate to {sub}: {str(args.get('description', ''))[:150]}",
                     {"tool": "task", "subagent": sub})
        elif name in ("write_file", "edit_file"):
            ctx.emit("planner", "tool_call", f"{name}({args.get('file_path', '')})", {"tool": name, "path": args.get("file_path")})


def run(ctx: RunContext, model=None) -> None:
    sid = ctx.sid
    agent = build_agent(ctx, model)
    cfg = {"callbacks": [PlannerCallLogger(sid)], "recursion_limit": RECURSION_LIMIT}
    inputs = {"messages": [{"role": "user", "content": f"Audit the apartment scan sid {sid} and write /agent/report.md."}]}
    for chunk in agent.stream(inputs, config=cfg, stream_mode="updates", subgraphs=True):
        ctx.check_cancel()
        ns, update = chunk if isinstance(chunk, tuple) and len(chunk) == 2 else ((), chunk)
        if ns:  # subagent internals: their tools already emit events with the subagent name
            continue
        for node_update in (update or {}).values():
            if not isinstance(node_update, dict):
                continue
            for m in node_update.get("messages", []) or []:
                if isinstance(m, AIMessage):
                    _emit_planner_activity(ctx, m)
    ctx.check_cancel()
    _finish(ctx)


def _complete_walk(ctx: RunContext) -> None:
    """Run whatever part of the walk the planner skipped, in the scripted order. Each step is skipped
    when its output already exists, so work the planner did is kept (list_rooms would restart the walk)."""
    sid = ctx.sid
    if store.read(sid, "building.json") is None:
        tools.load_building(ctx)
    if store.read(sid, "view_tasks.json") is None:
        tools.list_rooms(ctx)
    while "No pending views" not in tools.inspect_next_view(ctx):
        ctx.check_cancel()
    while "All observations resolved" not in tools.resolve_next(ctx):
        ctx.check_cancel()
    tools.build_inventory_tool(ctx)


DEFAULT_PLAN = {"budget_usd": 5000.0, "objective": "max_bill", "role": "owner"}


def _is_default_request(request: dict) -> bool:
    return all(request.get(k) == v for k, v in DEFAULT_PLAN.items())


def _views_left(sid: str) -> int:
    tasks = store.read(sid, "view_tasks.json") or []
    return max(0, len(tasks) - int(tools._state(sid).get("next_view", 0)))


def _unresolved(sid: str) -> list[str]:
    done = set(tools._state(sid)["resolved"])
    return [o.id for o in store.observations(sid) if o.id not in done]


def _finish(ctx: RunContext) -> None:
    """Guardrails: make missing steps visible, then finalise report.md from the planner's file."""
    sid = ctx.sid
    if store.read(sid, "inventory.json") is None:
        ctx.emit("planner", "error", "Planner finished without a complete walk; finishing it with the same tools",
                 {"code": "internal"})
        _complete_walk(ctx)
    corrected = False
    views_left = _views_left(sid)
    if views_left:
        ctx.emit("planner", "error", f"Walker stopped with {views_left} planned views not inspected; inspecting "
                 "them", {"code": "internal"})
        while "No pending views" not in tools.inspect_next_view(ctx):
            ctx.check_cancel()
        corrected = True
    pending = _unresolved(sid)
    if pending or corrected:
        if pending:
            ctx.emit("planner", "error", f"Walker stopped with {len(pending)} unresolved observations; resolving "
                     "them and rebuilding the inventory", {"code": "internal"})
        while "All observations resolved" not in tools.resolve_next(ctx):
            ctx.check_cancel()
        tools.build_inventory_tool(ctx)
        corrected = True
    plan = store.read(sid, "plan_default.json")
    if plan is None or corrected or not _is_default_request(plan.get("request", {})):
        ctx.emit("planner", "error", "Default plan missing, stale or made with non-default inputs; running "
                 "plan_upgrades with budget 5000, max_bill, owner", {"code": "internal"})
        tools.plan_upgrades(ctx)
        corrected = True
    if store.read(sid, "verify.json") is None or corrected:
        ctx.emit("planner", "error", "Verifier result missing or stale; running verify_audit_tool", {"code": "internal"})
        tools.verify_audit_tool(ctx)
    report = store.read_text(sid, "agent/report.md")
    if corrected and report and report.strip():
        # The planner's draft quotes numbers from before the corrections: keep it as a draft only.
        store.write(sid, "report.md", tools.template_report(sid))
        ctx.emit("planner", "status", "Report written from audit files (the planner's draft in agent/report.md "
                 "predates the corrections above)", {"report": "report.md"})
    elif report and report.strip():
        store.write(sid, "report.md", report)
        ctx.emit("planner", "status", "Report written by the planner from audit files", {"report": "report.md"})
    else:
        store.write(sid, "report.md", tools.template_report(sid))
        ctx.emit("planner", "status", "Planner wrote no report; template report written from files", {"report": "report.md"})


def reword(text: str) -> str:
    """Optional plain-language rewording for /explain (E.5). Caller enforces the 15 s timeout."""
    out = make_model().invoke(EXPLAIN_REWORD_PROMPT.format(template_text=text))
    content = out.content if isinstance(out.content, str) else " ".join(
        p.get("text", "") for p in out.content if isinstance(p, dict))
    return content.strip()


def ping(model=None) -> bool:
    """One planner-model call with a trivial tool bound. True if the model answered with a tool call."""
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    m = (model or make_model()).bind_tools([StructuredTool.from_function(add)])
    out = m.invoke("Use the add tool to compute 2 + 3. Reply only with the tool call.")
    calls = getattr(out, "tool_calls", None) or []
    return any(c.get("name") == "add" for c in calls)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m wattwalk.agent.deep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping", help="check the planner model answers with a tool call")
    args = ap.parse_args(argv)
    if args.cmd == "ping":
        print(f"planner model: {config.PLANNER_MODEL_ID or '(WATTWALK_PLANNER_MODEL_ID not set)'}")
        try:
            ok = ping()
        except Exception as e:  # noqa: BLE001 - report any provider error plainly
            print(f"FAILED: {type(e).__name__}: {e}")
            return 2
        print("OK: tool call returned" if ok else "FAILED: the model answered without a tool call; choose another model")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
