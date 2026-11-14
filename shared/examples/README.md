# WattWalk example payloads (ILLUSTRATIVE DATA)

Every file in this folder is **illustrative development data** for the fixture apartment `fixtureUnitA` at the fictional address "100 Example St, Los Angeles". It is not a real building, and no number here was measured.

All files were generated together from one reference calculation, so they agree with each other:
- `plan_response_*` totals equal the sum of their `upgrades` lines.
- `inventory.json` assets reference the observation ids in `observations.json`.
- `coverage.json` counts match `inventory.json` and `observations.json`.
- `model_calls.json` matches `audit_response.json` `model_call_summary`.
- `events.jsonl` narrates the same run.

The engine numbers depend on `../contracts/assumptions.json` (all `unverified_default`) and `../contracts/upgrades.json`. If Person 1 changes those values, the expected numbers in plan section 4.6 and in these files must be regenerated or updated in the same pull request.

| File | Schema type | Purpose |
|---|---|---|
| `model_geometry.json` | ModelGeometry | 6 rooms, 7 panoramas, 9 wall segments |
| `building.json` | Building | Year 1974, 65.0 m2 unit, EBEWE record, all layers `fixture` |
| `observations.json` | Observation[] | 10 observations (window seen twice) |
| `inventory.json` | Asset[] | 9 unique assets; asset id = `a_` + lowest observation id |
| `coverage.json` | Coverage | Bathroom partial (dark face) |
| `heat_shares.json` | HeatShare[] | Living room 0.430 share |
| `model_calls.json` | ModelCall[] | 41 calls: 31 small, 1 large, 9 planner |
| `questions.json` | Question[] | One expired bulb-type question |
| `audit_response.json` | AuditResponse | Full completed fixture audit |
| `audit_response_empty_running.json` | AuditResponse | Boundary: audit just started, nothing yet |
| `audit_status_running.json`, `audit_status_failed.json` | AuditStatus | Running; failed with upstream_auth |
| `events.jsonl` | Event (one per line) | 32 events ending with `done` |
| `start_audit_request.json` | StartAuditRequest | Fixture mode |
| `plan_request_*.json` / `plan_response_*.json` | PlanRequest / PlanResponse | Six scenarios (below) |
| `correction_request.json` / `correction_response.json` | CorrectionRequest / CorrectionResponse | Living-room fixture `a_o005` is LED |
| `explain_request.json` / `explain_response.json` | ExplainRequest / ExplainResponse | Template explanation for heat_pump |
| `answer_request.json` | AnswerRequest | Answer to q001 |
| `health_fixture.json` | Health | Fixture mode, Bedrock unavailable |
| `test_models.json` | TestModel[] | Fixture plus three real LA scans with room outlines and walls (scans without them were removed) |
| `benchmark_not_run.json` | Benchmark | Status `not_run` until Person 2 measures |
| `error_*.json` | Error | conflict, not_found, invalid_request, upstream_unavailable, timeout |

## Plan scenarios

| Scenario file suffix | Request | Chosen upgrades | Cost (USD) | kWh/yr | USD/yr | Key exclusions |
|---|---|---|---|---|---|---|
| `owner_5000_max_bill` | owner, $5,000, max_bill | led, window_film, fridge, heat_pump | 3,964 to 7,709 | 1748.8 | 524.63 | none |
| `owner_2000_max_bill` | owner, $2,000 | led, window_film, fridge | 964 to 1,709 | 800.8 | 240.23 | heat_pump over_budget |
| `tenant_2000_max_bill` | tenant, $2,000, stay 12 | led, window_film | 64 to 109 | 500.8 | 150.23 | fridge, heat_pump not_authorized |
| `owner_5000_conservative` | owner, $5,000, conservative | window_film | 24 to 45 | 54.0 | 16.20 | led, fridge unverified_evidence; heat_pump over_budget (upper estimate) |
| `owner_0_boundary` | owner, $0 | none | 0 | 0.0 | 0.00 | all over_budget |
| `tenant_2000_stay1_boundary` | tenant, $2,000, stay 1 month | none | 0 | 0.0 | 0.00 | led, window_film stay_too_short |

The correction example (`a_o005` bulb_type = led, owner $5,000) keeps all four upgrades, but the LED line now covers 6 bulbs (335.1 kWh/yr, $30 to $48) instead of 8, and the totals become $3,954 to $7,693, 1637.1 kWh/yr, $491.12/yr.
