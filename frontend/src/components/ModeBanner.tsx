/** Always-visible mode banner (plan 11.3, decision D18).
 * The header shows only what a realtor needs: whether the data is real, sample or recorded, and a plain
 * warning when something is broken. Technical detail (data sources, model calls, calibration, API address)
 * sits in the Details menu. */
import faceBasisJson from "@spatial/face_basis.json";
import { apiBaseLabel, isFixtureMode } from "../api";
import type { IntegrationStatus } from "../contracts";
import { formatIso } from "../format";
import { useAppState } from "../state";
import { ModelCallCounter } from "./ModelCallCounter";

const FACE_BASIS = faceBasisJson as { status?: string };

const SOURCE_NAMES: Record<string, string> = {
  matterport: "3D tour (Matterport)",
  costar: "Building records (CoStar)",
  costar_kit: "Building records (CoStar)",
  vexcel: "Aerial imagery (Vexcel)",
  ebewe: "LA energy benchmark (EBEWE)",
  bedrock: "AI vision",
};

const STATUS_WORDS: Record<string, string> = {
  live: "Connected",
  fixture: "Sample",
  replay: "Recorded",
  unavailable: "Offline",
};

function statusClass(status: IntegrationStatus | undefined): string {
  if (status === "live") return "layer-live";
  if (status === "fixture") return "layer-fixture";
  if (status === "replay") return "layer-replay";
  return "layer-unavailable";
}

export function ModeBanner() {
  const state = useAppState();
  const audit = state.audit;

  let modeLabel: string;
  let modeNote: string | null = null;
  let modeClass: string;
  if (isFixtureMode || audit?.status.mode === "fixture") {
    modeLabel = "Sample data";
    modeNote = "Illustrative fixture — not a real building";
    modeClass = "mode-fixture";
  } else if (audit?.status.mode === "replay") {
    modeLabel = "Recorded demo";
    modeNote = `Replay of a run recorded at ${formatIso(audit.status.replay_of)}`;
    modeClass = "mode-replay";
  } else {
    modeLabel = "Live";
    modeClass = "mode-live";
  }

  const degraded = state.health?.status === "degraded";
  const red = Boolean(state.healthError) || (degraded && !isFixtureMode && modeClass === "mode-live");
  const layers = audit?.building?.layer_status ?? null;
  const health = state.health?.integrations ?? null;
  const sources: Array<[string, IntegrationStatus]> = layers
    ? (Object.entries(layers) as Array<[string, IntegrationStatus]>)
    : health
      ? (Object.entries(health) as Array<[string, IntegrationStatus]>)
      : [];
  const calibrated = (FACE_BASIS.status ?? "unverified") === "calibrated";

  return (
    <div className={`mode-banner ${modeClass} ${red ? "mode-banner-error" : ""}`}>
      <span className={`mode-pill ${modeClass}`}>
        <span className="mode-dot" aria-hidden="true" />
        {modeLabel}
      </span>
      {modeNote ? <span className="mode-note">{modeNote}</span> : null}
      {state.healthError ? (
        <span className="banner-warning" role="alert">
          Can't reach the WattWalk server
        </span>
      ) : degraded && !isFixtureMode && modeClass === "mode-live" ? (
        <span className="banner-warning">Some data sources are offline</span>
      ) : null}
      <span className="banner-spacer" />
      <details className="banner-details">
        <summary>Details</summary>
        <div className="banner-details-panel">
          <h3>Data sources</h3>
          <ul className="source-list" aria-label="Data layer status">
            {sources.length ? (
              sources.map(([key, status]) => (
                <li key={key}>
                  <span>{SOURCE_NAMES[key] ?? key}</span>
                  <span className={`layer-chip ${statusClass(status)}`}>{STATUS_WORDS[status] ?? status}</span>
                </li>
              ))
            ) : (
              <li className="muted">Not checked yet</li>
            )}
          </ul>
          <h3>Audit</h3>
          <dl className="detail-list">
            <div>
              <dt>Status</dt>
              <dd>{audit?.status.status ?? "not started"}</dd>
            </div>
            <div>
              <dt>Pin positions</dt>
              <dd>{calibrated ? "Calibrated" : "Approximate (unverified)"}</dd>
            </div>
            <div>
              <dt>API</dt>
              <dd className="mono">{apiBaseLabel()}</dd>
            </div>
          </dl>
          <ModelCallCounter />
        </div>
      </details>
    </div>
  );
}
