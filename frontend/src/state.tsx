/**
 * One top-level store (plan A.7): a React context + useReducer holding every
 * piece of server-derived state.  Components never keep their own copies of
 * audit, inventory, coverage or plan data.
 */
import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type {
  AiAlternativesResponse,
  AssetEnergyResponse,
  AuditResponse,
  Benchmark,
  CorrectionResponse,
  Health,
  PlanRequest,
  PlanResponse,
  Question,
  TestModel,
  WattEvent,
} from "./contracts";
import { DEFAULT_PLAN_REQUEST, FIXTURE_SID } from "./fixtures";
import type { PinColorMode } from "./viewer/energyColor";

export type ViewMode = "3d" | "2d" | "heat";

export interface RequestError {
  status: number;
  message: string;
  field?: string | null;
}

export interface AppState {
  selectedSid: string;
  audit: AuditResponse | null;
  auditError: RequestError | null;
  events: WattEvent[];
  plan: PlanResponse | null;
  /** Energy and heat per asset (GET /audits/{sid}/energy); null until the inventory exists. */
  energy: AssetEnergyResponse | null;
  planRequest: PlanRequest;
  planLoading: boolean;
  planError: RequestError | null;
  selectedAssetId: string | null;
  /** Asset whose energy alternatives card is open, or null. */
  focusAssetId: string | null;
  /** Screen point the alternatives card grows from (a clicked 3D glow), or null for the centre. */
  focusOrigin: { x: number; y: number; r?: number; color?: string } | null;
  /** AI upgrade ideas fetched so far, by asset id. */
  aiAlternatives: Record<string, AiAlternativesResponse>;
  /** Upgrade the user picked for each asset in its card (one per asset), by asset id. */
  chosenUpgrades: Record<string, string>;
  /** Every pick, per apartment; chosenUpgrades is the selected apartment's share of it. */
  picks: Picks;
  openQuestion: Question | null;
  health: Health | null;
  healthError: string | null;
  testModels: TestModel[];
  modelsError: string | null;
  viewMode: ViewMode;
  /** Building overview shown in the main panel (street address, lower case), or null for the unit view. */
  buildingView: string | null;
  /** Pin colours: details known/unknown (default), cost per year, or heat per year. */
  pinColorMode: PinColorMode;
  benchmark: Benchmark | null;
  benchmarkError: string | null;
  correctionDiff: string[];
  correctionError: string | null;
  changedAssetIds: string[];
  fixtureNotice: string | null;
}

/** An upgrade picked for one item of one apartment, kept with what the plan needs to show it. */
export interface Pick {
  upgradeId: string;
  title: string;
  /** Yearly saving and install cost (midpoints, USD). */
  saves: number;
  cost: number;
  item: string;
  room: string;
}

/** Picks per apartment (sid) and item (asset id). */
export type Picks = Record<string, Record<string, Pick>>;

const PICKS_KEY = "wattwalk.picks.v1";

function loadPicks(): Picks {
  try {
    const raw = window.localStorage.getItem(PICKS_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Picks) : {};
  } catch {
    return {};
  }
}

/** Remember the picks in this browser (they survive reloads). */
export function savePicks(picks: Picks): void {
  try {
    window.localStorage.setItem(PICKS_KEY, JSON.stringify(picks));
  } catch {
    // private mode or storage blocked: picks last for this session only
  }
}

const chosenFor = (picks: Picks, sid: string): Record<string, string> =>
  Object.fromEntries(Object.entries(picks[sid] ?? {}).map(([assetId, pick]) => [assetId, pick.upgradeId]));

export const initialState: AppState = {
  selectedSid: FIXTURE_SID,
  audit: null,
  auditError: null,
  events: [],
  plan: null,
  energy: null,
  planRequest: DEFAULT_PLAN_REQUEST,
  planLoading: false,
  planError: null,
  selectedAssetId: null,
  focusAssetId: null,
  focusOrigin: null,
  aiAlternatives: {},
  chosenUpgrades: {},
  picks: typeof window === "undefined" ? {} : loadPicks(),
  openQuestion: null,
  health: null,
  healthError: null,
  testModels: [],
  modelsError: null,
  viewMode: "2d",
  buildingView: null,
  pinColorMode: "heat",
  benchmark: null,
  benchmarkError: null,
  correctionDiff: [],
  correctionError: null,
  changedAssetIds: [],
  fixtureNotice: null,
};

export type Action =
  | { type: "selectSid"; sid: string }
  | { type: "audit"; audit: AuditResponse | null; error?: RequestError | null }
  | { type: "auditError"; error: RequestError | null }
  | { type: "addEvent"; event: WattEvent }
  | { type: "clearEvents" }
  | { type: "plan"; plan: PlanResponse | null }
  | { type: "energy"; energy: AssetEnergyResponse | null }
  | { type: "pinColor"; mode: PinColorMode }
  | { type: "aiAlternatives"; data: AiAlternativesResponse }
  | { type: "chooseUpgrade"; assetId: string; upgradeId: string | null; pick?: Pick }
  | { type: "removePick"; sid: string; assetId: string }
  | { type: "buildingView"; key: string | null }
  | { type: "focusEnergy"; assetId: string | null; origin?: { x: number; y: number; r?: number; color?: string } | null }
  | { type: "planRequest"; request: PlanRequest }
  | { type: "planLoading"; loading: boolean }
  | { type: "planError"; error: RequestError | null }
  | { type: "selectAsset"; assetId: string | null }
  | { type: "question"; question: Question | null }
  | { type: "health"; health: Health | null }
  | { type: "healthError"; message: string | null }
  | { type: "models"; models: TestModel[]; error?: string | null }
  | { type: "view"; view: ViewMode }
  | { type: "benchmark"; benchmark: Benchmark | null }
  | { type: "benchmarkError"; message: string | null }
  | {
      type: "correction";
      response: CorrectionResponse;
      diff: string[];
      changed: string[];
    }
  | { type: "correctionError"; message: string | null }
  | { type: "changed"; ids: string[] }
  | { type: "fixtureNotice"; notice: string | null }
  | { type: "resetRun" };

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "selectSid":
      return {
        ...state,
        buildingView: null,
        selectedSid: action.sid,
        chosenUpgrades: chosenFor(state.picks, action.sid),
        audit: null,
        energy: null,
        auditError: null,
        events: [],
        plan: null,
        planError: null,
        planRequest: DEFAULT_PLAN_REQUEST,
        selectedAssetId: null,
        focusAssetId: null,
        focusOrigin: null,
        aiAlternatives: {},
        openQuestion: null,
        correctionDiff: [],
        correctionError: null,
        changedAssetIds: [],
        fixtureNotice: null,
      };
    case "audit": {
      const audit = action.audit;
      let openQuestion: Question | null = null;
      if (audit) {
        openQuestion = audit.questions.find((question) => question.status === "open") ?? null;
        if (!openQuestion && state.openQuestion && state.openQuestion.status === "open") {
          const same = audit.questions.find(
            (question) => question.question_id === state.openQuestion?.question_id,
          );
          // A question event can arrive before the next refetch stores it; keep
          // it only while the audit is running and the server has no record yet.
          if (!same && audit.status.status === "running") {
            openQuestion = state.openQuestion;
          }
        }
      } else {
        openQuestion = state.openQuestion;
      }
      return {
        ...state,
        audit,
        auditError: action.error ?? null,
        openQuestion,
      };
    }
    case "auditError":
      return { ...state, auditError: action.error };
    case "addEvent":
      return { ...state, events: [...state.events, action.event] };
    case "clearEvents":
      return { ...state, events: [] };
    case "focusEnergy":
      return { ...state, focusAssetId: action.assetId, focusOrigin: action.origin ?? null };
    case "pinColor":
      return { ...state, pinColorMode: action.mode };
    case "buildingView":
      return { ...state, buildingView: action.key };
    case "chooseUpgrade": {
      // One pick per item, kept with its apartment so switching apartments never loses or mixes picks.
      const sid = state.selectedSid;
      const unit = { ...(state.picks[sid] ?? {}) };
      if (action.upgradeId && action.pick) unit[action.assetId] = action.pick;
      else delete unit[action.assetId];
      const picks = { ...state.picks, [sid]: unit };
      if (Object.keys(unit).length === 0) delete picks[sid];
      return { ...state, picks, chosenUpgrades: chosenFor(picks, sid) };
    }
    case "removePick": {
      const unit = { ...(state.picks[action.sid] ?? {}) };
      delete unit[action.assetId];
      const picks = { ...state.picks, [action.sid]: unit };
      if (Object.keys(unit).length === 0) delete picks[action.sid];
      return { ...state, picks, chosenUpgrades: chosenFor(picks, state.selectedSid) };
    }
    case "aiAlternatives":
      return { ...state, aiAlternatives: { ...state.aiAlternatives, [action.data.asset_id]: action.data } };
    case "energy":
      return { ...state, energy: action.energy };
    case "plan":
      return { ...state, plan: action.plan };
    case "planRequest":
      return { ...state, planRequest: action.request };
    case "planLoading":
      return { ...state, planLoading: action.loading };
    case "planError":
      return { ...state, planError: action.error };
    case "selectAsset":
      return { ...state, selectedAssetId: action.assetId };
    case "question":
      return { ...state, openQuestion: action.question };
    case "health":
      return { ...state, health: action.health, healthError: null };
    case "healthError":
      return { ...state, healthError: action.message };
    case "models":
      return {
        ...state,
        testModels: action.models,
        modelsError: action.error ?? null,
      };
    case "view":
      return { ...state, viewMode: action.view };
    case "benchmark":
      return { ...state, benchmark: action.benchmark, benchmarkError: null };
    case "benchmarkError":
      return { ...state, benchmarkError: action.message };
    case "correction": {
      const { response } = action;
      const audit = state.audit
        ? {
            ...state.audit,
            inventory: response.inventory,
            coverage: response.coverage,
          }
        : state.audit;
      return {
        ...state,
        audit,
        plan: response.plan,
        planRequest: response.plan.request,
        correctionDiff: action.diff,
        correctionError: null,
        changedAssetIds: action.changed,
      };
    }
    case "correctionError":
      return { ...state, correctionError: action.message };
    case "changed":
      return { ...state, changedAssetIds: action.ids };
    case "fixtureNotice":
      return { ...state, fixtureNotice: action.notice };
    case "resetRun":
      return {
        ...state,
        audit: null,
        auditError: null,
        events: [],
        plan: null,
        energy: null,
        planError: null,
        planRequest: DEFAULT_PLAN_REQUEST,
        selectedAssetId: null,
        focusAssetId: null,
        focusOrigin: null,
        aiAlternatives: {},
        chosenUpgrades: chosenFor(state.picks, state.selectedSid),
        openQuestion: null,
        correctionDiff: [],
        correctionError: null,
        changedAssetIds: [],
        fixtureNotice: null,
      };
    default:
      return state;
  }
}

const StateContext = createContext<AppState | null>(null);
const DispatchContext = createContext<Dispatch<Action> | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <StateContext.Provider value={state}>
      <DispatchContext.Provider value={dispatch}>{children}</DispatchContext.Provider>
    </StateContext.Provider>
  );
}

export function useAppState(): AppState {
  const value = useContext(StateContext);
  if (value === null) throw new Error("useAppState must be used inside AppStateProvider");
  return value;
}

export function useAppDispatch(): Dispatch<Action> {
  const value = useContext(DispatchContext);
  if (value === null) throw new Error("useAppDispatch must be used inside AppStateProvider");
  return value;
}
