/** Audit progress bar under the Start / Cancel controls; the maths lives in progress.ts. */
import { useEffect, useState } from "react";
import { useAppState } from "../state";
import { computeProgress } from "./progress";

function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m} min ${s.toString().padStart(2, "0")} s` : `${s} s`;
}

export function ProgressTracker() {
  const state = useAppState();
  const status = state.audit?.status.status;
  const running = status === "running";
  const progress = computeProgress(state.events);

  // Tick once a second so "elapsed" moves between events.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  // Only while an audit runs: once it is done, the status next to the apartment's name says so.
  if (!running) return null;

  const startedAt = state.audit?.status.started_at ? Date.parse(state.audit.status.started_at) : NaN;
  const elapsed = running && Number.isFinite(startedAt)
    ? Math.max(progress.elapsedS, Math.round((Date.now() - startedAt) / 1000))
    : progress.elapsedS;

  return (
    <div className="progress" role="group" aria-label="Audit progress">
      <div className="progress-head">
        <strong>{progress.stage}</strong>
        <span>{progress.percent}%</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress.percent}
        aria-valuetext={`${progress.percent}% \u2013 ${progress.stage}`}
      >
        <div
          className={running ? "progress-fill running" : "progress-fill"}
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <div className="progress-meta muted small">
        <span>{progress.detail}</span>
        <span>
          {clock(elapsed)} elapsed
          {running && progress.etaS !== null
            ? ` \u00b7 about ${clock(progress.etaS)} left in this stage`
            : running && progress.estimating
              ? " \u00b7 estimating time left\u2026"
              : ""}
        </span>
      </div>
    </div>
  );
}
