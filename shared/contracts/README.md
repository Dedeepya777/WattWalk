# WattWalk shared contract pack (schema version 1.0.0)

This folder is identical in all four implementation packs. It is copied once into the shared repository baseline at `shared/contracts/` by Person 3 (see `shared/integration.md` section 2).

## 1. Canonical sources

| What | Canonical file | Mirrors (must match) | Owner of changes |
|---|---|---|---|
| Data shapes (all JSON payloads and stored files) | `wattwalk.schema.json` | `python/contracts.py`, `typescript/contracts.ts`, prose in `plan/plan.md` section 7 | Person 3 coordinates; producer and consumer must both approve |
| Assumption values used by the engine | `assumptions.json` | none | Person 1 |
| Upgrade library (costs, authorizers, stages) | `upgrades.json` | none | Person 1 |
| HTTP API (paths, methods, status codes) | section 4 of this file | `plan/plan.md` section 7.12 | Person 3 |
| Internal Python function signatures | section 5 of this file | `plan/plan.md` section 7.13 | Owner of the module that implements the function |
| Example payloads | `../examples/` | none | Generated together; any contract change regenerates affected examples |

If two documents disagree, the canonical file in the table wins, and the other document is a bug to report in the team chat.

## 2. Units and conventions

| Quantity | Unit | Notes |
|---|---|---|
| Length, coordinates | metre (m) | Matterport Model API frame |
| Area | square metre (m2) | EBEWE uses ft2; convert with `kbtu_per_ft2_to_kwh_per_m2` or 1 ft2 = 0.092903 m2 |
| Energy | kWh per year (kWh/yr) | All savings are annual |
| Money | US dollars (USD) | Costs are one-time; bill savings are per year |
| EBEWE site EUI | kBtu/ft2/yr | Only inside `EbeweRecord`; never mixed with kWh fields |
| Time in events | seconds since run start (`t_s`) | Timestamps elsewhere are ISO 8601 UTC strings |
| Image boxes | pixels in the skybox face image | Origin top-left, x right, y down |

Rounding in API responses: kWh to 1 decimal, USD to 2 decimals, shares to 3 decimals, payback years to 2 decimals. Internal calculations use full precision and round only when serializing.

## 3. Coordinate systems

1. **Model frame (canonical).** Matterport Model API positions (`panoLocations.position`, floor `vertices`). Metres, z up. Every `Vec3` and `Vec2` in these contracts uses this frame.
2. **Skybox face frame.** Faces 0 to 5 per panorama: 0 up, 1 to 4 around the horizon, 5 down (per the CoStar Matterport quickstart). The mapping from face index to direction in the model frame is a calibration constant owned by Person 4 (`backend/wattwalk/spatial/face_basis.json`). It is unverified until Person 4 completes calibration (plan section 9.6).
3. **Showcase SDK frame.** Used only inside `frontend/src/viewer/coords.ts` (Person 4). The conversion from the model frame is a calibration constant. Never store SDK coordinates in the backend.

## 4. HTTP API (Person 3 implements, Person 4 consumes)

Base URL in development: `http://localhost:8000`. All responses are JSON unless noted. Errors use the `Error` shape with the listed HTTP status.

| Method | Path | Request body | Success | Errors |
|---|---|---|---|---|
| GET | `/health` | none | 200 `Health` | none |
| GET | `/models/test` | none | 200 `TestModel[]` | none |
| POST | `/audits/{sid}` | `StartAuditRequest` | 202 `AuditStatus` | 409 conflict (already running), 404 not_found (mode replay or fixture without data), 422 invalid_request |
| POST | `/audits/{sid}/cancel` | none | 200 `AuditStatus` (status cancelled) | 404 not_found |
| DELETE | `/audits/{sid}` | none | 200 `AuditStatus` (status idle) | 409 conflict (running; cancel first) |
| GET | `/audits/{sid}` | none | 200 `AuditResponse` | 404 not_found |
| GET | `/audits/{sid}/events?from_seq=N` | none | 200 `text/event-stream`, each message `data: <Event JSON>` | 404 not_found |
| GET | `/audits/{sid}/model_calls` | none | 200 `ModelCall[]` | 404 not_found |
| POST | `/audits/{sid}/answer` | `AnswerRequest` | 200 `Question` | 404 not_found, 409 conflict (question not open) |
| POST | `/audits/{sid}/plan` | `PlanRequest` | 200 `PlanResponse` | 404 not_found (no inventory yet), 422 invalid_request |
| POST | `/audits/{sid}/explain` | `ExplainRequest` | 200 `ExplainResponse` | 404, 422; on model timeout returns 200 with `generated_by: "template"` |
| POST | `/audits/{sid}/corrections` | `CorrectionRequest` | 200 `CorrectionResponse` | 404 (asset), 422 (field or value invalid) |
| GET | `/audits/{sid}/files/{path}` | none | 200 image/jpeg (crops, Vexcel ortho) | 404 |
| GET | `/benchmark` | none | 200 `Benchmark` | none |

Timeouts: plan, corrections and audit reads must answer within 1 s on a laptop. Explain falls back to the template after 15 s. Upstream calls: Matterport 30 s, Vexcel 20 s, EBEWE 15 s, Bedrock vision 45 s per call.

SSE rules: `seq` starts at 0 and increases by 1. A client reconnecting with `from_seq=N` receives events with `seq >= N`. The last event of a run has `type: "done"` (success, failure or cancellation; `data.status` says which). In replay mode the server re-emits the recorded events with their original spacing, and the first event summary starts with `Replay of run recorded at`.

## 5. Internal Python interfaces (canonical signatures)

All types come from `backend/wattwalk/contracts.py`. Functions raise `wattwalk.errors.UpstreamError(integration, retryable, message)` for external failures and `ValueError` for invalid input. `wattwalk/errors.py` is part of the baseline (Person 3).

### Person 1: data and engine
```python
# backend/wattwalk/data/matterport.py
def get_geometry(sid: str) -> ModelGeometry: ...
def get_face_image(sid: str, pano_id: str, face: int, resolution: Literal["2k", "4k"]) -> pathlib.Path: ...
# backend/wattwalk/data/building.py
def get_building(sid: str, geometry: ModelGeometry) -> Building: ...
# backend/wattwalk/engine/__init__.py
def plan(sid: str, inventory: list[Asset], building: Building, req: PlanRequest) -> PlanResponse: ...
def heat_shares(rooms: list[Room], inventory: list[Asset], building: Building) -> list[HeatShare]: ...
def explain_template(plan: PlanResponse, upgrade_id: str) -> str: ...
```

### Person 2: vision and inventory
```python
# backend/wattwalk/vision/walk.py
def plan_views(geometry: ModelGeometry) -> list[ViewTask]: ...          # ViewTask = {room_id, pano_id, reason}
def inspect_view(sid: str, geometry: ModelGeometry, room_id: str, pano_id: str) -> InspectResult: ...
def resolve(sid: str, geometry: ModelGeometry, observation_id: str, ask: AskFn) -> ResolveResult: ...
# backend/wattwalk/inventory/__init__.py
def build_inventory(observations: list[Observation]) -> list[Asset]: ...
def compute_coverage(geometry: ModelGeometry, observations: list[Observation], inventory: list[Asset], reviewed: dict[str, list[str]], faces_rejected: int, partial_rooms: dict[str, str]) -> Coverage: ...
def apply_correction(inventory: list[Asset], observations: list[Observation], req: CorrectionRequest) -> tuple[list[Asset], list[str]]: ...
# backend/wattwalk/eval/benchmark.py
def run(labels_csv: pathlib.Path) -> Benchmark: ...
```
`InspectResult`, `ResolveResult`, `ViewTask` and `AskFn` are defined in `backend/wattwalk/vision/types.py` (Person 2) with the fields listed in plan section 7.13. `AskFn = Callable[[Question], Optional[str]]` is supplied by Person 3 and returns the answer or `None` on timeout.

### Person 3: store, agent, API
```python
# backend/wattwalk/store.py
def audit_path(sid: str, *parts: str) -> pathlib.Path: ...   # creates parent folders; used for crops and caches
def read(sid: str, name: str, model: type[T] | None = None, default=None): ...
def write(sid: str, name: str, obj) -> None: ...          # atomic write (temp file + rename)
def observations(sid: str) -> list[Observation]: ...
def append_observations(sid: str, obs: list[Observation]) -> None: ...
def apply_resolve(sid: str, result: ResolveResult) -> None: ...   # replaces the updated observation, appends new ones, records the question
def append_model_calls(sid: str, calls: list[ModelCall]) -> None: ...
# Person 2 keeps router state with read/write under the name "router_state.json".
# Adapters read modes through config.effective_data_mode() and config.effective_vision_mode().
# backend/wattwalk/agent/verify.py
def verify_audit(sid: str) -> list[str]: ...              # list of problems, empty when consistent
```

### Person 4: spatial
```python
# backend/wattwalk/spatial/geometry.py
def anchor_from_bbox(pano: Pano, face: int, bbox: BBox, face_px: int, walls: list[WallSegment], room: Room | None) -> tuple[Vec3 | None, str]: ...
```
Returns the anchor and the method string (`wall_raycast`, `ceiling_plane`, `floor_plane`, `none`).

## 6. Versioning

`schema_version` is `1.0.0`. Additive optional fields bump the minor version (1.1.0). Renames, removals, type changes and enum removals bump the major version and need all four people to agree. Every change gets a line in `shared/decision_log.md` and regenerated examples.
