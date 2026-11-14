/** "Today | After upgrades" switch for the heat map, with the apartment-wide saving (what-if preview). */
import { useAppDispatch, useAppState } from "../state";
import { afterTotals } from "../viewer/afterUpgrades";

export function AfterUpgradesSwitch() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const rows = state.energy?.assets ?? [];
  if (rows.length === 0) return null;
  const totals = afterTotals(rows, state.aiAlternatives);
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
          title="Preview: every item with its best upgrade (library and AI ideas)"
          onClick={() => dispatch({ type: "afterUpgrades", on: true })}
        >
          After upgrades
        </button>
      </div>
      {on ? (
        <span className="after-summary">
          −${Math.round(totals.usd).toLocaleString()}/yr · −{Math.round(totals.heat).toLocaleString()} kWh heat
          <span className="muted small"> · {totals.upgraded} items upgraded</span>
        </span>
      ) : null}
    </div>
  );
}
