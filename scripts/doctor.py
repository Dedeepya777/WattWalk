"""WattWalk setup checker. Run from the repository root:

    python3 scripts/doctor.py

Looks at the things that most often stop the app from working (the .env settings, keys, Ollama and its
models, other model providers, the CoStar kit path, ports) and prints, for every problem, what is wrong,
why it matters and numbered steps to fix it. scripts/run.py runs the same checks before it starts.

PROBLEM  = the app (or live mode) will not work until it is fixed; run.py stops.
WARNING  = something optional or easy to work around; run.py starts anyway.
Never prints key or token values. Standard library only.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup import ENV_FILE, ROOT, read_env, venv_python  # noqa: E402

BACKEND_PORT, FRONTEND_PORT = 8000, 5173
DEFAULT_API_BASE = f"http://localhost:{BACKEND_PORT}"
MODES = {"WATTWALK_DATA_MODE": {"fixture", "live"}, "WATTWALK_VISION_MODE": {"fixture", "live"},
         "WATTWALK_AGENT_MODE": {"scripted", "deep_agents"}}


@dataclass
class Issue:
    level: str          # "problem" or "warning"
    title: str
    why: str
    steps: list[str] = field(default_factory=list)


def _set(env: dict[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _venv_has(module: str) -> bool:
    py = venv_python()
    return py.exists() and subprocess.run([str(py), "-c", f"import {module}"], capture_output=True).returncode == 0


# ------------------------------------------------------------------------------------------------ checks
def check_install(issues: list[Issue]) -> None:
    if not venv_python().exists():
        issues.append(Issue("problem", "The Python environment (.venv) is missing",
                            "The backend cannot start without its packages.",
                            ["Run:  python3 scripts/setup.py", "Then run WattWalk again."]))
    if not (ROOT / "frontend" / "node_modules").exists():
        issues.append(Issue("problem", "The frontend packages (frontend/node_modules) are missing",
                            "The web page cannot start without them.",
                            ["Run:  python3 scripts/setup.py   (or: cd frontend && npm install)"]))


def check_env_file(issues: list[Issue]) -> dict[str, str] | None:
    if not ENV_FILE.exists():
        issues.append(Issue("problem", "There is no .env file",
                            ".env holds the modes, model names and keys; without it only the sample apartment works.",
                            ["Run:  python3 scripts/setup.py   (it creates .env and asks for your keys)",
                             "Or copy the template:  cp .env.example .env   then fill in the keys (README section 3.2)."]))
        return None
    env = read_env(ENV_FILE)
    for key, allowed in MODES.items():
        value = env.get(key, "").strip()
        if value and value not in allowed:
            issues.append(Issue("problem", f"{key} has an unknown value",
                                f"The backend refuses to start with it. Allowed: {', '.join(sorted(allowed))}.",
                                [f"Open .env and set {key} to one of: {', '.join(sorted(allowed))}.",
                                 "Save, then start WattWalk again."]))
    return env


def check_live_keys(env: dict[str, str], issues: list[Issue]) -> None:
    if env.get("WATTWALK_DATA_MODE") != "live":
        return
    missing = [k for k in ("MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN") if not _set(env, k)]
    if missing:
        issues.append(Issue("problem", f"Live mode is on but {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} empty",
                            "Live audits read the apartment scans from the Matterport API with these keys.",
                            ["In the CoStar track Discord channel, run  /costar-keys",
                             "Open .env and paste the API key after MATTERPORT_API_KEY= and the token after "
                             "MATTERPORT_API_TOKEN= (no quotes, no spaces).",
                             "Save, then start WattWalk again.",
                             "Without keys you can still use the sample apartment: set WATTWALK_DATA_MODE=fixture "
                             "and WATTWALK_VISION_MODE=fixture."]))


def check_frontend_link(env: dict[str, str], issues: list[Issue]) -> None:
    value = env.get("VITE_API_BASE", "").strip()
    if value in ("", "fixture:") and "live" in (env.get("WATTWALK_DATA_MODE"), env.get("WATTWALK_VISION_MODE")):
        issues.append(Issue("warning", "VITE_API_BASE is not set in .env",
                            "Without it the web page only plays the built-in sample ('API: fixture' in the banner) and "
                            "never talks to the backend. scripts/run.py sets it for you each time it starts.",
                            [f"To make it permanent, add this line to .env:  VITE_API_BASE={DEFAULT_API_BASE}",
                             "If you start the frontend yourself (npm run dev), restart it after saving."]))


def check_sdk_key(env: dict[str, str], issues: list[Issue]) -> None:
    server, browser = _set(env, "MATTERPORT_SDK_KEY"), _set(env, "VITE_MATTERPORT_SDK_KEY")
    if not server and not browser:
        issues.append(Issue("warning", "No Matterport SDK key: the 3D tab shows the tour without pins",
                            "Pins inside the 3D tour need the Showcase SDK key. The 2D plan works without it.",
                            ["Get the SDK key (from /costar-keys or my.matterport.com > Settings > Developer Tools).",
                             "Add it twice to .env, same value:  MATTERPORT_SDK_KEY=...  and  VITE_MATTERPORT_SDK_KEY=...",
                             "On my.matterport.com add  localhost:5173  to the key's allowed domains."]))
    elif server and not browser:
        issues.append(Issue("warning", "VITE_MATTERPORT_SDK_KEY is empty (MATTERPORT_SDK_KEY is set)",
                            "The browser can only read names that start with VITE_, so 3D pins stay off.",
                            ["Open .env and give VITE_MATTERPORT_SDK_KEY the same value as MATTERPORT_SDK_KEY.",
                             "Restart the frontend (or scripts/run.py)."]))
    elif server and browser and env["MATTERPORT_SDK_KEY"].strip() != env["VITE_MATTERPORT_SDK_KEY"].strip():
        issues.append(Issue("warning", "MATTERPORT_SDK_KEY and VITE_MATTERPORT_SDK_KEY are different",
                            "They should be the same key; the 3D view uses the VITE_ one.",
                            ["Open .env and copy the correct SDK key into both lines."]))


def check_models(env: dict[str, str], issues: list[Issue], ollama_should_run: bool = True) -> None:
    vision_live = env.get("WATTWALK_VISION_MODE") == "live"
    deep = env.get("WATTWALK_AGENT_MODE") == "deep_agents"
    ids = {k: env.get(k, "").strip() for k in
           ("WATTWALK_SMALL_VISION_MODEL_ID", "WATTWALK_LARGE_VISION_MODEL_ID", "WATTWALK_PLANNER_MODEL_ID")}
    used = {k: v for k, v in ids.items()
            if v and (k == "WATTWALK_PLANNER_MODEL_ID" and deep or k != "WATTWALK_PLANNER_MODEL_ID" and vision_live)}

    if vision_live and not (ids["WATTWALK_SMALL_VISION_MODEL_ID"] and ids["WATTWALK_LARGE_VISION_MODEL_ID"]):
        issues.append(Issue("problem", "Vision is live but a vision model id is empty",
                            "Live audits need a model that looks at the photos.",
                            ["Put these in .env:",
                             "   WATTWALK_SMALL_VISION_MODEL_ID=deepseek/deepseek-flash",
                             "   WATTWALK_LARGE_VISION_MODEL_ID=deepseek/deepseek-flash",
                             "   DEEPSEEK_API_KEY=sk-..."]))
    if deep and not ids["WATTWALK_PLANNER_MODEL_ID"]:
        issues.append(Issue("problem", "WATTWALK_AGENT_MODE=deep_agents but WATTWALK_PLANNER_MODEL_ID is empty",
                            "Deep Agents mode needs a planner model; the audit fails at once without it.",
                            ["Add  WATTWALK_PLANNER_MODEL_ID=deepseek/deepseek-flash  to .env",
                             "or set  WATTWALK_AGENT_MODE=scripted  (same tools in a fixed order, no planner model)."]))

    if any(v.startswith("deepseek/") or v.lower().startswith("deepseek-") for v in used.values()):
        if not _set(env, "DEEPSEEK_API_KEY"):
            issues.append(Issue("problem", "A deepseek/ model is set but DEEPSEEK_API_KEY is empty",
                                "DeepSeek API calls need an API key from https://platform.deepseek.com",
                                ["Add  DEEPSEEK_API_KEY=sk-...  to .env and start WattWalk again."]))
        if not _venv_has("langchain_openai"):
            issues.append(Issue("problem", "deepseek/ planner ids need the langchain-openai package",
                                "The package is needed for OpenAI-compatible chat models.",
                                ["Run:  .venv\\Scripts\\python -m pip install langchain-openai"]))

    if any(v.startswith("gemini/") for v in used.values()):
        if not _set(env, "GOOGLE_API_KEY"):
            issues.append(Issue("problem", "A gemini/ model is set but GOOGLE_API_KEY is empty",
                                "Gemini calls need a Google AI Studio key.",
                                ["Create a key at https://aistudio.google.com/apikey",
                                 "Add  GOOGLE_API_KEY=...  to .env and start WattWalk again."]))
        issues.append(Issue("warning", "Gemini free tier: 20 requests per model per day",
                            "One audit needs 60 to 100 calls, so a free key runs out during the first audit "
                            "('Gemini daily quota used up').",
                            ["Enable billing on the key, or switch the model ids back to deepseek/... in .env."]))
    if any(v.startswith("openrouter/") for v in used.values()):
        if not _set(env, "OPENROUTER_API_KEY"):
            issues.append(Issue("problem", "An openrouter/ planner is set but OPENROUTER_API_KEY is empty",
                                "OpenRouter calls need a key.",
                                ["Create a key at https://openrouter.ai/keys", "Add  OPENROUTER_API_KEY=...  to .env."]))
        if not _venv_has("langchain_openai"):
            issues.append(Issue("problem", "openrouter/ planner ids need the langchain-openai package",
                                "It is optional and not installed.",
                                ["Run:  .venv/bin/python -m pip install langchain-openai   "
                                 "(Windows: .venv\\Scripts\\python -m pip install langchain-openai)"]))
    bedrock = [v for v in used.values() if not v.startswith(("deepseek/", "gemini/", "openrouter/")) and not v.lower().startswith("deepseek-")]
    if bedrock and not (os.environ.get("AWS_ACCESS_KEY_ID") or (Path.home() / ".aws" / "credentials").exists()
                        or os.environ.get("AWS_PROFILE")):
        issues.append(Issue("warning", "Bedrock model ids are set but no AWS credentials were found",
                            "Amazon Bedrock calls need AWS credentials and model access in your region.",
                            ["Run  aws configure  (or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in your shell).",
                             "Or use DeepSeek: deepseek/deepseek-flash."]))


def check_costar(env: dict[str, str], issues: list[Issue]) -> None:
    kit = env.get("COSTAR_KIT_ZIP", "").strip().strip('"')
    if not kit:
        if env.get("WATTWALK_DATA_MODE") == "live":
            issues.append(Issue("warning", "COSTAR_KIT_ZIP is empty",
                                "The building card shows fewer fields (year built, units, rent come from the kit).",
                                ["Download the CoStar kit from the CoStar keys card.",
                                 "Set  COSTAR_KIT_ZIP=/full/path/to/the/zip-or-unzipped-folder  in .env."]))
        return
    path = Path(kit).expanduser()
    if not path.exists():
        issues.append(Issue("warning", "COSTAR_KIT_ZIP points to a path that does not exist",
                            "The CoStar fields on the building card will be missing.",
                            ["Check the path in .env (full path, no quotes needed).",
                             "It can be the downloaded .zip or the unzipped folder."]))
    elif path.suffix.lower() == ".zip" and not _set(env, "COSTAR_ZIP_PASSWORD"):
        issues.append(Issue("warning", "COSTAR_KIT_ZIP is a zip but COSTAR_ZIP_PASSWORD is empty",
                            "The kit zip is password protected.",
                            ["Add the password from the CoStar keys card as COSTAR_ZIP_PASSWORD=... in .env,",
                             "or unzip it once and point COSTAR_KIT_ZIP at the folder."]))


def check_ports(issues: list[Issue]) -> None:
    for port, what in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "frontend")):
        if _port_in_use(port):
            issues.append(Issue("problem", f"Port {port} is already in use (the {what})",
                                "WattWalk (or another program) is already running there, so a second copy cannot start.",
                                ["If WattWalk is already running in another terminal, use that one, or press Ctrl+C there.",
                                 f"To see what holds the port:  lsof -i :{port}   (Windows: netstat -ano | findstr {port})",
                                 "Then start WattWalk again."]))


def run_checks(include_ports: bool = False, ollama_should_run: bool = True) -> list[Issue]:
    issues: list[Issue] = []
    check_install(issues)
    env = check_env_file(issues)
    if env is not None:
        check_live_keys(env, issues)
        check_frontend_link(env, issues)
        check_sdk_key(env, issues)
        check_models(env, issues, ollama_should_run)
        check_costar(env, issues)
    if include_ports:
        check_ports(issues)
    return issues


def report(issues: list[Issue]) -> int:
    """Print the issues; returns the number of problems."""
    problems = [i for i in issues if i.level == "problem"]
    warnings = [i for i in issues if i.level == "warning"]
    if not issues:
        print("WattWalk check: everything looks good.")
        return 0
    print(f"WattWalk check: {len(problems)} problem(s), {len(warnings)} warning(s)\n")
    for issue in problems + warnings:
        tag = "PROBLEM" if issue.level == "problem" else "WARNING"
        print(f"[{tag}] {issue.title}")
        print(f"   Why: {issue.why}")
        if issue.steps:
            print("   Fix:")
            for n, step in enumerate(issue.steps, 1):
                print(f"     {n}. {step}")
        print()
    return len(problems)


def main() -> None:
    problems = report(run_checks(include_ports=False))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
