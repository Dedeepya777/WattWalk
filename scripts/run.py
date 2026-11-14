"""Start WattWalk: Ollama (when .env uses ollama/ models), the backend and the frontend, then open the
browser. Ctrl+C stops the backend and frontend. Run from the repository root after scripts/setup.py:

    python3 scripts/run.py              # opens http://localhost:5173
    python3 scripts/run.py --no-browser
Standard library only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doctor import DEFAULT_API_BASE, report, run_checks  # noqa: E402
from setup import ENV_FILE, ROOT, read_env, venv_python  # noqa: E402

BACKEND = "http://localhost:8000/health"
FRONTEND = "http://localhost:5173"


def wait_for(url: str, seconds: int) -> bool:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return True
        except OSError:
            time.sleep(1)
    return False


HINTS = {
    "matterport": "check MATTERPORT_API_KEY / MATTERPORT_API_TOKEN in .env",
    "bedrock": "the vision model did not answer: check DEEPSEEK_API_KEY in .env",
    "costar_kit": "optional: set COSTAR_KIT_ZIP in .env for year built, units and rent",
    "ebewe": "optional: LA building energy data (needs internet)",
    "vexcel": "optional: roof imagery, needs VEXCEL_API_KEY",
}


def check_integrations(timeout_s: int = 120) -> dict[str, str] | None:
    """Run the backend's integration probes once (what the page's "Check integrations" button does).

    Health starts as "unavailable" for everything after a start, and the page blocks Live mode until a
    probe has succeeded, so doing it here means the page opens with Live already allowed. The first
    vision probe loads the model, hence the long timeout. Never raises.
    """
    import json

    print("Checking integrations (the first check loads the AI model, up to a minute)…", flush=True)
    try:
        with urllib.request.urlopen(f"{BACKEND}?probe=1", timeout=timeout_s) as resp:
            integrations = json.loads(resp.read()).get("integrations", {})
    except (OSError, ValueError) as exc:
        print(f"  could not check integrations ({exc}); use the page's 'Check integrations' button")
        return None
    for name, state in integrations.items():
        hint = "" if state in ("live", "fixture") else f"   ({HINTS.get(name, '')})"
        print(f"  {name:11} {state}{hint}")
    if integrations.get("matterport") == "live" and integrations.get("bedrock") == "live":
        print("  Live audits are ready.")
    return integrations


def main() -> None:
    p = argparse.ArgumentParser(description="Start WattWalk")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    py = venv_python()
    if not py.exists() or not (ROOT / "frontend" / "node_modules").exists():
        sys.exit("Not set up yet: run  python3 scripts/setup.py  first.")
    env = read_env(ENV_FILE) if ENV_FILE.exists() else {}
    print(f"Modes: data {env.get('WATTWALK_DATA_MODE', 'fixture')}, vision {env.get('WATTWALK_VISION_MODE', 'fixture')}, "
          f"agent {env.get('WATTWALK_AGENT_MODE', 'scripted')}")

    # Check the setup before starting anything: problems stop here with numbered fix steps.
    issues = run_checks(include_ports=True)
    if report(issues):
        sys.exit("Fix the problem(s) above, then run  python3 scripts/run.py  again "
                 "(python3 scripts/doctor.py re-checks without starting).")

    procs: list[subprocess.Popen] = []
    group = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    procs.append(subprocess.Popen([str(py), "-m", "uvicorn", "wattwalk.api.app:app", "--app-dir", "backend",
                                   "--port", "8000"], cwd=ROOT, **group))
    npm = shutil.which("npm")
    # Point the page at the backend started above. Variables already in the environment win over .env in
    # Vite, so a missing or "fixture:" VITE_API_BASE in .env can no longer leave the page on the sample data.
    frontend_env = dict(os.environ)
    if env.get("VITE_API_BASE", "").strip() in ("", "fixture:") and "VITE_API_BASE" not in os.environ:
        frontend_env["VITE_API_BASE"] = DEFAULT_API_BASE
        print(f"Using VITE_API_BASE={DEFAULT_API_BASE} for the page (not set in .env)")
    procs.append(subprocess.Popen([npm, "run", "dev", "--", "--port", "5173", "--strictPort"],
                                  cwd=ROOT / "frontend", env=frontend_env, **group))

    def stop(*_):
        print("\nStopping backend and frontend…")
        for proc in procs:
            if proc.poll() is None:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    if not wait_for(BACKEND, 60):
        print("The backend did not start: see its output above.")
        stop()
    if env.get("WATTWALK_DATA_MODE") == "live" or env.get("WATTWALK_VISION_MODE") == "live":
        check_integrations()
    if not wait_for(FRONTEND, 60):
        print("The frontend did not start: see its output above.")
        stop()
    print(f"\nWattWalk is running: {FRONTEND}   (backend {BACKEND})   Ctrl+C to stop\n")
    if not args.no_browser:
        webbrowser.open(FRONTEND)
    while all(proc.poll() is None for proc in procs):
        time.sleep(1)
    print("A server stopped unexpectedly: see its output above.")
    stop()


if __name__ == "__main__":
    main()
