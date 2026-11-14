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
