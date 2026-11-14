# Fix plan handoff: Person 3 (agent, API, replay, integration)

Branch `fix/p3-agent-api`, from `main` at `b329d79`.

## Implemented behaviour per section

| Section | Status | What changed |
|---|---|---|
| P3-5 stubs | Done | `agent/providers.py` is a plain import list of the owners' functions. No fallbacks; a failed import crashes at startup with the real traceback. `StubLimitation`, `implementation_status` and the stub data are gone. `grep -rn TEMPORARY backend/wattwalk/agent backend/wattwalk/api` is clean. |
| P3-4 health | Done | New `wattwalk/health_registry.py` (thread-safe, in memory). `GET /health` reads the registry only: `fixture` when the mode is fixture, `live` only after a real call succeeded within 600 s, otherwise `unavailable`. `GET /health?probe=1` calls the owners' probes concurrently (20 s overall cap), skipping fixture and unconfigured integrations. Live audits also record real outcomes: building layer statuses after `load_building`, and the integration of any `UpstreamError`. |
| P3-3 models | Done | `test_models.json` (API and `shared/examples/`): `r1NfhYW4TAr` (hero) first, then `H7CHGZ8m3Dg`, `2ibibwUGQAe` (still used by Person 2's regression tests), `fixtureUnitA` last. `has_fixture` (both `fixtures/live/<sid>/geometry.json` and `observations.json`) and `has_replay` are computed from files per request. |
| P3-1 Deep Agents | Code done; live check not run | Pinned agent dependencies. `python -m wattwalk.agent.deep ping`. Planner calls are logged under the subagent that made them. Offline fake-model tests always run. A live test skips with a stated reason. `agent/README.md` documents the versions and the exact `create_deep_agent` call. Also accepts `openrouter/<model>` planner ids (see departures). |
| P3-2 replay | Code done; recordings not made | `promote` refuses unless the run completed with 0 verifier problems, and writes `meta.json` with `recorded_at`, data, vision and agent modes, and the git commit. Each run records its modes in `run_modes.json`. Playback's first event begins `Replay of run recorded at <time> (data <mode>, vision <mode>, agent <mode>): `. `--force` was removed. |
| P3-7 config | Done except the decision-log line | Backend `MATTERPORT_SDK_KEY` removed from `.env.example` (`config.py` never had it). Added the localhost-origin comment for `VITE_MATTERPORT_SDK_KEY`, Windows/macOS `COSTAR_KIT_ZIP` examples, the "Amazon Bedrock model ids (not Ollama names)" comment, and `OPENROUTER_API_KEY`. `eval/crops/` was already in `.gitignore`. |
| P3-6 live run | Not done | Blocked: no Bedrock or OpenRouter credentials for vision or the planner on this machine yet, and Person 2's live vision (P2-3) isn't merged. |
| P3-8 README | Not done | Depends on P3-6 and the other handoffs. |

## Changed files

- `backend/wattwalk/agent/providers.py`: rewritten as an import list. Vision is imported before inventory to work around a circular import (see limitations).
- `backend/wattwalk/agent/run.py`:
  - added `PLACEHOLDER_JPEG` and `fixture_available()` (moved from providers);
  - added `run_modes()` and `replay_label()`;
  - records failures in the health registry.
- `backend/wattwalk/agent/tools.py`: records building layer statuses; the stub-only placeholder ortho block is removed.
- `backend/wattwalk/agent/deep.py`: subagent-aware `PlannerCallLogger`, OpenRouter planner option, `ping` CLI.
- `backend/wattwalk/agent/README.md` (new)
- `backend/wattwalk/health_registry.py` (new)
- `backend/wattwalk/api/app.py`: `/health` registry and probes; `/models/test` uses `fixture_available`; `/` no longer reports stub status.
- `backend/wattwalk/api/errors.py`: removed the `StubLimitation` handler.
- `backend/wattwalk/api/replay.py`: promote checks, `meta.json` modes and git commit, label.
- `backend/wattwalk/api/test_models.json`, `shared/examples/test_models.json`
- `shared/examples/health_fixture.json`: `bedrock` is now `fixture` in fixture vision mode, because it follows `VISION_MODE`.
- `backend/wattwalk/config.py`: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`
- `backend/requirements.txt`: pins
- `.env.example`
- Tests:
  - `backend/tests/api/conftest.py`: the `env` fixture forces fixture modes and clears the registry, so P3 tests no longer depend on a developer's local `.env`.
  - `backend/tests/api/test_health.py` (new)
  - `backend/tests/api/test_api.py`: added the model-flags test.
  - `backend/tests/agent/test_agent.py`: provider tests and replay tests.
  - `backend/tests/agent/test_deep_agents.py` (new)

## Commands to reproduce

```bash
python -m pytest -q
python scripts/check_contracts.py
grep -rn TEMPORARY backend/wattwalk/agent backend/wattwalk/api
cd backend && python -m wattwalk.agent.deep ping          # needs WATTWALK_PLANNER_MODEL_ID and credentials
curl "http://localhost:8000/health?probe=1"
python -m wattwalk.api.replay promote r1NfhYW4TAr          # after a completed live run
```

## Configuration used (no secrets)

`WATTWALK_PLANNER_MODEL_ID` was not set. Tests ran with `WATTWALK_DATA_MODE=fixture`, `WATTWALK_VISION_MODE=fixture` and `WATTWALK_AGENT_MODE=scripted`. They also ran with the local live `.env`; results are below.

## Checks actually run

- Full suite with fixture modes: **163 passed, 1 skipped**. The skip is `test_deep_agents_live_fixture`: "WATTWALK_PLANNER_MODEL_ID is not set".
- Full suite with a live local `.env`:
  - 157 passed, 1 skipped, 6 failed.
  - All 6 failures are Person 1's `backend/tests/data/test_building.py` and `test_matterport.py` fixture-mode tests. They read `WATTWALK_DATA_MODE` from the developer's `.env`.
  - All P3 tests pass either way.
- `scripts/check_contracts.py`: OK.
- TEMPORARY grep: clean.
- Not run:
  - `ping` against a real model.
  - `?probe=1` against real probes: none are merged yet.
  - A Deep Agents run with a real model.
  - Any live run.
  - The fresh-venv install of `requirements.txt`: pins are the versions installed and tested in the working environment.

## Known limitations

- Circular import between `wattwalk.inventory` and `wattwalk.vision` (Person 2): `inventory/__init__.py` imports `vision.prompts`, whose package `__init__` imports `walk`, which imports `inventory`.
  - Importing `wattwalk.inventory` before `wattwalk.vision` raises ImportError.
  - `providers.py` imports vision first to avoid it.
  - Person 2 should break the cycle.
- No probe modules exist yet (`wattwalk.data.probes`, `wattwalk.vision.probes`), so `?probe=1` reports those integrations as `unavailable` and logs "probe not available". A live audit still records real outcomes.
- After a restart, live integrations show `unavailable` until a probe or a real call succeeds. This is by design.
- `GET /models/test` now lists the hero (live-only) scan first. The frontend selects `models[0]` on load (`frontend/src/App.tsx:140`), so in fixture mode it opens on a scan that has no fixture until P1-5 and P2-4 land. Tell Person 4.
- The OpenRouter planner path needs `langchain-openai`, which isn't installed or pinned here. Installing it was blocked in this session; `make_model` raises a clear error if it's missing.
- No replay recordings exist (`demo/replays/` is empty). They need P3-6.

## Merge status of the other fix branches

None merged into this branch. Reported to owners:

- **P1:** the 6 data tests depend on the local `.env`. Add the probes `wattwalk.data.probes.probe_*`, which should call `health_registry.record`.
- **P2:**
  - Break the inventory/vision circular import.
  - Add `wattwalk.vision.probes.probe_bedrock`.
  - An OpenRouter vision path is stashed locally (`stash@{0}`, touches `vision/detect.py`) for Person 2 to review.
- **P4:** `GET /health?probe=1` exists for P4-9. `bedrock` now reports `fixture` in fixture vision mode. The hero sid is now first in `/models/test`.

## Departures from the plan

- **OpenRouter planner option.** The team has no Bedrock credits, only free OpenRouter models, so `make_model` also accepts `openrouter/<model>` through `langchain-openai`. Bedrock remains the default path.
- **`promote --force` removed.** The plan says to refuse anything except completed runs with 0 verifier problems. Fixture or scripted runs can be promoted, but their modes are shown in the replay label.
- **Live test.** `test_deep_agents_live_fixture` runs on fixture data with the real planner model. The plan's "with credentials" check describes a run on `fixtureUnitA`.
- **Workshop repository not opened.** The `create_deep_agent` call was verified against the installed deepagents 0.7.38 through the passing offline test, not against the workshop repository.
- **`2ibibwUGQAe` kept** in the model list, because Person 2's vision regression tests use it.
- **Decision-log line not added.** It waits for P4's pull request, and `shared/decision_log.md` doesn't exist yet.
