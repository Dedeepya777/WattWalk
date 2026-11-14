# WattWalk

An AI agent that walks a Matterport apartment scan, builds an evidence-backed inventory of energy-relevant assets, and produces a costed, constraint-aware upgrade package. Built at HackPrinceton Fall 2026.

Status: under construction. Person 3 maintains this file; see `shared/ownership.md`.

## Quick start (fixture mode, no keys needed)

```bash
cd backend
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
python scripts/check_contracts.py
uvicorn wattwalk.api.app:app --app-dir backend --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The banner shows whether data is live, replay or fixture.

## Live mode

Copy `.env.example` to `.env`, fill keys from `/costar-keys`, set `WATTWALK_DATA_MODE=live`, `WATTWALK_VISION_MODE=live`, `WATTWALK_AGENT_MODE=deep_agents`.

## Data sources

Matterport Model API (CoStar hackathon keys), Vexcel aerial imagery, CoStar data kit, City of Los Angeles EBEWE benchmarking data (data.lacity.org dataset 9yda-i4ya). Provider data is not committed to this repository.

## Agent and API (Person 3)

| Command | What it does |
|---|---|
| `uvicorn wattwalk.api.app:app --app-dir backend --reload --port 8000` | API on http://localhost:8000 (docs at `/docs`) |
| `curl -X POST localhost:8000/audits/fixtureUnitA -H "content-type: application/json" -d '{"mode":"fixture"}'` | Start the fixture audit |
| `curl -N localhost:8000/audits/fixtureUnitA/events` | Stream its events (SSE) until `done` |
| `python -m wattwalk.api.replay promote <sid>` (from `backend/`) | Record a completed live run as a labeled replay in `demo/replays/<sid>/` |
| `pytest backend/tests/agent backend/tests/api` | Person 3 tests |

Agent modes: `WATTWALK_AGENT_MODE=scripted` (fixed tool order, no model) or `deep_agents` (planner on Bedrock via `WATTWALK_PLANNER_MODEL_ID`, delegating to `exterior_analyst`, `walker`, `retrofit_planner`, `verifier`). Fixture runs always use the scripted agent. Replays are always labeled "Replay of run recorded at ...".

Until each owner's module lands on `main`, `backend/wattwalk/agent/providers.py` serves the fixture apartment from `shared/examples/` behind the canonical signatures. The real module wins automatically as soon as it is importable; `GET /` lists which functions are real and which are stubs.
