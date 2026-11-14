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
from setup import ENV_FILE, ROOT, read_env, start_ollama, venv_python  # noqa: E402

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

    if any(v.startswith("ollama/") for k, v in env.items() if k.endswith("_MODEL_ID")):
        exe = shutil.which("ollama")
        if not exe or not start_ollama(exe):
            sys.exit("These settings use Ollama, but it is not installed or did not start (see scripts/setup.py).")
        print("Ollama is running")

    procs: list[subprocess.Popen] = []
    group = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    procs.append(subprocess.Popen([str(py), "-m", "uvicorn", "wattwalk.api.app:app", "--app-dir", "backend",
                                   "--port", "8000"], cwd=ROOT, **group))
    npm = shutil.which("npm")
    procs.append(subprocess.Popen([npm, "run", "dev", "--", "--port", "5173", "--strictPort"],
                                  cwd=ROOT / "frontend", **group))

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
