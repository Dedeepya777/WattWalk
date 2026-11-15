// WattWalk shared contracts, TypeScript mirror. Schema version 1.0.0.
//
// CANONICAL SOURCE: shared/contracts/wattwalk.schema.json. This file mirrors it field for field.
// Copy this file to frontend/src/contracts.ts in the shared baseline. Do not edit field names,
// types, or enums without the contract change process in shared/integration.md section 6.
//
// Units: metres, square metres, kWh per year, US dollars. Coordinates: Matterport Model API frame,
// metres, z up. Convert to the Showcase SDK frame only inside frontend/src/viewer/coords.ts.

export const SCHEMA_VERSION = "1.0.0" as const;

export type Source = "visible_in_scan" | "reported_in_data" | "assumed_for_calculation" | "needs_verification" | "provided_by_user";
export type IntegrationStatus = "live" | "fixture" | "replay" | "unavailable";
export type City = "Los Angeles" | "Houston";
export type AssetLabel =
  | "window" | "window_ac" | "mini_split" | "supply_vent" | "thermostat" | "ceiling_light" | "lamp"
  | "refrigerator" | "range_gas" | "range_electric" | "dishwasher" | "washer" | "dryer" | "ceiling_fan" | "water_heater";
export type AgentName = "planner" | "walker" | "exterior_analyst" | "retrofit_planner" | "verifier" | "system" | "benchmark";

export interface Vec2 { x: number; y: number; }
export interface Vec3 { x: number; y: number; z: number; }
export interface Quat { x: number; y: number; z: number; w: number; }
export interface BBox { x0: number; y0: number; x1: number; y1: number; }

export interface Attr {
  value: string | number | null;
  source: Source;
  note?: string;
  evidence_obs_ids?: string[];
}

export interface ErrorBody {
  code: "not_found" | "invalid_request" | "conflict" | "upstream_unavailable" | "upstream_auth" | "timeout" | "cancelled" | "internal";
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
}
export interface ApiError { error: ErrorBody; }

export interface Room {
  id: string;
  label: string;
  floor_id: string;
  area_m2: number;
  height_m: number | null;
  polygon: Vec2[];
  pano_ids: string[];
}

export interface Pano { id: string; label: string; position: Vec3; room_id: string | null; rotation?: Quat | null; }
export interface WallSegment { a: Vec2; b: Vec2; floor_id: string; }

export interface ModelGeometry {
  schema_version: "1.0.0";
  sid: string;
  address: string;
  lat: number | null;
  lon: number | null;
  rooms: Room[];
  panos: Pano[];
  walls: WallSegment[];
  status: IntegrationStatus;
}

export interface EbeweRecord {
  site_eui_kbtu_ft2: number;
  gfa_ft2: number | null;
  program_year: number;
  year_built: number | null;
  property_type: string;
}

export interface Roof { status: IntegrationStatus; attributes: Record<string, unknown>; ortho_ref: string | null; }
export interface LayerStatus { matterport: IntegrationStatus; costar: IntegrationStatus; vexcel: IntegrationStatus; ebewe: IntegrationStatus; }

export interface Building {
  address: string;
  city: City;
  costar_property_id: string | null;
  year_built: Attr;
  units: Attr;
  asking_rent_usd_month: Attr;
  unit_floor_area_m2: Attr;
  ebewe: EbeweRecord | null;
  roof: Roof;
  layer_status: LayerStatus;
}

export interface Quality { blur: number; brightness: number; accepted: boolean; }

export interface Observation {
  id: string;
  pano_id: string;
  face: 1 | 2 | 3 | 4;
  resolution: "2k" | "4k";
  face_px: 2048 | 4096;
  bbox: BBox;
  label: AssetLabel;
  attrs: Record<string, Attr>;
  model_id: string;
  model_tier: "small" | "large";
  escalated: boolean;
  crop_ref: string;
  anchor: Vec3 | null;
  anchor_method: "wall_raycast" | "ceiling_plane" | "floor_plane" | "none";
  room_id: string | null;
  quality: Quality;
  created_at: string;
}

export interface Asset {
  id: string;
  label: AssetLabel;
  scope: "unit" | "building";
  room_id: string | null;
  observation_ids: string[];
  attrs: Record<string, Attr>;
  anchor: Vec3 | null;
  next_step: string;
  disagreement: boolean;
}

export interface RoomCoverage {
  room_id: string;
  room_label: string;
  status: "reviewed" | "partial" | "not_visited";
  panos_reviewed: string[];
  notes: string[];
}

export interface Coverage {
  panos_total: number;
  panos_reviewed: number;
  rooms_total: number;
  rooms_reviewed: number;
  assets_unique: number;
  observations_total: number;
  attrs_known: number;
  attrs_unknown: number;
  faces_rejected: number;
  not_visible: AssetLabel[];
  rooms: RoomCoverage[];
}

export interface ModelCall {
  id: string;
  agent: AgentName;
  kind: "detect" | "attr" | "planner" | "explain";
  model_id: string;
  model_tier: "small" | "large" | "planner";
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number;
  cache_hit: boolean;
  image_px: number | null;
  at: string;
}

export interface ModelCallSummary {
  calls_total: number;
  calls_small: number;
  calls_large: number;
  calls_planner: number;
  cache_hits: number;
  tokens_in: number | null;
  tokens_out: number | null;
}

export interface HeatShare { room_id: string; share: number; weight: number; }

/** A (low, high) range. */
export type Range2 = [number, number];

/** One upgrade applied to one asset: usage after it, the saving, cost and payback. */
/** A real product for an AI upgrade idea; url opens its page (first result on amazon.com). */
export interface ProductSuggestion {
  name: string;
  approx_price_usd: number | null;
  why: string;
  url: string;
}

export interface EnergyAlternative {
  upgrade_id: string;
  title: string;
  kwh_yr: Range2 | null;
  usd_yr: Range2 | null;
  heat_kwh_yr: Range2 | null;
  power_w: Range2 | null;
  saves_kwh_yr: Range2;
  saves_usd_yr: Range2;
  cost_usd: Range2;
  payback_years: Range2 | null;
  who: string;
  basis: string;
  products: ProductSuggestion[];
}

/** Energy and heat of one inventory asset (GET /audits/{sid}/energy). heat_kwh_yr < 0 removes heat. */
export interface AssetEnergy {
  asset_id: string;
  label: AssetLabel;
  room_id: string | null;
  estimated: boolean;
  kwh_yr: Range2 | null;
  usd_yr: Range2 | null;
  heat_kwh_yr: Range2 | null;
  power_w: Range2 | null;
  basis: string;
  assumed: string[];
  note: string;
  alternatives: EnergyAlternative[];
}

/** POST /audits/{sid}/assets/{asset_id}/alternatives/research: rough AI upgrade ideas for one asset. */
export interface AiAlternativesResponse {
  schema_version: "1.0.0";
  sid: string;
  asset_id: string;
  model_id: string;
  cached: boolean;
  today_kwh_yr: Range2 | null;
  today_usd_yr: Range2 | null;
  alternatives: EnergyAlternative[];
  note: string;
}

export interface AssetEnergyResponse {
  schema_version: "1.0.0";
  sid: string;
  assets: AssetEnergy[];
  total_kwh_yr: Range2;
  total_usd_yr: Range2;
  unassigned_cooling_kwh_yr: number;
}

export interface Question {
  question_id: string;
  asset_id: string | null;
  attr: string;
  text: string;
  choices: string[];
  status: "open" | "answered" | "expired";
  answer: string | null;
}

export interface AuditStatus {
  sid: string;
  status: "idle" | "running" | "completed" | "failed" | "cancelled";
  mode: "live" | "replay" | "fixture";
  started_at: string | null;
  finished_at: string | null;
  error: ApiError | null;
  replay_of?: string | null;
}

export interface AuditResponse {
  schema_version: "1.0.0";
  status: AuditStatus;
  building: Building | null;
  rooms: Room[];
  panos: Pano[];
  observations: Observation[];
  inventory: Asset[];
  coverage: Coverage | null;
  heat_shares: HeatShare[];
  model_call_summary: ModelCallSummary;
  questions: Question[];
  report_md: string | null;
}

export interface StartAuditRequest { mode: "live" | "replay" | "fixture"; }

export interface PlanRequest {
  budget_usd: number;
  objective: "max_bill" | "max_kwh" | "best_value" | "conservative";
  role: "owner" | "tenant";
  tenant_pays_electric: boolean;
  stay_months: number;
  overrides: Record<string, number>;
}

export interface WhoPays {
  pays: "owner" | "tenant" | "owner_or_tenant";
  saves: "owner" | "tenant";
  approval: "none" | "landlord_approval" | "owner_decision";
}

export interface UpgradeLine {
  upgrade_id: string;
  name: string;
  cost_low_usd: number;
  cost_high_usd: number;
  kwh_saved_yr: number;
  bill_saved_usd_yr: number;
  explanation: string;
  asset_ids: string[];
  evidence_level: "verified" | "partly_unverified";
  who_pays: WhoPays;
}

export interface Exclusion {
  upgrade_id: string;
  reason_code: "not_authorized" | "already_efficient" | "over_budget" | "unverified_evidence" | "stay_too_short" | "mutually_exclusive" | "missing_dependency" | "not_selected";
  reason: string;
}

export interface AssumptionUsed {
  key: string;
  value: number;
  unit: string;
  status: "unverified_default" | "sourced" | "user_override" | "physical_constant";
  source: string;
}

export interface PlanTotals {
  cost_low_usd: number;
  cost_high_usd: number;
  kwh_saved_yr: number;
  bill_saved_usd_yr: number;
  payback_years: number | null;
  baseline_kwh_yr: number;
  after_kwh_yr: number;
}

export interface PlanResponse {
  schema_version: "1.0.0";
  sid: string;
  request: PlanRequest;
  upgrades: UpgradeLine[];
  totals: PlanTotals;
  excluded: Exclusion[];
  notes: string[];
  assumptions_used: AssumptionUsed[];
  combos_evaluated: number;
}

export interface ExplainRequest { upgrade_id: string; plan_request: PlanRequest; }
export interface ExplainResponse { upgrade_id: string; text: string; generated_by: "llm" | "template"; }

export interface CorrectionRequest {
  asset_id: string;
  field: string;
  value: string | number;
  plan_request: PlanRequest;
}

export interface CorrectionResponse {
  schema_version: "1.0.0";
  inventory: Asset[];
  coverage: Coverage;
  plan: PlanResponse;
  changed_asset_ids: string[];
}

export interface AnswerRequest { question_id: string; answer: string; }

export interface WattEvent {
  seq: number;
  t_s: number;
  sid: string;
  agent: AgentName;
  type: "status" | "todo" | "tool_call" | "tool_result" | "finding" | "question" | "error" | "done";
  summary: string;
  data: Record<string, unknown>;
}

export interface TestModel {
  sid: string;
  address: string;
  city: City;
  note: string;
  has_fixture: boolean;
  has_replay: boolean;
}

export interface Health {
  status: "ok" | "degraded";
  schema_version: "1.0.0";
  integrations: { matterport: IntegrationStatus; vexcel: IntegrationStatus; costar_kit: IntegrationStatus; ebewe: IntegrationStatus; bedrock: IntegrationStatus; };
}

export interface BenchmarkMode {
  mode: "small_only" | "large_only" | "adaptive";
  detection_precision: number;
  detection_recall: number;
  attr_accuracy: number;
  correct_abstentions: number;
  unsupported_claims: number;
  escalation_rate: number;
  calls: number;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms_p50: number;
  cache_hits: number;
}

export interface Benchmark {
  schema_version: "1.0.0";
  status: "measured" | "not_run" | "illustrative";
  dataset: { n_images: number; labeled_by: string; created_at: string | null; };
  modes: BenchmarkMode[];
  notes: string[];
}

// Display labels for Source, used by EvidenceCard and other components.
export const SOURCE_LABEL: Record<Source, string> = {
  visible_in_scan: "Visible in scan",
  reported_in_data: "Reported in property data",
  assumed_for_calculation: "Assumed for calculation",
  needs_verification: "Needs verification",
  provided_by_user: "Provided by user",
};
