"""One-time setup for WattWalk. Run from the repository root:

    python3 scripts/setup.py            # asks before big downloads and for your keys
    python3 scripts/setup.py --yes      # no questions: install everything, keep .env as is

What it does, in order (each step is skipped when already done):
 1. checks Python and Node versions
 2. creates .venv and installs backend/requirements.txt (uses uv when installed, otherwise pip)
 3. installs the frontend packages (npm install)
 4. creates .env from .env.example with working local defaults, and asks for your keys (hidden input);
    an existing .env is never overwritten, only reported on
 5. checks Ollama: offers to install it with Homebrew on macOS, starts it, downloads the two models
 6. runs the contract check and the test suite

What it cannot do for you: the keys come from /costar-keys in the CoStar Discord channel, the CoStar
kit is licensed (download it from the keys card), and the Showcase SDK key's allowed domains are set
on my.matterport.com. Standard library only, so it runs before anything is installed.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "qwen2.5vl:7b"   # about 6 GB, photo detection
PLANNER_MODEL = "qwen3:8b"      # about 5 GB, Deep Agents planner (needs tool calling)

LOCAL_DEFAULTS = {
    "WATTWALK_SMALL_VISION_MODEL_ID": f"ollama/{VISION_MODEL}",
    "WATTWALK_LARGE_VISION_MODEL_ID": f"ollama/{VISION_MODEL}",
    "WATTWALK_PLANNER_MODEL_ID": f"ollama/{PLANNER_MODEL}",
    "WATTWALK_AGENT_MODE": "deep_agents",
    "VITE_API_BASE": "http://localhost:8000",
}
# (variable, question). The SDK key is written under both names: the browser only sees VITE_*.
KEY_QUESTIONS = [
    ("MATTERPORT_API_KEY", "Matterport API key (from /costar-keys)"),
    ("MATTERPORT_API_TOKEN", "Matterport API token (from /costar-keys)"),
    ("MATTERPORT_SDK_KEY", "Matterport Showcase SDK key (for 3D pins)"),
]
NEEDED_FOR_LIVE = ["MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN"]


def say(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"    ok   {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"    !!   {msg}", flush=True)


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True) -> int:
    print("    $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check).returncode


def ask(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    return input(f"    ?    {question} [y/N] ").strip().lower() in ("y", "yes")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ---------------------------------------------------------------- 1. versions
def check_versions() -> None:
    say("Checking Python and Node")
    v = sys.version_info
    if (v.major, v.minor) < (3, 11):
        sys.exit(f"Python 3.11 or 3.12 is needed (this is {platform.python_version()}).")
    ok(f"Python {platform.python_version()} runs this script")
    node = shutil.which("node")
    if not node:
        sys.exit("Node.js 20 or newer is needed for the frontend: https://nodejs.org (then run this again).")
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    if int(out.lstrip("v").split(".")[0]) < 20:
        sys.exit(f"Node.js 20 or newer is needed (found {out}).")
    ok(f"Node {out}")


# ---------------------------------------------------------------- 2. backend
def setup_backend() -> None:
    say("Backend: Python environment and packages")
    uv = shutil.which("uv")
    py = venv_python()
    if not py.exists():
        if uv:
            run([uv, "venv", str(VENV), "--python", "3.12"])
        else:
            if sys.version_info[:2] > (3, 12):
                warn("Python newer than 3.12 may lack packages; install Python 3.12 or uv (https://docs.astral.sh/uv/)")
            run([sys.executable, "-m", "venv", str(VENV)])
    else:
        ok(".venv exists")
    req = str(ROOT / "backend" / "requirements.txt")
    if uv:
        run([uv, "pip", "install", "--python", str(py), "-q", "-r", req])
    else:
        run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
        run([str(py), "-m", "pip", "install", "-q", "-r", req])
    ok("backend packages installed")


# ---------------------------------------------------------------- 3. frontend
def setup_frontend() -> None:
    say("Frontend: npm packages")
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found (it comes with Node.js).")
    run([npm, "install", "--no-fund", "--no-audit"], cwd=ROOT / "frontend")
    ok("frontend packages installed")


# ---------------------------------------------------------------- 4. .env
def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def write_env(template: Path, target: Path, values: dict[str, str]) -> None:
    lines = []
    for line in template.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in values:
                line = f"{k}={values[k]}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o600)


def setup_env(assume_yes: bool) -> dict[str, str]:
    say("Settings (.env)")
    if ENV_FILE.exists():
        env = read_env(ENV_FILE)
        ok(".env exists; leaving it unchanged")
    else:
        env = dict(LOCAL_DEFAULTS)
        interactive = sys.stdin.isatty() and not assume_yes
        if interactive:
            print("    Paste each key and press Enter (input is hidden). Press Enter alone to skip.")
            for name, question in KEY_QUESTIONS:
                value = getpass.getpass(f"    {question}: ").strip()
                if value:
                    env[name] = value
            kit = input("    Full path to the CoStar kit zip or folder (Enter to skip): ").strip().strip('"')
            if kit:
                env["COSTAR_KIT_ZIP"] = kit
                if kit.lower().endswith(".zip"):
                    pw = getpass.getpass("    CoStar kit zip password (hidden, Enter to skip): ").strip()
                    if pw:
                        env["COSTAR_ZIP_PASSWORD"] = pw
        if env.get("MATTERPORT_SDK_KEY"):
            env["VITE_MATTERPORT_SDK_KEY"] = env["MATTERPORT_SDK_KEY"]
        live = all(env.get(k) for k in NEEDED_FOR_LIVE)
        env["WATTWALK_DATA_MODE"] = env["WATTWALK_VISION_MODE"] = "live" if live else "fixture"
        write_env(ENV_EXAMPLE, ENV_FILE, env)
        ok(f".env created ({'live' if live else 'fixture'} mode)")
    missing = [k for k in NEEDED_FOR_LIVE + ["MATTERPORT_SDK_KEY", "VITE_MATTERPORT_SDK_KEY", "COSTAR_KIT_ZIP"]
               if not env.get(k)]
    for k in missing:
        warn(f"{k} is empty in .env")
    if env.get("WATTWALK_DATA_MODE") != "live":
        warn("Data mode is fixture: only the sample apartment works until the Matterport keys are set and "
             "WATTWALK_DATA_MODE / WATTWALK_VISION_MODE are live")
    return env


# ---------------------------------------------------------------- 5. Ollama
def ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2).read()
        return True
    except OSError:
        return False


def ollama_models() -> set[str]:
    try:
        data = json.loads(urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5).read())
        return {m["name"] for m in data.get("models", [])}
    except OSError:
        return set()


def start_ollama(exe: str) -> bool:
    if ollama_up():
        return True
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, "serve"], **kwargs)
    for _ in range(30):
        time.sleep(1)
        if ollama_up():
            return True
    return False


def setup_ollama(env: dict[str, str], assume_yes: bool) -> None:
    uses = {v.removeprefix("ollama/") for k, v in env.items() if k.endswith("_MODEL_ID") and v.startswith("ollama/")}
    if not uses:
        say("Ollama: not used by .env model ids, skipping")
        return
    say(f"Ollama (local AI): models {', '.join(sorted(uses))}")
    exe = shutil.which("ollama")
    if not exe and platform.system() == "Darwin" and shutil.which("brew"):
        if ask("Ollama is not installed. Install it with Homebrew now?", assume_yes):
            run([shutil.which("brew"), "install", "ollama"])
            exe = shutil.which("ollama")
    if not exe:
        warn("Ollama is not installed: get it from https://ollama.com/download, then run this script again")
        return
    if not start_ollama(exe):
        warn("Ollama did not start; open the Ollama app or run 'ollama serve', then run this script again")
        return
    ok("Ollama is running")
    have = ollama_models()
    for model in sorted(uses):
        if model in have or f"{model}:latest" in have:
            ok(f"model {model} present")
        elif ask(f"Download model {model} now (several GB)?", assume_yes):
            run([exe, "pull", model])
        else:
            warn(f"model {model} missing: run 'ollama pull {model}'")


# ---------------------------------------------------------------- 6. checks
def run_checks() -> None:
    say("Checks: contracts and tests")
    py = str(venv_python())
    run([py, "scripts/check_contracts.py"])
    code = run([py, "-m", "pytest", "backend/tests", "-q"], check=False)
    if code == 0:
        ok("all tests pass")
    else:
        warn("some tests failed: see the output above")


def main() -> None:
    p = argparse.ArgumentParser(description="One-time WattWalk setup")
    p.add_argument("--yes", action="store_true", help="install everything without asking; never asks for keys")
    p.add_argument("--skip-tests", action="store_true")
    args = p.parse_args()
    check_versions()
    setup_backend()
    setup_frontend()
    env = setup_env(args.yes)
    setup_ollama(env, args.yes)
    if not args.skip_tests:
        run_checks()
    say("Done. Start everything with:  python3 scripts/run.py")
    print("    Still manual (cannot be automated): keys from /costar-keys, the CoStar kit download, and adding\n"
          "    localhost:5173 to the SDK key's allowed domains on my.matterport.com (Settings > Developer Tools).")


if __name__ == "__main__":
    main()
