/** Start / Cancel / Reset controls and mode selector (plan 11.3, P4-9). */
import { useEffect, useRef, useState } from "react";
import { ApiFailure, getHealthProbe, isFixtureMode } from "../api";
import type { Health, StartAuditRequest } from "../contracts";
import { FIXTURE_SID } from "../fixtures";
import { useAppState } from "../state";
import { ProgressTracker } from "./ProgressTracker";

type Mode = StartAuditRequest["mode"];

interface Props {
  onStart: (mode: Mode) => Promise<void>;
  onCancel: () => Promise<void>;
  onReset: () => Promise<void>;
  /** True while GET /audits/{sid} is loading, so Start cannot race a run started elsewhere. */
  auditLoading?: boolean;
  /** A run this tab started on a different scan is still running. */
  otherRunSid?: string | null;
}

const INTEGRATION_LABEL: Record<string, string> = {
  costar_kit: "CoStar",
  ebewe: "EBEWE",
  vexcel: "Vexcel",
};

export function StartControls({
  onStart,
  onCancel,
  onReset,
  auditLoading = false,
  otherRunSid = null,
}: Props) {
  const state = useAppState();
  const running = state.audit?.status.status === "running";
  const [mode, setMode] = useState<Mode>(isFixtureMode ? "fixture" : "live");
  const [busy, setBusy] = useState<null | "start" | "cancel" | "reset">(null);
  const [probe, setProbe] = useState<Health | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const lastProbeRef = useRef(0);
  const probingRef = useRef(false);

  const model = state.testModels.find((item) => item.sid === state.selectedSid);

  const probeLive = async (force = false) => {
    if (probingRef.current) return;
    if (!force && Date.now() - lastProbeRef.current < 60_000) return;
    probingRef.current = true;
    setProbing(true);
    setProbeError(null);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 25_000);
    try {
      const result = await getHealthProbe(controller.signal);
      setProbe(result);
      lastProbeRef.current = Date.now();
    } catch (error) {
      setProbeError(
        error instanceof ApiFailure
          ? error.message
          : "Could not check the live integrations.",
      );
    } finally {
      window.clearTimeout(timer);
      probingRef.current = false;
      setProbing(false);
    }
  };

  const integrations = probe?.integrations;
  const liveReady = Boolean(
    integrations && integrations.matterport === "live" && integrations.bedrock === "live",
  );
  const degraded = integrations
    ? (["costar_kit", "ebewe", "vexcel"] as const)
        .filter((key) => integrations[key] !== "live")
        .map((key) => INTEGRATION_LABEL[key])
    : [];

  const available: Record<Mode, boolean> = {
    live: liveReady,
    replay: Boolean(model?.has_replay),
    fixture:
      Boolean(model?.has_fixture) || (isFixtureMode && state.selectedSid === FIXTURE_SID),
  };
  const anyAvailable = available.live || available.replay || available.fixture;

  useEffect(() => {
    if (available[mode]) return;
    if (available.fixture) setMode("fixture");
    else if (available.replay) setMode("replay");
    else if (available.live) setMode("live");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available.fixture, available.live, available.replay, mode]);

  const liveReason = (() => {
    if (liveReady) return null;
    if (probing) return "Checking Matterport and Bedrock\u2026";
    if (probeError) return `Live needs Matterport and Bedrock. ${probeError}`;
    if (!integrations) return "Live needs Matterport and Bedrock. Check the integrations to enable it.";
    const missing: string[] = [];
    if (integrations.matterport !== "live") missing.push(`Matterport: ${integrations.matterport}`);
    if (integrations.bedrock !== "live") missing.push(`Bedrock: ${integrations.bedrock}`);
    return `Live needs Matterport and Bedrock. ${missing.join(". ")}.`;
  })();

  const noModeReason = available.replay || available.fixture
    ? "No audit mode is available for this scan. Choose another scan or check the integrations."
    : "No audit mode is available. Live needs Matterport and Bedrock, and this scan has no replay or fixture.";

  const startDisabled =
    running ||
    busy !== null ||
    auditLoading ||
    Boolean(otherRunSid) ||
    !available[mode] ||
    state.selectedSid === "";

  const error =
    (state.auditError && state.auditError.status !== 0 ? state.auditError.message : null) ??
    state.audit?.status.error?.error.message ??
    null;

  return (
    <section className="panel" aria-labelledby="run-heading">
      <div className="panel-heading">
        <h2 id="run-heading">Audit</h2>
        <span className={`status-dot status-${state.audit?.status.status ?? "idle"}`}>
          {state.audit?.status.status ?? "idle"}
        </span>
      </div>

      <div className="field">
        <span>Mode</span>
        <div
          className="segmented"
          role="group"
          aria-label="Audit mode"
          onFocus={() => void probeLive()}
          onMouseDown={() => void probeLive()}
        >
          <button
            type="button"
            className={mode === "live" ? "segmented-button active" : "segmented-button"}
            aria-pressed={mode === "live"}
            disabled={!available.live || running || busy !== null}
            title={liveReason ?? "Live audit with Matterport, Bedrock and property data"}
            onClick={() => setMode("live")}
          >
            {probing ? <span className="spinner" aria-hidden="true" /> : null}
            live
          </button>
          <button
            type="button"
            className={mode === "replay" ? "segmented-button active" : "segmented-button"}
            aria-pressed={mode === "replay"}
            disabled={!available.replay || running || busy !== null}
            title={available.replay ? "Replay a recorded audit" : "This scan has no replay recording"}
            onClick={() => setMode("replay")}
          >
            replay
          </button>
          <button
            type="button"
            className={mode === "fixture" ? "segmented-button active" : "segmented-button"}
            aria-pressed={mode === "fixture"}
            disabled={!available.fixture || running || busy !== null}
            title={available.fixture ? "Run the illustrative fixture" : "This scan has no fixture"}
            onClick={() => setMode("fixture")}
          >
            fixture
          </button>
        </div>
      </div>

      {liveReason ? (
        <p className="hint small">
          {liveReason}{" "}
          {!probing ? (
            <button className="button small" onClick={() => void probeLive(true)}>
              Check integrations
            </button>
          ) : null}
        </p>
      ) : degraded.length > 0 ? (
        <p className="hint small">
          Live will run with reduced detail: {degraded.join(", ")} unavailable. The audit degrades
          gracefully.
        </p>
      ) : null}

      {otherRunSid ? (
        <p className="hint small">
          An audit for {otherRunSid} is still running. Cancel it or wait before starting another.
        </p>
      ) : null}

      <div className="button-row">
        {anyAvailable ? (
          <button
            className="button primary"
            onClick={async () => {
              setBusy("start");
              try {
                await onStart(mode);
              } finally {
                setBusy(null);
              }
            }}
            disabled={startDisabled}
          >
            {busy === "start" || auditLoading ? (
              <span className="spinner" aria-hidden="true" />
            ) : null}
            {auditLoading
              ? "Checking scan\u2026"
              : busy === "start"
                ? "Starting\u2026"
                : "Start audit"}
          </button>
        ) : (
          <p className="hint">{noModeReason}</p>
        )}
        <button
          className="button"
          disabled={!running || busy !== null}
          onClick={async () => {
            setBusy("cancel");
            try {
              await onCancel();
            } finally {
              setBusy(null);
            }
          }}
        >
          Cancel
        </button>
        <button
          className="button"
          disabled={running || busy !== null}
          onClick={async () => {
            setBusy("reset");
            try {
              await onReset();
            } finally {
              setBusy(null);
            }
          }}
        >
          Reset
        </button>
      </div>

      <ProgressTracker />

      {isFixtureMode ? (
        <p className="hint">
          The API is in fixture mode, so Start always plays the illustrative fixture audit and the
          banner stays labelled fixture.
        </p>
      ) : null}

      {error ? (
        <div className="inline-error" role="alert">
          <p>{error}</p>
          {state.auditError?.status === 409 ? <p className="small">Already running.</p> : null}
        </div>
      ) : null}

      {state.audit?.status.status === "failed" ? (
        <p className="hint">
          Retry, or switch the mode to fixture/replay. Check MATTERPORT_API_KEY and
          MATTERPORT_API_TOKEN in .env for upstream_auth.
        </p>
      ) : null}
    </section>
  );
}
