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

const STATUS_TEXT: Record<string, string> = {
  idle: "Not started",
  running: "Running",
  completed: "Done",
  failed: "Failed",
  cancelled: "Stopped",
};

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
  const [showOptions, setShowOptions] = useState(false);
  const [liveFailed, setLiveFailed] = useState(false);
  const [probe, setProbe] = useState<Health | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const lastProbeRef = useRef(0);
  const probingRef = useRef(false);

  const model = state.testModels.find((item) => item.sid === state.selectedSid);

  const probeLive = async (force = false): Promise<Health | null> => {
    if (probingRef.current) return null;
    if (!force && Date.now() - lastProbeRef.current < 60_000) return probe;
    probingRef.current = true;
    setProbing(true);
    setProbeError(null);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 25_000);
    try {
      const result = await getHealthProbe(controller.signal);
      setProbe(result);
      lastProbeRef.current = Date.now();
      return result;
    } catch (error) {
      setProbeError(
        error instanceof ApiFailure
          ? error.message
          : "Could not check the live integrations.",
      );
      return null;
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

  const status = state.audit?.status.status ?? "idle";
  const done = status === "completed";
  const MODE_LABEL: Record<Mode, string> = { live: "Live", replay: "Replay", fixture: "Demo data" };
  const MODE_TITLE: Record<Mode, string> = {
    live: liveReady
      ? degraded.length
        ? `Live scan and AI. Running with less detail: ${degraded.join(", ")} unavailable.`
        : "Live scan and AI"
      : liveReason ?? "Live needs Matterport and the AI model",
    replay: available.replay ? "Replay a recorded audit (instant)" : "This apartment has no recording",
    fixture: available.fixture ? "Illustrative demo data (instant)" : "This apartment has no demo data",
  };
  const start = async () => {
    setBusy("start");
    try {
      await onStart(mode);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel audit-panel" aria-labelledby="run-heading">
      <div className="panel-heading">
        <h2 id="run-heading">Audit</h2>
        <span className={`status-dot status-${status}`}>{STATUS_TEXT[status] ?? status}</span>
      </div>

      {running ? (
        <button
          className="button audit-main"
          disabled={busy !== null}
          onClick={async () => {
            setBusy("cancel");
            try {
              await onCancel();
            } finally {
              setBusy(null);
            }
          }}
        >
          {busy === "cancel" ? <span className="spinner" aria-hidden="true" /> : null}
          Stop audit
        </button>
      ) : anyAvailable ? (
        <button className="button primary audit-main" onClick={() => void start()} disabled={startDisabled}>
          {busy === "start" || auditLoading ? <span className="spinner" aria-hidden="true" /> : null}
          {auditLoading
            ? "Checking apartment…"
            : busy === "start"
              ? "Starting…"
              : done
                ? "Run audit again"
                : "Start audit"}
        </button>
      ) : (
        // Live-only apartment: check the live services, then start a live audit straight away.
        <button
          className="button primary audit-main"
          disabled={probing || busy !== null || auditLoading || Boolean(otherRunSid)}
          onClick={async () => {
            setLiveFailed(false);
            const health = await probeLive(true);
            const ok = health?.integrations.matterport === "live" && health?.integrations.bedrock === "live";
            if (!ok) {
              setLiveFailed(true);
              return;
            }
            setMode("live");
            setBusy("start");
            try {
              await onStart("live");
            } finally {
              setBusy(null);
            }
          }}
        >
          {probing || busy === "start" ? <span className="spinner" aria-hidden="true" /> : null}
          {probing ? "Connecting\u2026" : busy === "start" ? "Starting\u2026" : done ? "Run audit again" : "Start audit"}
        </button>
      )}
      {liveFailed && !anyAvailable ? (
        <p className="hint small audit-note" title={liveReason ?? undefined}>
          Live services aren’t ready. Pick an Instant demo apartment.
        </p>
      ) : null}

      <ProgressTracker />

      {!running ? (
        <button
          type="button"
          className="audit-link audit-options-toggle"
          aria-expanded={showOptions}
          onClick={() => setShowOptions((open) => !open)}
        >
          {showOptions ? "Hide options" : "Options"}
        </button>
      ) : null}

      {showOptions && !running ? (
      <div className="audit-extras">
        <div
          className="segmented audit-mode"
          role="group"
          aria-label="Audit source"
          onFocus={() => void probeLive()}
          onMouseDown={() => void probeLive()}
        >
          {(["live", "replay", "fixture"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              className={mode === m ? "segmented-button active" : "segmented-button"}
              aria-pressed={mode === m}
              disabled={!available[m] || running || busy !== null}
              title={MODE_TITLE[m]}
              onClick={() => setMode(m)}
            >
              {m === "live" && probing ? <span className="spinner" aria-hidden="true" /> : null}
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>
        {!liveReady && !probing ? (
          <button
            className="audit-link"
            title={liveReason ?? undefined}
            onClick={() => void probeLive(true)}
          >
            Enable live
          </button>
        ) : null}
        {!running && state.audit && status !== "idle" ? (
          <button
            className="audit-link"
            disabled={busy !== null}
            title="Clear this apartment's results"
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
        ) : null}
      </div>
      ) : null}

      {probeError && showOptions ? <p className="hint small">{liveReason}</p> : null}

      {otherRunSid ? (
        <p className="hint small">Another apartment is still being audited. Stop it or wait first.</p>
      ) : null}

      {error ? (
        <div className="inline-error" role="alert">
          <p>{error}</p>
          {state.auditError?.status === 409 ? <p className="small">Already running.</p> : null}
        </div>
      ) : null}

      {status === "failed" ? (
        <p className="hint small">
          Try again, or pick Replay or Demo data. If it says upstream_auth, check MATTERPORT_API_KEY and
          MATTERPORT_API_TOKEN in .env.
        </p>
      ) : null}
    </section>
  );
}
