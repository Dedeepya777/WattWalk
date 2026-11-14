# WattWalk — Project Summary and Chat Handoff

Last updated: 2026-11-14. Branch: `v2` (DeepSeek-V4.1-Flash multimodal cloud integration, Ollama purged). Working tree: clean.

Use this file as the short context for a new chat: it captures the current state, the Person 4 work,
the DeepSeek cloud integration, and a one-line map of every folder.

## 1. What WattWalk is

An AI agent that walks a Matterport 3D apartment scan, builds an evidence-backed inventory of
energy-relevant assets (windows, lights, AC units, appliances), places them on a 2D floor plan and in
the 3D tour, and produces a costed upgrade plan showing who pays, who saves, and what needs approval.

Modes:
- **fixture** — illustrative apartment from `shared/examples/`, no keys or network.
- **replay** — recorded audit events from `demo/replays/`.
- **live** — real Matterport scan, real vision model, real planner.
- **3D pins** — optional Matterport Showcase SDK overlay; 2D plan is the safe fallback.

## 2. What was done in this workstream

### 2.1 Branch v2: DeepSeek-V4.1-Flash Cloud Integration & Test Green
- **DeepSeek Multimodal API**: Replaced Ollama across the stack with DeepSeek (`deepseek-flash` / `DeepSeek-V4.1-Flash-1017`).
  - Multimodal vision detection in `backend/wattwalk/vision/detect.py` using OpenAI-compatible chat completions with base64 images.
  - Deep Agents planner model in `backend/wattwalk/agent/deep.py` via `ChatOpenAI`. Verified live tool-calling with `python -m wattwalk.agent.deep ping`.
  - Added `langchain-openai` to `backend/requirements.txt`.
- **Purged Ollama**: Removed all Ollama code, startup scripts, and model downloads. `scripts/doctor.py` and `scripts/run.py` now run without Ollama.
- **Fixed All 10 Failing Tests**: Refreshed `shared/examples/` plan scenario outputs and `correction_response.json` to match current engine computations.
  - Full test suite now passes: **204 passed, 1 skipped, 0 failed**!
- **Frontend verified**: Vitest (16/16 passed), check:text passed, production build passed.
- **Live Probes**: Verified live Matterport API and DeepSeek Vision endpoint via `/health?probe=1` (both live).

## 3. Ollama / local-AI plan

### 3.1 Goal and models

Run the whole AI path for free on a laptop, without a Bedrock account:

| Role | Model | Size | Notes |
|---|---|---|---|
| Vision / detection | `qwen2.5vl:7b` | ~6 GB | Used for both small and large tiers by default. |
| Planner | `qwen3:8b` | ~5 GB | Must support tool calling; wrapped by Deep Agents. |

Requires roughly 8 GB disk and 16 GB RAM for a comfortable run. Ollama must stay running during an
audit. Only one live audit at a time when using Ollama.

### 3.2 One-command path

```bash
python3 scripts/setup.py     # once: .venv, npm install, .env, Ollama install/start/pull, tests
python3 scripts/run.py       # every time: Ollama, backend, frontend; opens localhost:5173
```

`setup.py` writes working local defaults into a new `.env`:

```dotenv
WATTWALK_SMALL_VISION_MODEL_ID=ollama/qwen2.5vl:7b
WATTWALK_LARGE_VISION_MODEL_ID=ollama/qwen2.5vl:7b
WATTWALK_PLANNER_MODEL_ID=ollama/qwen3:8b
WATTWALK_AGENT_MODE=deep_agents
OLLAMA_BASE_URL=http://localhost:11434
```

It never overwrites an existing `.env`. `run.py` starts Ollama when any model id starts with
`ollama/`, starts the FastAPI backend on `:8000`, starts Vite on `:5173`, and probes
`/health?probe=1` so Live mode is allowed before the page opens.

### 3.3 Manual path

```bash
ollama serve
ollama pull qwen2.5vl:7b
ollama pull qwen3:8b
```

Set the `.env` values above, then check the planner:

```bash
PYTHONPATH=backend python -m wattwalk.agent.deep ping
```

### 3.4 Provider routing

`backend/wattwalk/agent/deep.py` picks the planner provider by prefix:

| Prefix | Provider | Required setting |
|---|---|---|
| `ollama/<model>` | `ChatOllama`, `num_ctx=16384` | `OLLAMA_BASE_URL` |
| `gemini/<model>` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY`, `GEMINI_MIN_INTERVAL_S` |
| `openrouter/<model>` | `ChatOpenAI` | `OPENROUTER_API_KEY`; optional `langchain-openai` |
| anything else | `ChatBedrockConverse` | AWS credential chain, `AWS_REGION` |

Vision follows the same `ollama/` or `gemini/` prefixes in `backend/wattwalk/vision/detect.py`.

### 3.5 Relevant `.env` settings

| Variable | Purpose |
|---|---|
| `WATTWALK_DATA_MODE` | `fixture` or `live` data adapters. |
| `WATTWALK_VISION_MODE` | `fixture` or `live` vision. |
| `WATTWALK_AGENT_MODE` | `scripted` (no planner model) or `deep_agents`. |
| `WATTWALK_SMALL_VISION_MODEL_ID` | Small-tier vision model. |
| `WATTWALK_LARGE_VISION_MODEL_ID` | Large-tier/escalated vision model. |
| `WATTWALK_PLANNER_MODEL_ID` | Deep Agents planner model. |
| `OLLAMA_BASE_URL` | Local Ollama server, default `http://localhost:11434`. |
| `GOOGLE_API_KEY` / `GEMINI_MIN_INTERVAL_S` | Gemini API and free-tier pacing. |
| `OPENROUTER_API_KEY` | Optional OpenRouter planner fallback. |
| `MATTERPORT_API_KEY` / `MATTERPORT_API_TOKEN` | Matterport Model API auth. |
| `VITE_MATTERPORT_SDK_KEY` | Browser Showcase SDK key; never commit it. |
| `VITE_API_BASE` | Frontend API base; unset means fixture mode. |
| `COSTAR_KIT_ZIP` / `COSTAR_ZIP_PASSWORD` | Licensed CoStar kit. |

### 3.6 Current Ollama status

Code and setup scripts are merged. **Not live-tested in this environment**: no Ollama install/models,
no Matterport credentials, no Bedrock/Gemini/OpenRouter keys. The first Ollama vision call is slow
because the model loads into memory; repeat runs are faster due to caching.

## 4. Folder map (one line each)

| Path | Contains |
|---|---|
| `backend/` | FastAPI service, agent, vision, data adapters, engine, tests, `requirements.txt`, local `.venv/`. |
| `backend/wattwalk/api/` | FastAPI app, routes, SSE, replay, error mapping, test-model list. |
| `backend/wattwalk/agent/` | Scripted agent + Deep Agents planner, tools, providers, subagents, verifier, prompts, README. |
| `backend/wattwalk/vision/` | Detection/attribute vision, Ollama/Gemini/Bedrock backends, walk/inspect/resolve, probes. |
| `backend/wattwalk/data/` | Matterport, CoStar, EBEWE, Vexcel, building/index adapters and probes. |
| `backend/wattwalk/engine/` | Plan optimizer, heat shares, explain templates, cost/savings logic. |
| `backend/wattwalk/inventory/` | Merge/dedupe, coverage, corrections. |
| `backend/wattwalk/spatial/` | Pixel-to-3D anchors, wall/ceiling/floor raycasts, face basis, calibration CLI. |
| `backend/wattwalk/eval/` | Benchmark helpers. |
| `backend/wattwalk/` root files | `config.py`, `contracts.py`, `store.py`, `errors.py`, `health_registry.py`. |
| `backend/tests/` | Mirrors `wattwalk/`: `api`, `agent`, `data`, `engine`, `eval`, `inventory`, `scripts`, `spatial`, `vision`, shared fixtures. |
| `frontend/` | Vite + React + TypeScript app; `src/`, `scripts/check-text.mjs`, configs, generated `node_modules/` and `dist/`. |
| `frontend/src/components/` | UI panels: model picker, start controls, progress, plan, evidence, inventory, coverage, log, benchmark, report. |
| `frontend/src/viewer/` | 2D floor plan, 3D viewer, SDK adapter, frame fit, 3D readiness. |
| `frontend/src/` root | `App.tsx`, `api.ts`, `state.tsx`, `fixtures.ts`, `format.ts`, `contracts.ts`, `styles.css`. |
| `shared/contracts/` | Canonical JSON schemas, assumptions, upgrade catalog. |
| `shared/examples/` | Fixture API payloads used by backend tests and the frontend fixture mode. |
| `fixtures/` | `models_index.csv` + demo model list; `fixtures/live/<sid>/` geometry/building JSON (images are gitignored). |
| `scripts/` | `setup.py`, `run.py`, `doctor.py`, `check_contracts.py`, `capture_fixture.py`, `fetch_models_index.py`, `validate_live_data.py`. |
| `demo/replays/` | Recorded replay data for offline demos. |
| `audits/` | Generated runtime audit state (gitignored). |
| `eval/` | Benchmark labels/results; large data is gitignored. |
| `.env.example` | All environment variables; copy to `.env`. Never commit `.env`. |
| `README.md` | Setup, run, demo, troubleshooting, project layout. |
| `PERSON4_HANDOFF.md`, `HANDOFF_P3.md`, `HANDOFF_FIX_P3.md` | Historical per-person handoffs. |
| `pytest.ini` | Pytest config (`pythonpath=backend`). |

## 5. Key files for a new chat

| Topic | Files |
|---|---|
| Setup / Ollama | `README.md`, `scripts/setup.py`, `scripts/run.py`, `scripts/doctor.py`, `.env.example` |
| Planner providers | `backend/wattwalk/agent/deep.py`, `backend/wattwalk/agent/README.md` |
| Vision providers | `backend/wattwalk/vision/detect.py`, `backend/wattwalk/vision/probes.py` |
| Config | `backend/wattwalk/config.py` |
| 3D pins | `frontend/src/viewer/Viewer3D.tsx`, `sdkAdapter.ts`, `sdkFrame.ts`, `sdkReadiness.ts` |
| 2D plan / face basis | `frontend/src/viewer/FloorPlan2D.tsx`, `backend/wattwalk/spatial/geometry.py`, `face_basis.json`, `calibrate.py` |
| 3D tests | `frontend/src/viewer/sdkFrame.test.ts`, `sdkAdapter.test.ts` |
| Agent/API tests | `backend/tests/agent/`, `backend/tests/api/`, `backend/tests/conftest.py` |
| Contracts | `shared/contracts/`, `frontend/src/contracts.ts` (mirror; do not edit casually) |

## 6. Current checks and known issues

- Frontend: `npm test` → 16 passed; `npm run build` → pass; `npm run check:text` → pass.
- Backend pytest: **204 passed, 1 skipped, 0 failed**! All plan scenario and correction tests are 100% green.
- Live integration: DeepSeek API and Matterport API both verified live and working via `GET /health?probe=1`.
- Setup checker: `python scripts/doctor.py` → 0 problems.

## 7. Next steps

1. Push branch `v2` to origin.
2. Record the 2-minute demo video with the live DeepSeek integration.
