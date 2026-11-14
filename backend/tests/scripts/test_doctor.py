"""scripts/doctor.py turns common setup mistakes into clear problems with fix steps (no network needed)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import doctor  # noqa: E402


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(doctor, "_venv_has", lambda mod: True)


def _titles(env):
    issues = []
    doctor.check_live_keys(env, issues)
    doctor.check_frontend_link(env, issues)
    doctor.check_sdk_key(env, issues)
    doctor.check_models(env, issues)
    return {(i.level, i.title) for i in issues}, issues


GOOD = {
    "WATTWALK_DATA_MODE": "live",
    "WATTWALK_VISION_MODE": "live",
    "WATTWALK_AGENT_MODE": "deep_agents",
    "MATTERPORT_API_KEY": "k",
    "MATTERPORT_API_TOKEN": "t",
    "MATTERPORT_SDK_KEY": "s",
    "VITE_MATTERPORT_SDK_KEY": "s",
    "VITE_API_BASE": "http://localhost:8000",
    "DEEPSEEK_API_KEY": "sk-test",
    "WATTWALK_SMALL_VISION_MODEL_ID": "deepseek/deepseek-flash",
    "WATTWALK_LARGE_VISION_MODEL_ID": "deepseek/deepseek-flash",
    "WATTWALK_PLANNER_MODEL_ID": "deepseek/deepseek-flash",
}


def test_good_local_setup_has_no_issues(offline):
    titles, _ = _titles(dict(GOOD))
    assert titles == set()


def test_common_mistakes_are_reported_with_fix_steps(offline):
    env = dict(
        GOOD,
        MATTERPORT_API_KEY="",
        VITE_API_BASE="",
        VITE_MATTERPORT_SDK_KEY="",
        DEEPSEEK_API_KEY="",
    )
    titles, issues = _titles(env)
    levels = {t: lvl for lvl, t in titles}
    assert levels["Live mode is on but MATTERPORT_API_KEY is empty"] == "problem"
    assert levels["A deepseek/ model is set but DEEPSEEK_API_KEY is empty"] == "problem"
    assert levels["VITE_API_BASE is not set in .env"] == "warning"
    assert levels["VITE_MATTERPORT_SDK_KEY is empty (MATTERPORT_SDK_KEY is set)"] == "warning"
    assert all(i.steps for i in issues)
    assert not any("k" == step or "s" == step for i in issues for step in i.steps)  # never echoes key values


def test_deepseek_missing_langchain_openai(offline, monkeypatch):
    monkeypatch.setattr(doctor, "_venv_has", lambda mod: False)
    env = dict(GOOD)
    issues = []
    doctor.check_models(env, issues)
    assert any("langchain-openai package" in i.title for i in issues)
