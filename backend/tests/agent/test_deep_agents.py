"""Deep Agents planner tests (fix plan P3-1). Run: pytest backend/tests/agent/test_deep_agents.py

The offline tests always run. test_deep_agents_live_fixture runs only with a configured planner model
and credentials, and otherwise skips with the reason.
"""
from __future__ import annotations

import os
import sys
import types

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from wattwalk import config, store

from ..api.conftest import SID, env  # noqa: F401  (pytest fixtures)


class _ToolCaller(BaseChatModel):
    """Answers every prompt with one call to the first bound tool (or plain text if told not to)."""

    call_tools: bool = True
    tool_name: str = ""

    @property
    def _llm_type(self) -> str:
        return "tool-caller"

    def bind_tools(self, tools, **kwargs):
        name = getattr(tools[0], "name", "") if tools else ""
        return self.model_copy(update={"tool_name": name})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.call_tools and self.tool_name:
            msg = AIMessage(content="", tool_calls=[{"name": self.tool_name, "args": {"a": 2, "b": 3}, "id": "c1", "type": "tool_call"}])
        else:
            msg = AIMessage(content="5")
        return ChatResult(generations=[ChatGeneration(message=msg)])


# ----------------------------------------------------------------------------- offline
def test_ping_reports_tool_calling():
    from wattwalk.agent import deep

    assert deep.ping(_ToolCaller()) is True
    assert deep.ping(_ToolCaller(call_tools=False)) is False


def test_make_model_requires_planner_id(monkeypatch):
    from wattwalk.agent import deep

    monkeypatch.setattr(deep, "MODEL_FACTORY", None)
    monkeypatch.setattr(config, "PLANNER_MODEL_ID", "")
    with pytest.raises(RuntimeError, match="WATTWALK_PLANNER_MODEL_ID is not set"):
        deep.make_model()


def test_make_model_openrouter(monkeypatch):
    from wattwalk.agent import deep

    created = {}

    class FakeChatOpenAI:
        def __init__(self, **kw):
            created.update(kw)

    monkeypatch.setattr(deep, "MODEL_FACTORY", None)
    monkeypatch.setattr(config, "PLANNER_MODEL_ID", "openrouter/thinkingmachines/inkling-2-small:free")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        deep.make_model()
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    assert isinstance(deep.make_model(), FakeChatOpenAI)
    assert created["model"] == "thinkingmachines/inkling-2-small:free"
    assert created["base_url"] == config.OPENROUTER_BASE_URL and created["api_key"] == "test-key"
    assert created["temperature"] == 0


def test_planner_calls_logged_per_subagent(env):
    """The offline fake-model run logs planner-tier calls under the subagent that made them."""
    from wattwalk.agent import context, deep
    from wattwalk.agent.context import RunContext
    from wattwalk.agent.events import EventBus
    from wattwalk.agent.run import _prepare_fixture

    from .fake_planner import RulePlanner

    _prepare_fixture(SID)
    (config.AUDITS_DIR / SID / "model_calls.json").unlink()
    ctx = RunContext(sid=SID, mode="fixture", bus=EventBus(SID))
    token = config.RUN_MODE_OVERRIDE.set("fixture")
    try:
        deep.run(ctx, model=RulePlanner())
    finally:
        config.RUN_MODE_OVERRIDE.reset(token)
        context.release(SID)
    calls = store.read(SID, "model_calls.json")
    agents = {c["agent"] for c in calls}
    assert {"planner", "exterior_analyst", "walker", "retrofit_planner", "verifier"} <= agents
    assert all(c["kind"] == "planner" and c["model_tier"] == "planner" and c["image_px"] is None for c in calls)


# ----------------------------------------------------------------------------- live (needs credentials)
def _live_skip_reason() -> str | None:
    model_id = os.getenv("WATTWALK_PLANNER_MODEL_ID") or config.PLANNER_MODEL_ID
    if not model_id:
        return "WATTWALK_PLANNER_MODEL_ID is not set"
    if model_id.startswith("openrouter/"):
        if not config.OPENROUTER_API_KEY:
            return "openrouter/ planner id but OPENROUTER_API_KEY is not set"
        try:
            import langchain_openai  # noqa: F401
        except ImportError:
            return "openrouter/ planner id but langchain-openai is not installed"
        return None
    try:
        import boto3
        if boto3.Session().get_credentials() is None:
            return "no AWS credentials found (aws configure or AWS_* environment variables)"
    except Exception as e:  # noqa: BLE001
        return f"AWS credentials unavailable: {e}"
    return None


@pytest.mark.skipif(_live_skip_reason() is not None, reason=_live_skip_reason() or "")
def test_deep_agents_live_fixture(env):
    """A real planner model drives the agent over the fixture apartment (fixture data, real planner calls)."""
    from wattwalk.agent import context, deep
    from wattwalk.agent.context import RunContext
    from wattwalk.agent.events import EventBus
    from wattwalk.agent.run import _prepare_fixture

    _prepare_fixture(SID)
    (config.AUDITS_DIR / SID / "model_calls.json").unlink()
    ctx = RunContext(sid=SID, mode="fixture", bus=EventBus(SID))
    token = config.RUN_MODE_OVERRIDE.set("fixture")
    try:
        deep.run(ctx)
    finally:
        config.RUN_MODE_OVERRIDE.reset(token)
        context.release(SID)
    by_agent = {e.agent for e in ctx.bus.events if e.type in ("tool_call", "tool_result")}
    assert {"exterior_analyst", "walker", "retrofit_planner", "verifier"} <= by_agent
    assert (config.AUDITS_DIR / SID / "agent").is_dir()
    assert store.read(SID, "verify.json") is not None
    assert any(c["model_tier"] == "planner" for c in store.read(SID, "model_calls.json"))
