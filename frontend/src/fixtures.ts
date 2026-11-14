/**
 * Fixture payloads for VITE_API_BASE=fixture: (plan 11.1).
 *
 * Every object here is imported directly from shared/examples through the
 * @examples Vite alias.  Nothing is recomputed: this file only types and groups
 * the illustrative JSON so api.ts can serve it.
 */
import type {
  Asset,
  AuditResponse,
  AuditStatus,
  Benchmark,
  Building,
  CorrectionRequest,
  CorrectionResponse,
  Coverage,
  ExplainRequest,
  ExplainResponse,
  Health,
  HeatShare,
  ModelGeometry,
  Observation,
  PlanRequest,
  PlanResponse,
  Question,
  TestModel,
  WattEvent,
} from "./contracts";

import auditResponseJson from "@examples/audit_response.json";
import auditEmptyRunningJson from "@examples/audit_response_empty_running.json";
import auditStatusRunningJson from "@examples/audit_status_running.json";
import benchmarkNotRunJson from "@examples/benchmark_not_run.json";
import buildingJson from "@examples/building.json";
import correctionRequestJson from "@examples/correction_request.json";
import correctionResponseJson from "@examples/correction_response.json";
import coverageJson from "@examples/coverage.json";
import explainRequestJson from "@examples/explain_request.json";
import explainResponseJson from "@examples/explain_response.json";
import healthFixtureJson from "@examples/health_fixture.json";
import heatSharesJson from "@examples/heat_shares.json";
import inventoryJson from "@examples/inventory.json";
import geometryJson from "@examples/model_geometry.json";
import observationsJson from "@examples/observations.json";
import questionsJson from "@examples/questions.json";
import testModelsJson from "@examples/test_models.json";

import planRequestOwner5000 from "@examples/plan_request_owner_5000_max_bill.json";
import planRequestOwner2000 from "@examples/plan_request_owner_2000_max_bill.json";
import planRequestTenant2000 from "@examples/plan_request_tenant_2000_max_bill.json";
import planRequestOwnerConservative from "@examples/plan_request_owner_5000_conservative.json";
import planRequestOwner0 from "@examples/plan_request_owner_0_boundary.json";
import planRequestTenantStay1 from "@examples/plan_request_tenant_2000_stay1_boundary.json";

import planResponseOwner5000 from "@examples/plan_response_owner_5000_max_bill.json";
import planResponseOwner2000 from "@examples/plan_response_owner_2000_max_bill.json";
import planResponseTenant2000 from "@examples/plan_response_tenant_2000_max_bill.json";
import planResponseOwnerConservative from "@examples/plan_response_owner_5000_conservative.json";
import planResponseOwner0 from "@examples/plan_response_owner_0_boundary.json";
import planResponseTenantStay1 from "@examples/plan_response_tenant_2000_stay1_boundary.json";

import eventsRaw from "@examples/events.jsonl?raw";

export const FIXTURE_SID = "fixtureUnitA";

export const health = healthFixtureJson as unknown as Health;
export const testModels = testModelsJson as unknown as TestModel[];
export const benchmark = benchmarkNotRunJson as unknown as Benchmark;
export const building = buildingJson as unknown as Building;
export const geometry = geometryJson as unknown as ModelGeometry;
export const observations = observationsJson as unknown as Observation[];
export const inventory = inventoryJson as unknown as Asset[];
export const coverage = coverageJson as unknown as Coverage;
export const heatShares = heatSharesJson as unknown as HeatShare[];
export const questions = questionsJson as unknown as Question[];
export const auditStatusRunning = auditStatusRunningJson as unknown as AuditStatus;
export const auditEmptyRunning = auditEmptyRunningJson as unknown as AuditResponse;
export const auditResponse = auditResponseJson as unknown as AuditResponse;
export const correctionRequest = correctionRequestJson as unknown as CorrectionRequest;
export const correctionResponse = correctionResponseJson as unknown as CorrectionResponse;
export const explainRequest = explainRequestJson as unknown as ExplainRequest;
export const explainResponse = explainResponseJson as unknown as ExplainResponse;

export const fixtureEvents: WattEvent[] = eventsRaw
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter(Boolean)
  .map((line) => JSON.parse(line) as WattEvent);

export interface PlanScenario {
  request: PlanRequest;
  response: PlanResponse;
}

export const planScenarios: PlanScenario[] = [
  {
    request: planRequestOwner5000 as unknown as PlanRequest,
    response: planResponseOwner5000 as unknown as PlanResponse,
  },
  {
    request: planRequestOwner2000 as unknown as PlanRequest,
    response: planResponseOwner2000 as unknown as PlanResponse,
  },
  {
    request: planRequestTenant2000 as unknown as PlanRequest,
    response: planResponseTenant2000 as unknown as PlanResponse,
  },
  {
    request: planRequestOwnerConservative as unknown as PlanRequest,
    response: planResponseOwnerConservative as unknown as PlanResponse,
  },
  {
    request: planRequestOwner0 as unknown as PlanRequest,
    response: planResponseOwner0 as unknown as PlanResponse,
  },
  {
    request: planRequestTenantStay1 as unknown as PlanRequest,
    response: planResponseTenantStay1 as unknown as PlanResponse,
  },
];

/** The default request from plan 7.11 and plan 11.4. */
export const DEFAULT_PLAN_REQUEST: PlanRequest = {
  budget_usd: 5000,
  objective: "max_bill",
  role: "owner",
  tenant_pays_electric: true,
  stay_months: 12,
  overrides: {},
};

export function samePlanRequest(a: PlanRequest, b: PlanRequest): boolean {
  const keys = Object.keys(a.overrides ?? {}).sort();
  const otherKeys = Object.keys(b.overrides ?? {}).sort();
  if (keys.length !== otherKeys.length) return false;
  if (keys.some((key, index) => key !== otherKeys[index])) return false;
  if (keys.some((key) => (a.overrides ?? {})[key] !== (b.overrides ?? {})[key])) return false;
  return (
    a.budget_usd === b.budget_usd &&
    a.objective === b.objective &&
    a.role === b.role &&
    a.tenant_pays_electric === b.tenant_pays_electric &&
    a.stay_months === b.stay_months
  );
}
