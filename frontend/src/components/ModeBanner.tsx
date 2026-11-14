/** Always-visible mode banner (plan 11.3, decision D18). */
import faceBasisJson from "@spatial/face_basis.json";
import { apiBaseLabel, isFixtureMode } from "../api";
import type { IntegrationStatus } from "../contracts";
import { formatIso } from "../format";
import { useAppState } from "../state";

const FACE_BASIS = faceBasisJson as { status?: string };

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
  let modeClass: string;
  if (isFixtureMode) {
    modeLabel = "Illustrative fixture — not a real building";
    modeClass = "mode-fixture";
  } else if (audit?.status.mode === "replay") {
    modeLabel = `Replay of a run recorded at ${formatIso(audit.status.replay_of)}`;
    modeClass = "mode-replay";
  } else if (audit?.status.mode === "fixture") {
    modeLabel = "Illustrative fixture — not a real building";
    modeClass = "mode-fixture";
  } else {
    modeLabel = "Live";
    modeClass = "mode-live";
  }

  const degraded = state.health?.status === "degraded";
  const red = Boolean(state.healthError) || (degraded && !isFixtureMode && modeClass === "mode-live");
  const layers = audit?.building?.layer_status ?? null;
  const health = state.health?.integrations ?? null;
  const calibrationUnverified = (FACE_BASIS.status ?? "unverified") !== "calibrated";

  return (
    <div className={`mode-banner ${modeClass} ${red ? "mode-banner-error" : ""}`}>
      <span className={`mode-pill ${modeClass}`}>{modeLabel}</span>
      {state.audit?.status.status ? (
        <span className="muted small">Audit: {state.audit.status.status}</span>
      ) : null}
      <span className="banner-sep" aria-hidden="true" />
      <span className="layer-list" aria-label="Data layer status">
        {layers
          ? (Object.keys(layers) as Array<keyof typeof layers>).map((key) => (
              <span key={key} className={`layer-chip ${statusClass(layers[key])}`}>
                {key}: {layers[key]}
              </span>
            ))
          : health
            ? (Object.keys(health) as Array<keyof typeof health>).map((key) => (
                <span key={key} className={`layer-chip ${statusClass(health[key])}`}>
                  {key.replace("_kit", "")}: {health[key]}
                </span>
              ))
            : null}
      </span>
      {calibrationUnverified ? (
        <span className="banner-warning" title="face_basis.json status is unverified; pins are labelled approximate">
          Pin positions unverified
        </span>
      ) : null}
      {state.healthError ? (
        <span className="banner-warning" role="alert">
          API unreachable
        </span>
      ) : degraded && !isFixtureMode ? (
        <span className="banner-warning">Health degraded</span>
      ) : null}
      <span className="banner-spacer" />
      <span className="banner-source" title="Configured API base">
        API: {apiBaseLabel()}
      </span>
    </div>
  );
}
