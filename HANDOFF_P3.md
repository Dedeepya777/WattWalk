# Handoff: Person 3, Agent and API integration (M1 checkpoint)

## 1. Implemented behavior
- Every route in `shared/contracts/README.md` section 4: health, models/test, start / cancel / reset, GET audit, SSE events (`from_seq`, `speed`, 15 s keepalive), model_calls, answer, plan, explain, corrections, files (only `crops/` and `vexcel/`, no `..`), benchmark.
- Error mapping to the `Error` shape: 404 not_found, 409 conflict, 422 invalid_request (with `details.field`), 502/503 upstream, 501 for a temporary stub that cannot answer, 500 internal.
- Store (`store.py`): atomic writes, per-sid lock, canonical helpers, plus `reset` that keeps `audits/cache/`.
- Run loop (`agent/run.py`): one run per sid, cancel flag checked in every tool, fixture override via `RUN_MODE_OVERRIDE`, always ends with `done`.
- Scripted agent, the seven tools, ask callback (30 s by default, `config.TIMEOUTS_S["ask_user"]`), the verifier with ten checks.
- Deep Agents planner (`deepagents` 0.7.38): `create_deep_agent(system_prompt=..., subagents=[...], backend=FilesystemBackend(audits/<sid>, virtual_mode=True), permissions=...)`. The planner may only write under `/agent/`. Planner calls are logged as ModelCall tier `planner`. If the planner skips a step, the run says so and runs it.
- Replay: `promote` CLI, labeled playback (status mode replay, `replay_of`, first event "Replay of run recorded at ..."), observations appear progressively, all snapshot files are copied at the end.
- Explain: the template always; Bedrock rewording only in deep_agents mode with a planner model, 15 s timeout, falls back to the template.

## 2. Changed files
`backend/wattwalk/store.py`, `backend/wattwalk/agent/*`, `backend/wattwalk/api/*`, `backend/tests/agent/*`, `backend/tests/api/*`, `README.md`, `HANDOFF_P3.md`.

## 3. Startup
See README "Agent and API (Person 3)".

## 4. Configuration used in checks
Defaults only (fixture data, fixture vision, scripted agent). No keys.

## 5. Checks actually run
| Check | Result |
|---|---|
| `python scripts/check_contracts.py` | pass |
| `pytest` (27 tests) | pass |
| Fixture audit: GET equals `audit_response.json` except status timestamps and report text | pass |
| Six plan examples, correction, explain, health, models/test, benchmark equal their examples | pass |
| Error examples (not_found, conflict, invalid plan request, failed status upstream_auth) | pass |
| Cancel during a run: cancelled in under 2 s with a `done` event | pass |
| Reset: GET then returns 404 and the cache file remains | pass |
| Question: expires on timeout; an answer sets `provided_by_user` on `a_o007` | pass |
| Verifier: 0 problems on the fixture; flags a duplicate asset, changed totals, a missing crop and others | pass |
| Deep Agents with an offline rule-based model: delegates to all 4 subagents, same inventory and plan as scripted, writing outside `/agent/` refused | pass |
| Replay: labeled, and gives the same inventory and coverage as the recorded run | pass |
| uvicorn over real HTTP, real 30 s question timeout: completed in 33 s | pass |
| Deep Agents on Bedrock, live hero audit under 4 min | not run: no AWS credentials or model id, and no teammate modules yet |

## 6. Known limitations
- `agent/providers.py` stubs (marked TEMPORARY) only serve `fixtureUnitA`. If the inventory differs from the examples (for example after an answered question), the stub engine reuses the example numbers and adds a note saying so.
- Replay speed is set by the first SSE client passing `?speed=`.
- The verifier's duplicate check uses a 0.5 m anchor rule until `wattwalk.inventory.dedupe.same_object` exists.

## 7. Remaining integration issues
- Person 1: `data.matterport.get_geometry`, `data.building.get_building`, `engine.plan`, `engine.heat_shares`, `engine.explain_template`.
- Person 2: `vision.types`, `vision.walk.{plan_views,inspect_view,resolve}`, `inventory.{build_inventory,compute_coverage,apply_correction}`. A `dedupe.same_object(a, b)` would also let the verifier reuse your rule. `resolve` receives the AskFn; when an answer comes back, set the observation attribute to `provided_by_user`.
- Person 4: the frontend can develop against the fixture API now.

## 8. Departures from the specification
- No separate `api/routes.py`: all routes are in `api/app.py`.
- Fixture runs copy the illustrative `model_calls.json` so `model_call_summary` matches the example (the stubs make no model calls).
