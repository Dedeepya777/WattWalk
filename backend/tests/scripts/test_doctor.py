"""scripts/doctor.py turns common setup mistakes into clear problems with fix steps (no network needed)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import doctor  # noqa: E402


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor, "ollama_up", lambda: True)
    monkeypatch.setattr(doctor, "ollama_models", lambda: {"qwen2.5vl:7b", "qwen3:8b"})
    caps = {"qwen2.5vl:7b": {"completion", "vision"}, "qwen3:8b": {"completion", "tools"}}
    monkeypatch.setattr(doctor, "_ollama_capabilities", lambda m: caps.get(m))


def _titles(env):
    issues = []
    doctor.check_live_keys(env, issues)
    doctor.check_frontend_link(env, issues)
    doctor.check_sdk_key(env, issues)
    doctor.check_models(env, issues)
    return {(i.level, i.title) for i in issues}, issues


GOOD = {"WATTWALK_DATA_MODE": "live", "WATTWALK_VISION_MODE": "live", "WATTWALK_AGENT_MODE": "deep_agents",
        "MATTERPORT_API_KEY": "k", "MATTERPORT_API_TOKEN": "t", "MATTERPORT_SDK_KEY": "s",
        "VITE_MATTERPORT_SDK_KEY": "s", "VITE_API_BASE": "http://localhost:8000",
        "WATTWALK_SMALL_VISION_MODEL_ID": "ollama/qwen2.5vl:7b", "WATTWALK_LARGE_VISION_MODEL_ID": "ollama/qwen2.5vl:7b",
        "WATTWALK_PLANNER_MODEL_ID": "ollama/qwen3:8b"}


def test_good_local_setup_has_no_issues(offline):
    titles, _ = _titles(dict(GOOD))
    assert titles == set()


def test_common_mistakes_are_reported_with_fix_steps(offline):
    env = dict(GOOD, MATTERPORT_API_KEY="", VITE_API_BASE="", VITE_MATTERPORT_SDK_KEY="",
               WATTWALK_PLANNER_MODEL_ID="ollama/qwen2.5vl:7b", WATTWALK_LARGE_VISION_MODEL_ID="ollama/llava:13b")
    titles, issues = _titles(env)
    levels = {t: lvl for lvl, t in titles}
    assert levels["Live mode is on but MATTERPORT_API_KEY is empty"] == "problem"
    assert levels["The planner model qwen2.5vl:7b cannot use tools"] == "problem"
    assert levels["The Ollama model llava:13b is not downloaded"] == "problem"
    assert levels["VITE_API_BASE is not set in .env"] == "warning"
    assert levels["VITE_MATTERPORT_SDK_KEY is empty (MATTERPORT_SDK_KEY is set)"] == "warning"
    assert all(i.steps for i in issues)
    assert not any("k" == step or "s" == step for i in issues for step in i.steps)  # never echoes key values


def test_ollama_not_running_and_not_installed(offline, monkeypatch):
    env = {"WATTWALK_VISION_MODE": "live", "WATTWALK_SMALL_VISION_MODEL_ID": "ollama/qwen2.5vl:7b",
           "WATTWALK_LARGE_VISION_MODEL_ID": "ollama/qwen2.5vl:7b"}
    monkeypatch.setattr(doctor, "ollama_up", lambda: False)
    issues = []
    doctor.check_models(env, issues)
    assert [i.title for i in issues] == ["Ollama is installed but not running"]
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    issues = []
    doctor.check_models(env, issues)
    assert [i.title for i in issues] == ["Your .env uses Ollama models but Ollama is not installed"]
