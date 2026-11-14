# Person 4 handoff — Spatial viewer and frontend

Project: WattWalk (HackPrinceton Fall 2026). Owner: Person 4.
Status: implemented against the shared fixtures and contract pack; live mode is wired to the documented HTTP API but could not be exercised here because Person 3's backend is not present in this workspace.

## 1. Implemented behavior

### Spatial backend (`backend/wattwalk/spatial/`)

- `geometry.py`
  - `load_basis()` reads `face_basis.json`.
  - `pixel_ray()` implements plan 9.3 (`a = 2(u+0.5)/N - 1`, `b = 1 - 2(v+0.5)/N`).
  - `ray_wall_hit()` solves the 2D ray/segment intersection and returns the nearest positive distance.
  - `anchor_pixel()` uses the bbox centre, top-centre for ceiling labels and bottom-centre for floor-standing labels (plan 9.3).
  - `anchor_from_bbox()` returns the rounded 3D point and `wall_raycast` / `ceiling_plane` / `floor_plane` / `none`, stops 0.10 m before walls, limits hits to 15 m and compares wall and plane hits by horizontal distance (plan 9.4–9.5).
  - `anchor_observation()` is a convenience wrapper for Person 2: it takes a full `Observation` and `ModelGeometry`, looks up the panorama/room and passes `label` automatically.
  - `room_centroid()` supports the approximate 2D fallback.
- `calibrate.py`
  - `candidate_bases()` enumerates the eight candidate bases from plan 9.6.
  - `score_candidate()` triangulates correspondence pairs, rejects rays behind a camera and checks midpoints against room polygons (plan H.5).
  - `evaluate_candidates()` and `choose_basis()` apply the 0.30 m mean-residual and 2x second-best acceptance test.
  - CLI: `python -m wattwalk.spatial.calibrate --sid <sid> --points points.csv [--out ...]`; it can also save horizon faces for two panoramas and writes a diagnostic floor-plan PNG.
- `face_basis.json` keeps the planning default with `status: "unverified"`.

### Frontend (`frontend/`)

- Vite + React 18 + TypeScript app. Every function in plan A.7 is in `src/api.ts`.
- Permanent fixture mode (`VITE_API_BASE` unset or starting with `fixture:`): imports `shared/examples/` through the `@examples` alias, replays the 32-event stream at one event per 300 ms, and serves progressive `AuditResponse` snapshots. The mode banner always says "Illustrative fixture — not a real building".
- HTTP mode: all documented endpoints (start, cancel, reset, get audit, SSE with `from_seq`, plan, explain, corrections, answer, benchmark, crop/ortho files). `DELETE` runs before `POST` on Start to avoid mixing a previous run (plan 7.12.3).
- One context + `useReducer` store (`src/state.tsx`) holds selected sid, audit, events, plan, plan request, selected asset, open question, health, test models and view mode. Refetches are debounced to at most one per 500 ms after `finding`, `tool_result`, `question` and `done`.
- Components: `ModeBanner`, `ModelPicker`, `StartControls`, `BuildingCard`, `AgentLog`, `FloorPlan2D`, `Viewer3D`, `EvidenceCard`, `Inventory`, `Coverage`, `PlanPanel`, `ExplainBox`, `QuestionDialog`, `ModelCallCounter`, `ReportTab`, `BenchmarkTab`, `BottomTabs`, `SourceChip`.
- 2D floor plan: six room polygons, panorama dots, one pin per inventory asset, dashed grey pins labelled "approximate position" while the face basis is unverified, a deterministic room-centroid fallback toggle, rejected-face markers for partial rooms, and a heat-map mode with a percentage legend from `heat_shares`.
- Evidence card: crops (or fixture placeholders), one source chip per attribute, notes, next step, dependent upgrades from the current plan, disagreement warning, attribute corrections (`provided_by_user`) and duplicate merging. The example correction displays exactly `LED: 446.8 to 335.1 kWh/yr`.
- Plan panel: budget slider + number input, four objectives, owner/tenant, tenant-pays-electric, stay months, scalar overrides (lighting hours, $/kWh), debounced 250 ms plan requests, evidence badges, who pays/saves/approval, totals, exclusions with reasons, notes, assumptions with "unverified default" badges, and Explain with formula plus template/model wording.
- Question dialog with a 30 s countdown, choices, skip and expired handling.
- Model-call counter, report Markdown tab, benchmark table with "not run" state, and a global error banner with Retry when the backend is unreachable.
- The 3D tab is disabled because `sdk_frame.json` is uncalibrated; `toSdk()` throws until calibrated and the 2D plan is the default, as plan 9.7 requires.

## 2. Changed files

Owned paths:

- `backend/wattwalk/spatial/__init__.py`
- `backend/wattwalk/spatial/geometry.py`
- `backend/wattwalk/spatial/calibrate.py`
- `backend/wattwalk/spatial/face_basis.json`
- `backend/tests/spatial/test_geometry.py`
- `backend/tests/spatial/test_calibration.py`
- `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`
- `frontend/src/` — `main.tsx`, `App.tsx`, `api.ts`, `fixtures.ts`, `format.ts`, `state.tsx`, `styles.css`, `vite-env.d.ts`, `contracts.ts` (identical copy of the shared mirror), `components/*`, `viewer/{FloorPlan2D,Viewer3D,coords}.tsx|ts`, `viewer/sdk_frame.json`

Baseline files created only because no Person 3 repository baseline existed in this workspace. They are unmodified copies of the pack baseline and should be replaced by Person 3's `baseline-v1` at integration:

- `shared/contracts/`, `shared/examples/`
- `backend/wattwalk/__init__.py`, `config.py`, `errors.py`, `contracts.py`
- `backend/requirements.txt`
- `pytest.ini`

`frontend/src/contracts.ts` is byte-identical to `shared/contracts/typescript/contracts.ts`.

## 3. Startup instructions

```powershell
# frontend, fixture mode (default)
cd frontend
npm install
npm run dev
# open http://localhost:5173, press Start audit

# frontend, live mode once Person 3's API is running
$env:VITE_API_BASE = "http://localhost:8000"
npm run dev

# backend spatial tests (from repository root)
python -m pytest backend/tests/spatial -q

# calibration CLI (live keys + Person 1 adapter, or --geometry)
$env:PYTHONPATH = "backend"
python -m wattwalk.spatial.calibrate --sid <sid> --pano-a p01 --pano-b p02
python -m wattwalk.spatial.calibrate --sid <sid> --points points.csv
```

On bash use `VITE_API_BASE=http://localhost:8000 npm run dev` and `PYTHONPATH=backend python ...`.

## 4. Configuration

- `VITE_API_BASE`: unset or `fixture:` = fixture mode; `http://localhost:8000` = live API. The current test run used fixture mode.
- `backend/wattwalk/spatial/face_basis.json`: `status` is `unverified`, `residual_m` null, camera height 1.5 m.
- `frontend/src/viewer/sdk_frame.json`: `status` is `uncalibrated`; no Showcase SDK application key was available.
- No secrets or provider keys are stored in the code.

## 5. Checks actually run

| Check | Command / procedure | Result |
|---|---|---|
| Spatial unit tests | `python -m pytest backend/tests/spatial -q` | **21 passed** |
| Ten-anchor table | `test_anchor_fixture_table` against `shared/examples/observations.json` | all 10 anchors exactly match plan 4.6.2 (including o005 = 3.002, 3.145, 2.6 and o009 = 0.094, 4.505, 0.241), both through `anchor_from_bbox` and the `anchor_observation` wrapper |
| Synthetic faces/planes | `test_anchor_ceiling_plane`, `test_anchor_floor_plane`, `test_anchor_no_walls`, `test_anchor_nothing_within_15_metres` | pass |
| Synthetic calibration | `test_calibration_synthetic_recovers_default_basis`, rotated-basis case | recovers the generating basis, mean ≈ 0 m, inside ratio 1.0 |
| Calibration CLI smoke | generated 3 correspondence pairs on `fixtureUnitA`, wrote to a temp `--out` | correct candidate mean 0.000 m, second best 0.133 m, accepted, diagnostic PNG written. The repository `face_basis.json` was deliberately left unverified because this environment has no live panoramas. |
| TypeScript | `npx tsc --noEmit` | pass |
| Production build | `npm run build` | pass |
| Fixture UI smoke (Playwright + installed Chrome, 1440 x 900) | start audit, wait for done | 6 room polygons, 9 pins, 32 log events, coverage shows Bathroom `partial`, default plan package present |
| Layout | `document.documentElement.scrollWidth` vs `clientWidth` | 1440 vs 1440; no horizontal page scrolling |
| Plan scenarios | drove the UI through all six example requests | owner 5000 max_bill → 4 lines; owner 2000 → over_budget; tenant 2000 → not_authorized; conservative → 1 line + unverified evidence; budget 0 → 0 lines + over_budget; tenant stay 1 → 0 lines + stay_too_short |
| Correction | evidence card on `a_o005`, `bulb_type = led` | diff exactly `LED: 446.8 to 335.1 kWh/yr` |
| Explain | heat pump line | formula + template explanation shown, labelled "Generated by template" |
| Question dialog | fixture playback | opened with 30 s countdown, choices, Skip, then expired |
| Backend down | second Vite server pointed at `http://127.0.0.1:9999` | global error banner + Retry, all main panels still render; no blank page |
| Console errors | Playwright console listener during the fixture flow | none after adding the favicon |

Not run (no dependency available in this workspace): live audit against Person 3's FastAPI/SSE, Showcase SDK 3D viewer, two-minute demo video recording.

## 6. Known limitations

- Face basis is **unverified**; live calibration was not possible without Matterport face images and a real sid. Pins use the fixture anchors (which are the canonical expected outputs) and are drawn dashed, labelled "approximate position"; the strict room-centroid fallback is available with the "Room centroids" toggle. If an asset has no anchor, the centroid fallback is used automatically.
- 2D is the main viewer. 3D is disabled because there is no SDK application key and `sdk_frame.json` is not calibrated.
- Fixture mode only represents `fixtureUnitA`: other models return 404 for fixture start/get, only the example correction (`a_o005`, `bulb_type = led`) is accepted, and unrecognised plan requests show the default example plan with the documented banner.
- Fixture crops are placeholders because the repository intentionally does not commit Matterport images.
- Fixture playback compresses the 30 s question timeout to about 3 s so the whole run stays short; the dialog itself uses a real 30 s countdown in live mode.
- Answering the fixture question does not recompute a plan (there is no engine in fixture mode); the attribute remains unchanged in fixture data.
- The UI derives display-only counts (unknown attributes, "seen N times", heat percentages) from API arrays; it never computes savings, costs, model counts or shares.
- No demo video was recorded (this environment cannot capture the app; the fixture flow is ready to record).

## 7. Remaining integration issues

- **Person 2:** call `anchor_observation(observation, geometry)` (recommended) or `anchor_from_bbox(..., label=observation.label)`. The contract signature has six arguments; the optional `label` is needed for top-centre/bottom-centre anchoring. Without it, ceiling and floor-standing detections use the box centre and will not reproduce plan 4.6.2.
- **Person 3:** the frontend expects `POST /audits/{sid}` after a `DELETE`, `GET /audits/{sid}/events?from_seq=N` with `data: <Event JSON>`, and the documented 404/409/422 error bodies. CORS must allow `http://localhost:5173`.
- **Person 1:** fixture mode relies on the six example plan requests/responses; live mode posts `PlanRequest` unchanged.
- **3D:** a Showcase SDK key and the SDK-frame calibration (plan 9.7) are still needed; until then the 2D plan is the intended demo view.
- **Face basis:** after live calibration, replace `backend/wattwalk/spatial/face_basis.json`; the banner and pin styling automatically switch to "calibrated" after a rebuild.

## 8. Departures from the specification and why

- `anchor_from_bbox` keeps the canonical six-argument signature and adds optional keyword arguments `label` and `basis`. This is backwards-compatible; it is required because the six-argument signature alone cannot know whether a box is a ceiling or floor-standing label.
- While the face basis is unverified, the UI shows the API anchors (dashed, labelled approximate) instead of defaulting to room centroids, because the fixture anchors are the canonical expected output of plan 4.6.2. The centroid fallback is implemented as a toggle and is used automatically when an anchor is null.
- Start performs a reset before the POST (plan 7.12.3 recommends this), and the local plan inputs return to defaults on Start/Reset so the documented scenarios match exactly.
- A small `SourceChip.tsx` helper was added; it is not in the plan's file list but keeps source-chip rendering in one place.
- Baseline files were copied from the pack because no `baseline-v1` repository was available in this workspace.

## 9. Owned paths touched

- `backend/wattwalk/spatial/`
- `backend/tests/spatial/`
- `frontend/` (all files except `src/contracts.ts`, which is the shared mirror)
