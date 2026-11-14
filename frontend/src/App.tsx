/** Person 4's application shell: fixture/live data flow, SSE refetch rules, layout. */
import { useCallback, useEffect, useRef } from "react";
import {
  ApiFailure,
  cancelAudit,
  consumeFixtureNotice,
  getAudit,
  getBenchmark,
  getHealth,
  getTestModels,
  postPlan,
  resetAudit,
  startAudit,
  subscribeEvents,
} from "./api";
import { AgentLog } from "./components/AgentLog";
import { BottomTabs } from "./components/BottomTabs";
import { BuildingCard } from "./components/BuildingCard";
import { EvidenceCard } from "./components/EvidenceCard";
import { ModelCallCounter } from "./components/ModelCallCounter";
import { ModelPicker } from "./components/ModelPicker";
import { ModeBanner } from "./components/ModeBanner";
import { PlanPanel } from "./components/PlanPanel";
import { QuestionDialog } from "./components/QuestionDialog";
import { StartControls } from "./components/StartControls";
import type { StartAuditRequest, WattEvent } from "./contracts";
import { useAppDispatch, useAppState, type RequestError } from "./state";
import { FloorPlan2D } from "./viewer/FloorPlan2D";
import { Viewer3D } from "./viewer/Viewer3D";
import { isSdkFrameCalibrated } from "./viewer/coords";

function toRequestError(error: unknown): RequestError {
  if (error instanceof ApiFailure) {
    const details = error.body?.error.details;
    const field = details && typeof details.field === "string" ? details.field : null;
    return { status: error.status, message: error.message, field };
  }
  return {
    status: 0,
    message: error instanceof Error ? error.message : "Request failed.",
    field: null,
  };
}

export default function App() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const stateRef = useRef(state);
  stateRef.current = state;

  const stopEventsRef = useRef<(() => void) | null>(null);
  const runNonceRef = useRef(0);
  const refetchTimerRef = useRef<number | null>(null);
  const lastPlanKeyRef = useRef("");

  const refreshAudit = useCallback(
    async (sid: string) => {
      try {
        const audit = await getAudit(sid);
        if (stateRef.current.selectedSid !== sid) return;
        dispatch({ type: "audit", audit });
      } catch (error) {
        if (stateRef.current.selectedSid !== sid) return;
        if (error instanceof ApiFailure && error.status === 404) {
          dispatch({ type: "audit", audit: null });
        } else {
          dispatch({ type: "auditError", error: toRequestError(error) });
        }
      }
    },
    [dispatch],
  );

  const scheduleRefresh = useCallback(
    (sid: string) => {
      if (refetchTimerRef.current !== null) window.clearTimeout(refetchTimerRef.current);
      refetchTimerRef.current = window.setTimeout(() => {
        refetchTimerRef.current = null;
        void refreshAudit(sid);
      }, 500);
    },
    [refreshAudit],
  );

  const loadHealth = useCallback(async () => {
    try {
      const health = await getHealth();
      dispatch({ type: "health", health });
    } catch (error) {
      dispatch({
        type: "healthError",
        message:
          error instanceof ApiFailure
            ? error.message
            : "Cannot reach the WattWalk API. Is the backend running?",
      });
    }
  }, [dispatch]);

  const loadModels = useCallback(async () => {
    try {
      const models = await getTestModels();
      dispatch({ type: "models", models });
      const current = stateRef.current.selectedSid;
      if (models.length > 0 && !models.some((model) => model.sid === current)) {
        dispatch({ type: "selectSid", sid: models[0].sid });
      }
    } catch (error) {
      dispatch({
        type: "models",
        models: [],
        error:
          error instanceof ApiFailure
            ? error.message
            : "Could not load the test models.",
      });
    }
  }, [dispatch]);

  const loadBenchmark = useCallback(async () => {
    try {
      const benchmark = await getBenchmark();
      dispatch({ type: "benchmark", benchmark });
    } catch (error) {
      dispatch({
        type: "benchmarkError",
        message:
          error instanceof ApiFailure ? error.message : "Could not load the benchmark.",
      });
    }
  }, [dispatch]);

  // Initial load and a 60 s health refresh (plan 7.12.1 caches health for 60 s).
  useEffect(() => {
    void loadHealth();
    void loadModels();
    void loadBenchmark();
    const interval = window.setInterval(() => void loadHealth(), 60_000);
    return () => window.clearInterval(interval);
  }, [loadBenchmark, loadHealth, loadModels]);

  // Selecting a model loads its existing audit folder, or shows an empty state.
  useEffect(() => {
    let cancelled = false;
    stopEventsRef.current?.();
    stopEventsRef.current = null;
    if (!state.selectedSid) return () => undefined;
    void getAudit(state.selectedSid)
      .then((audit) => {
        if (!cancelled) dispatch({ type: "audit", audit });
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiFailure && error.status === 404) {
          dispatch({ type: "audit", audit: null });
        } else {
          dispatch({ type: "auditError", error: toRequestError(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, state.selectedSid]);

  // Plan requests: debounced 250 ms, recomputed from current inputs, never cached.
  const inventoryLength = state.audit?.inventory.length ?? 0;
  const requestKey = JSON.stringify(state.planRequest);
  useEffect(() => {
    if (!state.selectedSid || inventoryLength === 0) {
      lastPlanKeyRef.current = "";
      return;
    }
    const key = `${state.selectedSid}|${inventoryLength}|${requestKey}`;
    if (lastPlanKeyRef.current === key) return;
    const timer = window.setTimeout(async () => {
      dispatch({ type: "planLoading", loading: true });
      dispatch({ type: "planError", error: null });
      try {
        const plan = await postPlan(state.selectedSid, state.planRequest);
        lastPlanKeyRef.current = key;
        dispatch({ type: "plan", plan });
        dispatch({ type: "fixtureNotice", notice: consumeFixtureNotice() });
      } catch (error) {
        dispatch({ type: "plan", plan: null });
        dispatch({ type: "planError", error: toRequestError(error) });
      } finally {
        dispatch({ type: "planLoading", loading: false });
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [dispatch, inventoryLength, requestKey, state.planRequest, state.selectedSid]);

  const handleStart = async (mode: StartAuditRequest["mode"]) => {
    const sid = stateRef.current.selectedSid;
    runNonceRef.current += 1;
    const nonce = runNonceRef.current;
    stopEventsRef.current?.();
    stopEventsRef.current = null;
    lastPlanKeyRef.current = "";
    dispatch({ type: "resetRun" });
    dispatch({ type: "clearEvents" });
    dispatch({ type: "auditError", error: null });

    try {
      // Plan 7.12.3: reset first so a previous completed run does not mix with
      // the new events and files. Caches survive reset.
      await resetAudit(sid);
      await startAudit(sid, mode);
      if (nonce !== runNonceRef.current) return;
      stopEventsRef.current = subscribeEvents(sid, 0, (event: WattEvent) => {
        if (nonce !== runNonceRef.current) return;
        dispatch({ type: "addEvent", event });
        if (event.type === "question") scheduleRefresh(sid);
        if (
          event.type === "tool_result" &&
          event.data.question_id &&
          String(event.summary).toLowerCase().includes("expired")
        ) {
          dispatch({ type: "question", question: null });
        }
        if (event.type === "done") dispatch({ type: "question", question: null });
        if (
          event.type === "finding" ||
          event.type === "tool_result" ||
          event.type === "question" ||
          event.type === "done"
        ) {
          scheduleRefresh(sid);
        }
      }, (message) => {
        if (nonce === runNonceRef.current) {
          dispatch({ type: "auditError", error: { status: 0, message } });
        }
      });
      await refreshAudit(sid);
    } catch (error) {
      if (nonce !== runNonceRef.current) return;
      dispatch({ type: "auditError", error: toRequestError(error) });
    }
  };

  const handleCancel = async () => {
    const sid = stateRef.current.selectedSid;
    try {
      await cancelAudit(sid);
      await refreshAudit(sid);
    } catch (error) {
      dispatch({ type: "auditError", error: toRequestError(error) });
    }
  };

  const handleReset = async () => {
    const sid = stateRef.current.selectedSid;
    runNonceRef.current += 1;
    stopEventsRef.current?.();
    stopEventsRef.current = null;
    lastPlanKeyRef.current = "";
    try {
      await resetAudit(sid);
      dispatch({ type: "resetRun" });
      dispatch({ type: "clearEvents" });
      dispatch({ type: "auditError", error: null });
    } catch (error) {
      dispatch({ type: "auditError", error: toRequestError(error) });
    }
  };

  const retry = () => {
    void loadHealth();
    void loadModels();
    if (stateRef.current.selectedSid) void refreshAudit(stateRef.current.selectedSid);
    // Give the plan effect a fresh identity so a transient failure can retry.
    dispatch({ type: "planRequest", request: { ...stateRef.current.planRequest } });
  };

  const heatAvailable = (state.audit?.heat_shares.length ?? 0) > 0;
  const errorBanner = state.healthError ?? state.auditError?.message ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <ModeBanner />
        <ModelCallCounter />
      </header>

      {errorBanner ? (
        <div className="error-banner" role="alert">
          <strong>Connection problem.</strong>
          <span>{errorBanner}</span>
          <button className="button small" onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="main-grid">
        <aside className="left-column">
          <ModelPicker onRetry={() => void loadModels()} />
          <StartControls
            onStart={handleStart}
            onCancel={handleCancel}
            onReset={handleReset}
          />
          <BuildingCard />
        </aside>

        <section className="panel viewer-panel" aria-labelledby="viewer-heading">
          <div className="viewer-tab-row">
            <h2 id="viewer-heading" className="sr-only">
              Spatial viewer
            </h2>
            <div className="segmented" role="group" aria-label="Viewer mode">
              <button
                type="button"
                className={state.viewMode === "3d" ? "segmented-button active" : "segmented-button"}
                aria-pressed={state.viewMode === "3d"}
                title={
                  isSdkFrameCalibrated()
                    ? "3D tour with tags"
                    : "3D tour (pins stay on the 2D plan until the Showcase SDK frame is calibrated)"
                }
                onClick={() => dispatch({ type: "view", view: "3d" })}
              >
                3D
              </button>
              <button
                type="button"
                className={state.viewMode === "2d" ? "segmented-button active" : "segmented-button"}
                aria-pressed={state.viewMode === "2d"}
                onClick={() => dispatch({ type: "view", view: "2d" })}
              >
                2D plan
              </button>
              <button
                type="button"
                className={state.viewMode === "heat" ? "segmented-button active" : "segmented-button"}
                aria-pressed={state.viewMode === "heat"}
                disabled={!heatAvailable}
                title={heatAvailable ? "Room heat shares" : "Heat shares appear after the walk"}
                onClick={() => dispatch({ type: "view", view: "heat" })}
              >
                Heat map
              </button>
            </div>
            <span className="muted small">
              {state.audit?.rooms.length ?? 0} rooms · {state.audit?.inventory.length ?? 0} assets
            </span>
          </div>
          <div className="viewer-body">
            {state.viewMode === "3d" ? <Viewer3D /> : <FloorPlan2D />}
          </div>
        </section>

        <aside className="right-column">
          <PlanPanel />
        </aside>
      </div>

      <div className="bottom-grid">
        <AgentLog />
        <BottomTabs />
      </div>

      <EvidenceCard />
      <QuestionDialog />
    </div>
  );
}
