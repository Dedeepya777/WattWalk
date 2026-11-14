/** "Today | After upgrades" switch for the heat map, with the apartment-wide saving (what-if preview). */
import { useAppDispatch, useAppState } from "../state";
import { afterTotals } from "../viewer/afterUpgrades";

export function AfterUpgradesSwitch() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const rows = state.energy?.assets ?? [];
  if (rows.length === 0) return null;
  const totals = afterTotals(rows, state.aiAlternatives, state.chosenUpgrades);
  const on = state.afterUpgrades;
  return (
    <div className="after-switch">
      <div className="segmented" role="group" aria-label="Heat map: today or after upgrades">
        <button
          type="button"
          className={on ? "segmented-button" : "segmented-button active"}
          aria-pressed={!on}
          onClick={() => dispatch({ type: "afterUpgrades", on: false })}
        >
          Today
        </button>
        <button
          type="button"
          className={on ? "segmented-button active" : "segmented-button"}
          aria-pressed={on}
          disabled={totals.upgraded === 0}
          title={
            totals.upgraded === 0
              ? "Click a glow or pin and pick an upgrade in its card first"
              : "Preview the apartment with the upgrades you picked"
          }
          onClick={() => dispatch({ type: "afterUpgrades", on: true })}
        >
          After upgrades
        </button>
      </div>
      {totals.upgraded === 0 ? (
        <span className="muted small">Pick upgrades in an item's card to preview them</span>
      ) : (
        <span className={on ? "after-summary" : "after-summary after-summary-idle"}>
          {totals.upgraded} picked · −${Math.round(totals.usd).toLocaleString()}/yr
          {totals.heat > 0 ? ` · −${Math.round(totals.heat).toLocaleString()} kWh heat` : ""}
          <span className="muted small"> · costs ~${Math.round(totals.cost).toLocaleString()}</span>
        </span>
      )}
    </div>
  );
}
