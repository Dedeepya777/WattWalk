"""WattWalk shared contracts, Python mirror (pydantic v2). Schema version 1.0.0.

CANONICAL SOURCE: shared/contracts/wattwalk.schema.json. This file mirrors it field for field.
Copy this file to backend/wattwalk/contracts.py in the shared baseline. Do not edit field names,
types, or enums without the contract change process in shared/integration.md section 6.

Units: metres, square metres, kWh per year, US dollars. Coordinates: Matterport Model API frame,
metres, z up (never the Showcase SDK frame).
"""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_serializer

SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

Source = Literal["visible_in_scan", "reported_in_data", "assumed_for_calculation", "needs_verification", "provided_by_user"]
IntegrationStatus = Literal["live", "fixture", "replay", "unavailable"]
City = Literal["Los Angeles", "Houston"]
AssetLabel = Literal[
    "window", "window_ac", "mini_split", "supply_vent", "thermostat", "ceiling_light", "lamp",
    "refrigerator", "range_gas", "range_electric", "dishwasher", "washer", "dryer", "ceiling_fan", "water_heater",
]
ASSET_LABELS: tuple[str, ...] = (
    "window", "window_ac", "mini_split", "supply_vent", "thermostat", "ceiling_light", "lamp",
    "refrigerator", "range_gas", "range_electric", "dishwasher", "washer", "dryer", "ceiling_fan", "water_heater",
)
AgentName = Literal["planner", "walker", "exterior_analyst", "retrofit_planner", "verifier", "system", "benchmark"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vec2(_Strict):
    x: float
    y: float


class Vec3(_Strict):
    x: float
    y: float
    z: float


class Quat(_Strict):
    """Unit quaternion (Model API panoLocations.rotation); rotates pano-local directions into the model frame."""
    x: float
    y: float
    z: float
    w: float


class BBox(_Strict):
    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(ge=1)
    y1: int = Field(ge=1)


class Attr(_Strict):
    value: Union[str, float, int, None] = None
    source: Source
    note: str = ""
    evidence_obs_ids: list[str] = Field(default_factory=list)


class ErrorBody(_Strict):
    code: Literal["not_found", "invalid_request", "conflict", "upstream_unavailable", "upstream_auth", "timeout", "cancelled", "internal"]
    message: str
    retryable: bool
    details: dict = Field(default_factory=dict)


class Error(_Strict):
    error: ErrorBody


class Room(_Strict):
    id: str
    label: str
    floor_id: str
    area_m2: float = Field(ge=0)
    height_m: Optional[float] = Field(default=None, ge=0)
    polygon: list[Vec2] = Field(min_length=3)
    pano_ids: list[str]


class Pano(_Strict):
    id: str
    label: str
    position: Vec3
    room_id: Optional[str] = None
    rotation: Optional[Quat] = None

    @model_serializer(mode="wrap")
    def _omit_missing_rotation(self, handler):  # keeps rotation-less output identical to 1.0.0
        data = handler(self)
        if isinstance(data, dict) and data.get("rotation") is None:
            data.pop("rotation", None)
        return data


class WallSegment(_Strict):
    a: Vec2
    b: Vec2
    floor_id: str


class ModelGeometry(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    sid: str
    address: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    rooms: list[Room]
    panos: list[Pano]
    walls: list[WallSegment]
    status: IntegrationStatus


class EbeweRecord(_Strict):
    site_eui_kbtu_ft2: float = Field(ge=0)
    gfa_ft2: Optional[float] = Field(default=None, ge=0)
    program_year: int
    year_built: Optional[int] = None
    property_type: str


class Roof(_Strict):
    status: IntegrationStatus
    attributes: dict = Field(default_factory=dict)
    ortho_ref: Optional[str] = None


class LayerStatus(_Strict):
    matterport: IntegrationStatus
    costar: IntegrationStatus
    vexcel: IntegrationStatus
    ebewe: IntegrationStatus


class Building(_Strict):
    address: str
    city: City
    costar_property_id: Optional[str] = None
    year_built: Attr
    units: Attr
    asking_rent_usd_month: Attr
    unit_floor_area_m2: Attr
    ebewe: Optional[EbeweRecord] = None
    roof: Roof
    layer_status: LayerStatus


class Quality(_Strict):
    blur: float = Field(ge=0)
    brightness: float = Field(ge=0, le=255)
    accepted: bool


class Observation(_Strict):
    id: str
    pano_id: str
    face: int = Field(ge=1, le=4)
    resolution: Literal["2k", "4k"]
    face_px: Literal[2048, 4096]
    bbox: BBox
    label: AssetLabel
    attrs: dict[str, Attr] = Field(default_factory=dict)
    model_id: str
    model_tier: Literal["small", "large"]
    escalated: bool
    crop_ref: str
    anchor: Optional[Vec3] = None
    anchor_method: Literal["wall_raycast", "ceiling_plane", "floor_plane", "none"]
    room_id: Optional[str] = None
    quality: Quality
    created_at: str


class Asset(_Strict):
    id: str
    label: AssetLabel
    scope: Literal["unit", "building"] = "unit"
    room_id: Optional[str] = None
    observation_ids: list[str] = Field(min_length=1)
    attrs: dict[str, Attr] = Field(default_factory=dict)
    anchor: Optional[Vec3] = None
    next_step: str = ""
    disagreement: bool = False


class RoomCoverage(_Strict):
    room_id: str
    room_label: str
    status: Literal["reviewed", "partial", "not_visited"]
    panos_reviewed: list[str]
    notes: list[str] = Field(default_factory=list)


class Coverage(_Strict):
    panos_total: int = Field(ge=0)
    panos_reviewed: int = Field(ge=0)
    rooms_total: int = Field(ge=0)
    rooms_reviewed: int = Field(ge=0)
    assets_unique: int = Field(ge=0)
    observations_total: int = Field(ge=0)
    attrs_known: int = Field(ge=0)
    attrs_unknown: int = Field(ge=0)
    faces_rejected: int = Field(ge=0)
    not_visible: list[AssetLabel]
    rooms: list[RoomCoverage]


class ModelCall(_Strict):
    id: str
    agent: AgentName
    kind: Literal["detect", "attr", "planner", "explain"]
    model_id: str
    model_tier: Literal["small", "large", "planner"]
    tokens_in: Optional[int] = Field(default=None, ge=0)
    tokens_out: Optional[int] = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    cache_hit: bool
    image_px: Optional[int] = Field(default=None, ge=0)
    at: str


class ModelCallSummary(_Strict):
    calls_total: int = Field(ge=0)
    calls_small: int = Field(ge=0)
    calls_large: int = Field(ge=0)
    calls_planner: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    tokens_in: Optional[int] = Field(default=None, ge=0)
    tokens_out: Optional[int] = Field(default=None, ge=0)


class HeatShare(_Strict):
    room_id: str
    share: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)


Range2 = tuple[float, float]


class EnergyAlternative(_Strict):
    """One upgrade from upgrades.json applied to one asset: what it would use afterwards and the saving.

    kwh_yr/usd_yr/heat_kwh_yr/power_w are the asset after the upgrade (null when the upgrade acts on the
    whole apartment, e.g. a smart thermostat). payback_years is null when nothing is saved.
    """
    upgrade_id: str
    title: str
    kwh_yr: Optional[Range2] = None
    usd_yr: Optional[Range2] = None
    heat_kwh_yr: Optional[Range2] = None
    power_w: Optional[Range2] = None
    saves_kwh_yr: Range2
    saves_usd_yr: Range2
    cost_usd: Range2
    payback_years: Optional[Range2] = None
    who: str
    basis: str


class AssetEnergy(_Strict):
    """Energy and heat of one inventory asset, as (low, high) ranges (engine/asset_energy.py).

    heat_kwh_yr is negative for a unit that moves heat outside (window AC, mini split). estimated is
    false when no sourced assumption exists for the label; the ranges are then null and note says why.
    """
    asset_id: str
    label: AssetLabel
    room_id: Optional[str] = None
    estimated: bool
    kwh_yr: Optional[Range2] = None
    usd_yr: Optional[Range2] = None
    heat_kwh_yr: Optional[Range2] = None
    power_w: Optional[Range2] = None
    basis: str = ""
    assumed: list[str] = Field(default_factory=list)
    note: str = ""
    alternatives: list[EnergyAlternative] = Field(default_factory=list)


class AssetEnergyResponse(_Strict):
    """GET /audits/{sid}/energy. unassigned_cooling_kwh_yr is cooling energy no scanned asset accounts
    for (a central system with no cooling unit in the scan)."""
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    sid: str
    assets: list[AssetEnergy]
    total_kwh_yr: Range2
    total_usd_yr: Range2
    unassigned_cooling_kwh_yr: float = Field(ge=0)


class Question(_Strict):
    question_id: str
    asset_id: Optional[str] = None
    attr: str
    text: str
    choices: list[str]
    status: Literal["open", "answered", "expired"]
    answer: Optional[str] = None


class AuditStatus(_Strict):
    sid: str
    status: Literal["idle", "running", "completed", "failed", "cancelled"]
    mode: Literal["live", "replay", "fixture"]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[Error] = None
    replay_of: Optional[str] = None


class AuditResponse(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    status: AuditStatus
    building: Optional[Building] = None
    rooms: list[Room] = Field(default_factory=list)
    panos: list[Pano] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    inventory: list[Asset] = Field(default_factory=list)
    coverage: Optional[Coverage] = None
    heat_shares: list[HeatShare] = Field(default_factory=list)
    model_call_summary: ModelCallSummary
    questions: list[Question] = Field(default_factory=list)
    report_md: Optional[str] = None


class StartAuditRequest(_Strict):
    mode: Literal["live", "replay", "fixture"]


class PlanRequest(_Strict):
    budget_usd: float = Field(default=5000, ge=0, le=50000)
    objective: Literal["max_bill", "max_kwh", "best_value", "conservative"] = "max_bill"
    role: Literal["owner", "tenant"] = "owner"
    tenant_pays_electric: bool = True
    stay_months: int = Field(default=12, ge=1, le=120)
    overrides: dict[str, float] = Field(default_factory=dict)


class WhoPays(_Strict):
    pays: Literal["owner", "tenant", "owner_or_tenant"]
    saves: Literal["owner", "tenant"]
    approval: Literal["none", "landlord_approval", "owner_decision"]


class UpgradeLine(_Strict):
    upgrade_id: str
    name: str
    cost_low_usd: float = Field(ge=0)
    cost_high_usd: float = Field(ge=0)
    kwh_saved_yr: float
    bill_saved_usd_yr: float
    explanation: str
    asset_ids: list[str]
    evidence_level: Literal["verified", "partly_unverified"]
    who_pays: WhoPays


class Exclusion(_Strict):
    upgrade_id: str
    reason_code: Literal["not_authorized", "already_efficient", "over_budget", "unverified_evidence", "stay_too_short", "mutually_exclusive", "missing_dependency", "not_selected"]
    reason: str


class AssumptionUsed(_Strict):
    key: str
    value: float
    unit: str
    status: Literal["unverified_default", "sourced", "user_override", "physical_constant"]
    source: str


class PlanTotals(_Strict):
    cost_low_usd: float = Field(ge=0)
    cost_high_usd: float = Field(ge=0)
    kwh_saved_yr: float = Field(ge=0)
    bill_saved_usd_yr: float = Field(ge=0)
    payback_years: Optional[float] = Field(default=None, ge=0)
    baseline_kwh_yr: float = Field(ge=0)
    after_kwh_yr: float = Field(ge=0)


class PlanResponse(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    sid: str
    request: PlanRequest
    upgrades: list[UpgradeLine]
    totals: PlanTotals
    excluded: list[Exclusion]
    notes: list[str]
    assumptions_used: list[AssumptionUsed]
    combos_evaluated: int = Field(ge=0)


class ExplainRequest(_Strict):
    upgrade_id: str
    plan_request: PlanRequest


class ExplainResponse(_Strict):
    upgrade_id: str
    text: str
    generated_by: Literal["llm", "template"]


class CorrectionRequest(_Strict):
    asset_id: str
    field: str
    value: Union[str, float, int]
    plan_request: PlanRequest


class CorrectionResponse(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    inventory: list[Asset]
    coverage: Coverage
    plan: PlanResponse
    changed_asset_ids: list[str]


class AnswerRequest(_Strict):
    question_id: str
    answer: str


class Event(_Strict):
    seq: int = Field(ge=0)
    t_s: float = Field(ge=0)
    sid: str
    agent: AgentName
    type: Literal["status", "todo", "tool_call", "tool_result", "finding", "question", "error", "done"]
    summary: str = Field(max_length=200)
    data: dict = Field(default_factory=dict)


class TestModel(_Strict):
    sid: str
    address: str
    city: City
    note: str
    has_fixture: bool
    has_replay: bool


class HealthIntegrations(_Strict):
    matterport: IntegrationStatus
    vexcel: IntegrationStatus
    costar_kit: IntegrationStatus
    ebewe: IntegrationStatus
    bedrock: IntegrationStatus


class Health(_Strict):
    status: Literal["ok", "degraded"]
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    integrations: HealthIntegrations


class BenchmarkMode(_Strict):
    mode: Literal["small_only", "large_only", "adaptive"]
    detection_precision: float = Field(ge=0, le=1)
    detection_recall: float = Field(ge=0, le=1)
    attr_accuracy: float = Field(ge=0, le=1)
    correct_abstentions: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    escalation_rate: float = Field(ge=0, le=1)
    calls: int = Field(ge=0)
    tokens_in: Optional[int] = Field(default=None, ge=0)
    tokens_out: Optional[int] = Field(default=None, ge=0)
    latency_ms_p50: int = Field(ge=0)
    cache_hits: int = Field(ge=0)


class BenchmarkDataset(_Strict):
    n_images: int = Field(ge=0)
    labeled_by: str
    created_at: Optional[str] = None


class Benchmark(_Strict):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    status: Literal["measured", "not_run", "illustrative"]
    dataset: BenchmarkDataset
    modes: list[BenchmarkMode]
    notes: list[str]
