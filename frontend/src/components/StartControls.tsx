/** Start / Cancel / Reset controls and mode selector (plan 11.3). */
import { useEffect, useState } from "react";
import { isFixtureMode } from "../api";
import type { StartAuditRequest } from "../contracts";
import { FIXTURE_SID } from "../fixtures";
import { useAppState } from "../state";
import { ProgressTracker } from "./ProgressTracker";

type Mode = StartAuditRequest["mode"];

interface Props {
  onStart: (mode: Mode) => Promise<void>;
  onCancel: () => Promise<void>;
  onReset: () => Promise<void>;
}

export function StartControls({ onStart, onCancel, onReset }: Props) {
  const state = useAppState();
  const running = state.audit?.status.status === "running";
  const [mode, setMode] = useState<Mode>(isFixtureMode ? "fixture" : "live");
  const [busy, setBusy] = useState<null | "start" | "cancel" | "reset">(null);

  const model = state.testModels.find((item) => item.sid === state.selectedSid);
  const available: Record<Mode, boolean> = {
    live: true,
    replay: Boolean(model?.has_replay),
    fixture:
      Boolean(model?.has_fixture) || (isFixtureMode && state.selectedSid === FIXTURE_SID),
  };

  useEffect(() => {
    if (!available[mode]) {
      if (available.fixture) setMode("fixture");
      else if (available.replay) setMode("replay");
      else setMode("live");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, model?.has_fixture, model?.has_replay, state.selectedSid]);

  const startDisabled = running || busy !== null || !available[mode] || state.selectedSid === "";
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

      <label className="field">
        <span>Mode</span>
        <select
          value={mode}
          onChange={(event) => setMode(event.target.value as Mode)}
          disabled={running || busy !== null}
        >
          <option value="live">live</option>
          <option value="replay" disabled={!available.replay}>
            replay{available.replay ? "" : " (no recording)"}
          </option>
          <option value="fixture" disabled={!available.fixture}>
            fixture{available.fixture ? "" : " (no fixture)"}
          </option>
        </select>
      </label>

      <div className="button-row">
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
          {busy === "start" ? <span className="spinner" aria-hidden="true" /> : null}
          {busy === "start" ? "Starting…" : "Start audit"}
        </button>
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
          The API is in fixture mode, so Start always plays the illustrative fixture
          audit and the banner stays labelled fixture.
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
