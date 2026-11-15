/**
 * WattWalk API client (Person 4).
 *
 * Every function in plan A.7 lives here.  When VITE_API_BASE starts with
 * "fixture:", calls are served from shared/examples (plan 11.1); the permanent
 * fixture mode is used for development and as a demo fallback and is always
 * labelled in the mode banner.
 *
 * The UI never computes savings, costs, counts or shares.  This module only
 * transports API values.
 */
import type {
  AddBuildingRequest,
  AiAlternativesResponse,
  BuildingSearchResponse,
  Portfolio,
  AnswerRequest,
  ApiError,
  AssetEnergyResponse,
  AuditResponse,
  AuditStatus,
  Benchmark,
  CorrectionRequest,
  CorrectionResponse,
  ExplainRequest,
  ExplainResponse,
  Health,
  ModelCallSummary,
  PlanRequest,
  PlanResponse,
  Question,
  StartAuditRequest,
  TestModel,
  WattEvent,
} from "./contracts";
import {
  DEFAULT_PLAN_REQUEST,
  FIXTURE_SID,
  assetEnergy,
  auditResponse,
  benchmark,
  coverage,
  correctionResponse,
  explainResponse,
  fixtureEvents,
  health,
  heatShares,
  inventory,
  observations,
  planScenarios,
  questions,
  samePlanRequest,
  testModels,
} from "./fixtures";

export class ApiFailure extends Error {
  readonly status: number;
  readonly body: ApiError | null;

  constructor(status: number, body: ApiError | null, message?: string) {
    super(
      message ??
        body?.error.message ??
        (status === 0
          ? "Cannot reach the WattWalk API. Is the backend running?"
          : `Request failed (${status})`),
    );
    this.name = "ApiFailure";
    this.status = status;
    this.body = body;
  }
}

const RAW_BASE = (import.meta.env.VITE_API_BASE ?? "fixture:").trim();
export const isFixtureMode = RAW_BASE.toLowerCase().startsWith("fixture:");
const HTTP_BASE = isFixtureMode ? "" : RAW_BASE.replace(/\/+$/, "");

function request<T>(path: string, init?: RequestInit): Promise<T> {
  return fetch(`${HTTP_BASE}${path}`, init).then(
    async (response) => {
      const text = await response.text();
      let body: unknown = null;
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          body = null;
        }
      }
      if (!response.ok) {
        throw new ApiFailure(response.status, (body as ApiError | null) ?? null);
      }
      return body as T;
    },
    () => {
      throw new ApiFailure(0, null);
    },
  );
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

// --------------------------------------------------------------------------- //
// Fixture playback state
// --------------------------------------------------------------------------- //

type QuestionState = "none" | "open" | "answered" | "expired";

interface FixtureState {
  sid: string;
  started: boolean;
  startedAt: string | null;
  completedAt: string | null;
  eventsSeen: number;
  done: boolean;
  cancelled: boolean;
  questionState: QuestionState;
  answers: Record<string, string>;
}

let fixture: FixtureState = freshFixtureState(FIXTURE_SID);

function freshFixtureState(sid: string): FixtureState {
  return {
    sid,
    started: false,
    startedAt: null,
    completedAt: null,
    eventsSeen: 0,
    done: false,
    cancelled: false,
    questionState: "none",
    answers: {},
  };
}

const fixtureListeners = new Set<(event: WattEvent) => void>();
const fixtureTimers = new Set<number>();

function stopFixtureTimers() {
  for (const timer of fixtureTimers) window.clearTimeout(timer);
  fixtureTimers.clear();
}

function emitFixtureDone(status: "cancelled") {
  const event: WattEvent = {
    seq: fixture.eventsSeen,
    t_s: 0,
    sid: fixture.sid,
    agent: "system",
    type: "done",
    summary: status === "cancelled" ? "Audit cancelled" : "Audit completed",
    data: { status },
  };
  fixture.eventsSeen += 1;
  fixture.done = true;
  fixture.completedAt = new Date().toISOString();
  for (const listener of fixtureListeners) listener(event);
  fixtureListeners.clear();
}

function idleStatus(sid: string, mode: StartAuditRequest["mode"] = "fixture"): AuditStatus {
  return {
    sid,
    status: "idle",
    mode,
    started_at: null,
    finished_at: null,
    error: null,
    replay_of: null,
  };
}

function zeroSummary(): ModelCallSummary {
  return {
    calls_total: 0,
    calls_small: 0,
    calls_large: 0,
    calls_planner: 0,
    cache_hits: 0,
    tokens_in: 0,
    tokens_out: 0,
  };
}

function baseAudit(status: AuditStatus): AuditResponse {
  return {
    schema_version: "1.0.0",
    status,
    building: null,
    rooms: [],
    panos: [],
    observations: [],
    inventory: [],
    coverage: null,
    heat_shares: [],
    model_call_summary: zeroSummary(),
    questions: [],
    report_md: null,
  };
}

function fixtureStatus(): AuditStatus {
  if (!fixture.started) return idleStatus(FIXTURE_SID);
  if (fixture.done) {
    return {
      sid: FIXTURE_SID,
      status: fixture.cancelled ? "cancelled" : "completed",
      mode: "fixture",
      started_at: fixture.startedAt,
      finished_at: fixture.completedAt,
      error: null,
      replay_of: null,
    };
  }
  return {
    sid: FIXTURE_SID,
    status: "running",
    mode: "fixture",
    started_at: fixture.startedAt,
    finished_at: null,
    error: null,
    replay_of: null,
  };
}

function fixtureQuestions(seen: number, done: boolean): Question[] {
  if (seen <= 22) return [];
  const template = questions[0];
  if (!template) return [];
  let state = fixture.questionState;
  if (state === "none") state = done ? "expired" : "open";
  if (done && state === "open") state = "expired";
  return [
    {
      ...template,
      status:
        state === "answered" ? "answered" : state === "expired" ? "expired" : "open",
      answer: fixture.answers[template.question_id] ?? null,
    },
  ];
}

function fixtureAudit(): AuditResponse {
  if (!fixture.started) return baseAudit(idleStatus(FIXTURE_SID));

  const seen = fixture.eventsSeen;
  const done = fixture.done;
  const status = fixtureStatus();

  if (done && !fixture.cancelled) {
    return {
      ...clone(auditResponse),
      status,
      questions: fixtureQuestions(seen, true),
    };
  }

  const response = baseAudit(status);
  response.questions = fixtureQuestions(seen, done);

  if (seen > 3) response.building = clone(auditResponse.building);
  if (seen > 5) {
    response.rooms = clone(auditResponse.rooms);
    response.panos = clone(auditResponse.panos);
  }

  const observationIds = new Set<string>();
  for (const event of fixtureEvents.slice(0, seen)) {
    if (event.type === "finding") {
      const ids = event.data.observation_ids;
      if (Array.isArray(ids)) {
        for (const id of ids) if (typeof id === "string") observationIds.add(id);
      }
    }
  }
  response.observations = observations.filter((item) => observationIds.has(item.id));

  if (seen > 25) {
    response.inventory = clone(inventory);
    response.coverage = clone(coverage);
    response.heat_shares = clone(heatShares);
  }
  if (done) {
    response.model_call_summary = clone(auditResponse.model_call_summary);
    response.report_md = auditResponse.report_md;
  }
  return response;
}

/** Fixture-only notice from the last plan/explain/correction fallback. */
let lastFixtureNotice: string | null = null;
let lastPlan: PlanResponse = planScenarios[0].response;

export function consumeFixtureNotice(): string | null {
  const notice = lastFixtureNotice;
  lastFixtureNotice = null;
  return notice;
}

// --------------------------------------------------------------------------- //
// Public API (plan A.7)
// --------------------------------------------------------------------------- //

export async function getHealth(): Promise<Health> {
  if (isFixtureMode) return clone(health);
  return request<Health>("/health");
}

/**
 * Probe the live integrations (P3-4: GET /health?probe=1).  The probe can take up to 20 s, so the
 * mode selector calls it only when the user opens it (cached for 60 s in StartControls).
 */
export async function getHealthProbe(signal?: AbortSignal): Promise<Health> {
  if (isFixtureMode) return clone(health);
  return request<Health>("/health?probe=1", { signal });
}

const NO_BUILDINGS_IN_FIXTURE = (): ApiFailure =>
  new ApiFailure(503, {
    error: {
      code: "upstream_unavailable",
      message: "Finding buildings needs the live backend (start the app with scripts/run.py).",
      retryable: false,
    },
  });

/** Los Angeles buildings whose street address matches `q`, with their 3D tours. */
export async function searchBuildings(q: string, signal?: AbortSignal): Promise<BuildingSearchResponse> {
  if (isFixtureMode) throw NO_BUILDINGS_IN_FIXTURE();
  return request<BuildingSearchResponse>(`/buildings/search?q=${encodeURIComponent(q)}`, { signal });
}

/** The landlord's buildings. */
export async function getPortfolio(): Promise<Portfolio> {
  if (isFixtureMode) return { schema_version: "1.0.0", buildings: [] };
  return request<Portfolio>("/portfolio");
}

/** Add a building (or change its units) in the landlord's list. */
export async function addBuilding(req: AddBuildingRequest): Promise<Portfolio> {
  if (isFixtureMode) throw NO_BUILDINGS_IN_FIXTURE();
  return request<Portfolio>("/portfolio/buildings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function getTestModels(): Promise<TestModel[]> {
  if (isFixtureMode) return clone(testModels);
  return request<TestModel[]>("/models/test");
}

export async function startAudit(
  sid: string,
  mode: StartAuditRequest["mode"],
): Promise<AuditStatus> {
  if (isFixtureMode) {
    if (sid !== FIXTURE_SID) {
      throw new ApiFailure(404, {
        error: {
          code: "not_found",
          message: `Fixture mode only provides ${FIXTURE_SID}. Choose live/replay mode or a model with a fixture.`,
          retryable: false,
        },
      });
    }
    if (fixture.started && !fixture.done) {
      throw new ApiFailure(409, {
        error: {
          code: "conflict",
          message: "An audit is already running for this model.",
          retryable: true,
        },
      });
    }
    stopFixtureTimers();
    fixture = freshFixtureState(sid);
    fixture.started = true;
    // The banner must never claim live while the data is illustrative.
    fixture.startedAt = new Date().toISOString();
    return fixtureStatus();
  }
  return request<AuditStatus>(`/audits/${encodeURIComponent(sid)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode } satisfies StartAuditRequest),
  });
}

export async function cancelAudit(sid: string): Promise<AuditStatus> {
  if (isFixtureMode) {
    if (!fixture.started) {
      throw new ApiFailure(404, {
        error: { code: "not_found", message: "No audit for this model.", retryable: false },
      });
    }
    stopFixtureTimers();
    if (!fixture.done) {
      fixture.cancelled = true;
      emitFixtureDone("cancelled");
    }
    return fixtureStatus();
  }
  return request<AuditStatus>(`/audits/${encodeURIComponent(sid)}/cancel`, {
    method: "POST",
  });
}

export async function resetAudit(sid: string): Promise<AuditStatus> {
  if (isFixtureMode) {
    stopFixtureTimers();
    fixture = freshFixtureState(sid);
    return idleStatus(sid);
  }
  return request<AuditStatus>(`/audits/${encodeURIComponent(sid)}`, { method: "DELETE" });
}

export async function getAudit(sid: string): Promise<AuditResponse> {
  if (isFixtureMode) {
    if (sid !== FIXTURE_SID) {
      throw new ApiFailure(404, {
        error: { code: "not_found", message: "No fixture audit for this model.", retryable: false },
      });
    }
    return fixtureAudit();
  }
  return request<AuditResponse>(`/audits/${encodeURIComponent(sid)}`);
}

export function subscribeEvents(
  sid: string,
  fromSeq: number,
  onEvent: (event: WattEvent) => void,
  onError?: (message: string) => void,
): () => void {
  if (!isFixtureMode) {
    const source = new EventSource(
      `${HTTP_BASE}/audits/${encodeURIComponent(sid)}/events?from_seq=${fromSeq}`,
    );
    source.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as WattEvent);
      } catch {
        // Ignore malformed frames; the API is responsible for valid JSON.
      }
    };
    source.onerror = () => {
      source.close();
      onError?.("Event stream disconnected. Is the backend running?");
    };
    return () => source.close();
  }

  if (sid !== FIXTURE_SID) return () => undefined;

  fixtureListeners.add(onEvent);
  let cancelled = false;
  const pending = fixtureEvents.filter((event) => event.seq >= fromSeq);
  let delay = 0;
  pending.forEach((event) => {
    delay += 300;
    // Keep the human-in-the-loop dialog visible long enough to read; the real
    // backend timeout is 30 s (plan 7.10), but fixture playback stays short.
    if (
      event.type === "tool_result" &&
      String(event.summary).toLowerCase().includes("expired")
    ) {
      delay += 3000;
    }
    const timer = window.setTimeout(() => {
      fixtureTimers.delete(timer);
      if (cancelled || fixture.done) return;

      if (event.type === "question") {
        fixture.questionState = "open";
      }
      if (
        event.type === "tool_result" &&
        event.data.question_id &&
        String(event.summary).toLowerCase().includes("expired") &&
        fixture.questionState === "open"
      ) {
        fixture.questionState = "expired";
      }

      fixture.eventsSeen = Math.max(fixture.eventsSeen, event.seq + 1);
      if (event.type === "done") {
        fixture.done = true;
        fixture.completedAt = new Date().toISOString();
      }
      for (const listener of fixtureListeners) listener(event);
      if (event.type === "done") {
        fixtureListeners.clear();
      }
    }, delay);
    fixtureTimers.add(timer);
  });

  return () => {
    cancelled = true;
    fixtureListeners.delete(onEvent);
    // Leave scheduled timers alone: a new subscription during the same run
    // should continue playback.  reset/start clear them explicitly.
  };
}

/** Energy and heat per inventory asset. 404 until the audit has an inventory. */
export async function getAssetEnergy(sid: string): Promise<AssetEnergyResponse> {
  if (isFixtureMode) {
    if (sid !== FIXTURE_SID) {
      throw new ApiFailure(404, {
        error: { code: "not_found", message: "Fixture mode only provides fixtureUnitA.", retryable: false },
      });
    }
    return clone(assetEnergy);
  }
  return request<AssetEnergyResponse>(`/audits/${encodeURIComponent(sid)}/energy`);
}

/** 2-3 rough upgrade ideas for one asset from DeepSeek (saved per audit; refresh asks again). */
export async function postResearchAlternatives(
  sid: string,
  assetId: string,
  refresh = false,
): Promise<AiAlternativesResponse> {
  if (isFixtureMode) {
    throw new ApiFailure(503, {
      error: {
        code: "upstream_unavailable",
        message: "Finding more alternatives needs the live backend with DEEPSEEK_API_KEY.",
        retryable: false,
      },
    });
  }
  const query = refresh ? "?refresh=true" : "";
  return request<AiAlternativesResponse>(
    `/audits/${encodeURIComponent(sid)}/assets/${encodeURIComponent(assetId)}/alternatives/research${query}`,
    { method: "POST" },
  );
}

export async function postPlan(sid: string, req: PlanRequest): Promise<PlanResponse> {
  if (isFixtureMode) {
    const match = planScenarios.find((scenario) => samePlanRequest(scenario.request, req));
    if (match) {
      lastFixtureNotice = null;
      lastPlan = match.response;
      return clone(match.response);
    }
    lastFixtureNotice =
      "Fixture mode: only the six example scenarios are available. Showing owner, $5,000, max bill.";
    lastPlan = planScenarios[0].response;
    return clone(planScenarios[0].response);
  }
  return request<PlanResponse>(`/audits/${encodeURIComponent(sid)}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function postExplain(
  sid: string,
  req: ExplainRequest,
): Promise<ExplainResponse> {
  if (isFixtureMode) {
    if (req.upgrade_id === explainResponse.upgrade_id) {
      return clone(explainResponse);
    }
    const line = lastPlan.upgrades.find((item) => item.upgrade_id === req.upgrade_id);
    if (!line) {
      throw new ApiFailure(404, {
        error: {
          code: "not_found",
          message: "That upgrade is not in the current package.",
          retryable: false,
        },
      });
    }
    lastFixtureNotice =
      "Fixture mode: showing the code-generated formula; no model rewording is available.";
    return {
      upgrade_id: line.upgrade_id,
      generated_by: "template",
      text: `${line.explanation} Cost range $${line.cost_low_usd.toLocaleString()} to $${line.cost_high_usd.toLocaleString()}. Evidence: ${line.evidence_level.replace("_", " ")}.`,
    };
  }
  return request<ExplainResponse>(`/audits/${encodeURIComponent(sid)}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function postCorrection(
  sid: string,
  req: CorrectionRequest,
): Promise<CorrectionResponse> {
  if (isFixtureMode) {
    const matchesExample =
      req.asset_id === "a_o005" && req.field === "bulb_type" && req.value === "led";
    if (!matchesExample) {
      throw new ApiFailure(422, {
        error: {
          code: "invalid_request",
          message:
            "Fixture mode only contains the example correction: asset a_o005, bulb_type = led. Run live to correct other findings.",
          retryable: false,
          details: { field: req.field },
        },
      });
    }
    lastFixtureNotice = null;
    lastPlan = correctionResponse.plan;
    return clone(correctionResponse);
  }
  return request<CorrectionResponse>(`/audits/${encodeURIComponent(sid)}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function postAnswer(
  sid: string,
  req: AnswerRequest,
): Promise<Question> {
  if (isFixtureMode) {
    if (fixture.questionState !== "open") {
      throw new ApiFailure(409, {
        error: {
          code: "conflict",
          message: "That question is no longer open.",
          retryable: false,
        },
      });
    }
    const template = questions[0];
    if (!template || req.question_id !== template.question_id) {
      throw new ApiFailure(404, {
        error: { code: "not_found", message: "Unknown question.", retryable: false },
      });
    }
    fixture.questionState = "answered";
    fixture.answers[req.question_id] = req.answer;
    return {
      ...template,
      status: "answered",
      answer: req.answer,
    };
  }
  return request<Question>(`/audits/${encodeURIComponent(sid)}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function getBenchmark(): Promise<Benchmark> {
  if (isFixtureMode) return clone(benchmark);
  return request<Benchmark>("/benchmark");
}

/** Bird's-eye (oblique aerial) photo of the building of `sid`, looking `direction`; "" in fixture mode. */
export function birdseyeUrl(sid: string, direction: "north" | "east" | "south" | "west"): string {
  if (isFixtureMode || !sid) return "";
  return `${HTTP_BASE}/buildings/birdseye?sid=${encodeURIComponent(sid)}&direction=${direction}`;
}

export function fileUrl(sid: string, relPath: string): string {
  if (isFixtureMode) return "";
  return `${HTTP_BASE}/audits/${encodeURIComponent(sid)}/files/${relPath}`;
}

/** Exposed for the mode banner: the configured base without secrets. */
export function apiBaseLabel(): string {
  return isFixtureMode ? "fixture (shared/examples)" : HTTP_BASE;
}

export { DEFAULT_PLAN_REQUEST };
