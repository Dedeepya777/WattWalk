/** Person 4's application shell: fixture/live data flow, SSE refetch rules, layout. */
import { PinColorControls } from "./components/PinColorControls";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiFailure,
  cancelAudit,
  consumeFixtureNotice,
  getAssetEnergy,
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
import { EnergyAlternatives } from "./components/EnergyAlternatives";
import { EvidenceCard } from "./components/EvidenceCard";
import { ModelPicker } from "./components/ModelPicker";
import { ModeBanner } from "./components/ModeBanner";
import { PlanPanel } from "./components/PlanPanel";
import { QuestionDialog } from "./components/QuestionDialog";
import { StartControls } from "./components/StartControls";
import { Logo } from "./components/Logo";
import type { StartAuditRequest, WattEvent } from "./contracts";
import { useAppDispatch, useAppState, type RequestError } from "./state";
import { FloorPlan2D } from "./viewer/FloorPlan2D";
import { Viewer3D } from "./viewer/Viewer3D";
import {
  forgetSdkReady,
  initialSdkReadiness,
  sdkNoKeyTooltip,
  type SdkReadiness,
} from "./viewer/sdkReadiness";

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

  // Bottom panel (agent log and audit detail tabs) stays hidden until the user opens it, like the
  // VS Code terminal. Ctrl+` toggles it; the choice is remembered in this browser.
  const [panelOpen, setPanelOpen] = useState(() => {
    try {
      return localStorage.getItem("wattwalk.panelOpen") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("wattwalk.panelOpen", panelOpen ? "1" : "0");
    } catch {
      // storage unavailable (private window): keep the in-memory choice
    }
  }, [panelOpen]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === "`") {
        event.preventDefault();
        setPanelOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const lastEvent = state.events.length ? state.events[state.events.length - 1] : null;
  const auditRunning = state.audit?.status.status === "running";

  const stopEventsRef = useRef<(() => void) | null>(null);
  const runNonceRef = useRef(0);
  const refetchTimerRef = useRef<number | null>(null);
  const lastPlanKeyRef = useRef("");

  // 3D readiness (P4-5). `sid` pins the cached state to the scan it belongs to; a newly selected
  // scan derives a fresh state from sessionStorage until the viewer reports ready/failed.
  const [sdkState, setSdkState] = useState<{
    sid: string;
    readiness: SdkReadiness;
    attempt: number;
  }>(() => ({
    sid: state.selectedSid,
    readiness: initialSdkReadiness(state.selectedSid),
    attempt: 0,
  }));
  const sdkReadiness =
    sdkState.sid === state.selectedSid
      ? sdkState.readiness
      : initialSdkReadiness(state.selectedSid);

  // P4-8: the run this tab owns, even after the user switches away from its scan.
  const [activeRunSid, setActiveRunSid] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [switchBusy, setSwitchBusy] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

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

  // Stream a run's events into the log and progress bar; also used to reattach to a run that is
  // already going when the page loads or the model is re-selected.
  const listen = useCallback(
    (sid: string, nonce: number) => {
      stopEventsRef.current?.();
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
        if (event.type === "done") {
          dispatch({ type: "question", question: null });
          setActiveRunSid((current) => (current === sid ? null : current));
        }
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
    },
    [dispatch, scheduleRefresh],
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

  // Close the event stream and pending refetch when the app unmounts.  Switching scans also closes
  // it in the selection effect below, so no EventSource is left listening to an old run (P4-8).
  useEffect(
    () => () => {
      stopEventsRef.current?.();
      stopEventsRef.current = null;
      if (refetchTimerRef.current !== null) window.clearTimeout(refetchTimerRef.current);
    },
    [],
  );

  // Selecting a model loads its existing audit folder, or shows an empty state.  If that scan is
  // already running (for example a run started in another tab), attach to its event stream from
  // seq 0 instead of offering Start afresh.
  useEffect(() => {
    let cancelled = false;
    stopEventsRef.current?.();
    stopEventsRef.current = null;
    if (!state.selectedSid) return () => undefined;
    setAuditLoading(true);
    void getAudit(state.selectedSid)
      .then((audit) => {
        if (cancelled) return;
        dispatch({ type: "audit", audit });
        if (audit?.status.status === "running") {
          runNonceRef.current += 1;
          dispatch({ type: "clearEvents" });
          listen(state.selectedSid, runNonceRef.current);
          setActiveRunSid(state.selectedSid);
        } else {
          setActiveRunSid((current) => (current === state.selectedSid ? null : current));
        }
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiFailure && error.status === 404) {
          dispatch({ type: "audit", audit: null });
        } else {
          dispatch({ type: "auditError", error: toRequestError(error) });
        }
      })
      .finally(() => {
        if (!cancelled) setAuditLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, listen, state.selectedSid]);

  // Keep the "run in another scan" flag honest after the user chooses "Keep running" and leaves the
  // scan: once that audit stops (done/failed/cancelled), Start becomes available again.
  useEffect(() => {
    if (!activeRunSid || activeRunSid === state.selectedSid) return undefined;
    const timer = window.setInterval(() => {
      void getAudit(activeRunSid)
        .then((audit) => {
          if (audit.status.status !== "running") {
            setActiveRunSid((current) => (current === activeRunSid ? null : current));
          }
        })
        .catch(() => {
          // The audit folder may be gone after a reset; treat that as no longer running.
          setActiveRunSid((current) => (current === activeRunSid ? null : current));
        });
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [activeRunSid, state.selectedSid]);

  // Plan requests: debounced 250 ms, recomputed from current inputs, never cached.
  const inventoryLength = state.audit?.inventory.length ?? 0;

  // Energy and heat per asset: refetched when the inventory or its attributes change.
  const energyKey = (state.audit?.inventory ?? [])
    .map((asset) => `${asset.id}:${JSON.stringify(asset.attrs)}`)
    .join("|");
  useEffect(() => {
    const sid = state.selectedSid;
    if (!sid || inventoryLength === 0) {
      dispatch({ type: "energy", energy: null });
      return undefined;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const energy = await getAssetEnergy(sid);
        if (!cancelled) dispatch({ type: "energy", energy });
      } catch {
        if (!cancelled) dispatch({ type: "energy", energy: null }); // optional data: never an error banner
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [dispatch, energyKey, inventoryLength, state.selectedSid]);
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
      setActiveRunSid(sid);
      listen(sid, nonce);
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
      setActiveRunSid((current) => (current === sid ? null : current));
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
      setActiveRunSid((current) => (current === sid ? null : current));
      dispatch({ type: "resetRun" });
      dispatch({ type: "clearEvents" });
      dispatch({ type: "auditError", error: null });
    } catch (error) {
      dispatch({ type: "auditError", error: toRequestError(error) });
    }
  };

  /**
   * P4-8: cancel the run on the current scan, wait until the server reports it is no longer
   * running (up to 5 s), then switch.  Returns false when the run did not stop, so the picker
   * can keep its confirm dialog open with the error.
   */
  const cancelAndSwitch = useCallback(async (targetSid: string): Promise<boolean> => {
    const from = stateRef.current.selectedSid;
    if (!from || from === targetSid) {
      dispatch({ type: "selectSid", sid: targetSid });
      return true;
    }
    setSwitchBusy(true);
    setSwitchError(null);
    try {
      if (stateRef.current.audit?.status.status === "running") {
        await cancelAudit(from);
        let stopped = false;
        const deadline = Date.now() + 5_000;
        while (Date.now() < deadline) {
          const latest = await getAudit(from).catch(() => null);
          if (!latest || latest.status.status !== "running") {
            stopped = true;
            break;
          }
          await new Promise((resolve) => window.setTimeout(resolve, 500));
        }
        if (!stopped) {
          setSwitchError(
            "The running audit did not stop within 5 seconds. It is still running; try Cancel again.",
          );
          return false;
        }
        // Close the old stream before selecting the new scan so no listener leaks (P4-8).
        runNonceRef.current += 1;
        stopEventsRef.current?.();
        stopEventsRef.current = null;
        setActiveRunSid((current) => (current === from ? null : current));
      }
      dispatch({ type: "selectSid", sid: targetSid });
      return true;
    } catch (error) {
      setSwitchError(toRequestError(error).message);
      return false;
    } finally {
      setSwitchBusy(false);
    }
  }, [dispatch]);

  const retry = () => {
    void loadHealth();
    void loadModels();
    if (stateRef.current.selectedSid) void refreshAudit(stateRef.current.selectedSid);
    // Give the plan effect a fresh identity so a transient failure can retry.
    dispatch({ type: "planRequest", request: { ...stateRef.current.planRequest } });
  };

  const handleSdkReady = useCallback((sid: string) => {
    setSdkState((previous) => ({
      sid,
      readiness: { kind: "ready" },
      attempt: previous.sid === sid ? previous.attempt : 0,
    }));
  }, []);

  const handleSdkFailed = useCallback((reason: string) => {
    const sid = stateRef.current.selectedSid;
    forgetSdkReady(sid);
    setSdkState((previous) => ({
      sid,
      readiness: { kind: "failed", reason },
      attempt: previous.sid === sid ? previous.attempt : 0,
    }));
  }, []);

  const handleSdkRetry = useCallback(() => {
    const sid = stateRef.current.selectedSid;
    forgetSdkReady(sid);
    setSdkState((previous) => ({
      sid,
      readiness: { kind: "checking" },
      attempt: (previous.sid === sid ? previous.attempt : 0) + 1,
    }));
  }, []);

  const sdkNoKey = sdkReadiness.kind === "no_key";
  const errorBanner = state.healthError ?? state.auditError?.message ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand" aria-label="WattWalk">
          <Logo className="brand-logo" />
          WattWalk
        </div>
        <ModeBanner />
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
          <ModelPicker
            onRetry={() => void loadModels()}
            onCancelAndSwitch={cancelAndSwitch}
            switchBusy={switchBusy}
            switchError={switchError}
            onDismissSwitchError={() => setSwitchError(null)}
          />
          <StartControls
            onStart={handleStart}
            onCancel={handleCancel}
            onReset={handleReset}
            auditLoading={auditLoading}
            otherRunSid={activeRunSid && activeRunSid !== state.selectedSid ? activeRunSid : null}
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
                disabled={sdkNoKey}
                title={
                  sdkNoKey
                    ? sdkNoKeyTooltip()
                    : sdkReadiness.kind === "failed"
                      ? sdkReadiness.reason
                      : "3D tour with each item's heat shown as a glow; click a glow for its cost and upgrades"
                }
                onClick={() => dispatch({ type: "view", view: "3d" })}
              >
                {sdkReadiness.kind === "checking" ? (
                  <span className="spinner" aria-hidden="true" />
                ) : null}
                Heat map
              </button>
              <button
                type="button"
                className={state.viewMode === "2d" ? "segmented-button active" : "segmented-button"}
                aria-pressed={state.viewMode === "2d"}
                onClick={() => dispatch({ type: "view", view: "2d" })}
              >
                2D plan
              </button>
            </div>
            <PinColorControls />
            <span className="muted small">
              {state.audit?.rooms.length ?? 0} rooms {"\u00b7"}{" "}
              {state.audit?.inventory.length ?? 0} assets
            </span>
          </div>
          <div className="viewer-body">
            {state.viewMode === "3d" ? (
              <Viewer3D
                readiness={sdkReadiness}
                attempt={sdkState.sid === state.selectedSid ? sdkState.attempt : 0}
                onReady={handleSdkReady}
                onFailed={handleSdkFailed}
                onRetry={handleSdkRetry}
              />
            ) : (
              <FloorPlan2D />
            )}
          </div>
        </section>

        <aside className="right-column">
          <PlanPanel />
        </aside>
      </div>

      {panelOpen ? (
        <div className="bottom-grid" id="bottom-panel">
          <AgentLog />
          <BottomTabs />
        </div>
      ) : null}

      <button
        type="button"
        className={`panel-bar ${panelOpen ? "open" : ""}`}
        aria-expanded={panelOpen}
        aria-controls="bottom-panel"
        onClick={() => setPanelOpen((open) => !open)}
        title="Show or hide activity and details (Ctrl+`)"
      >
        <span className="panel-bar-chevron" aria-hidden="true">
          ⌃
        </span>
        <span className="panel-bar-title">Activity &amp; details</span>
        {auditRunning ? <span className="panel-bar-live" aria-hidden="true" /> : null}
        <span className="panel-bar-summary">
          {lastEvent ? lastEvent.summary : "Agent log, inventory, coverage and report"}
        </span>
        <span className="panel-bar-hint">{panelOpen ? "Hide" : "Show"} · Ctrl+`</span>
      </button>

      <EvidenceCard />
      <EnergyAlternatives />
      <QuestionDialog />
    </div>
  );
}
