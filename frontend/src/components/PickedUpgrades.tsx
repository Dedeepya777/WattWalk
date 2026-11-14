/** Heat map indicator: how many upgrades are picked and what they save together, with a link to the plan. */
import { useCallback, useState } from "react";
import { useAppState } from "../state";
import { afterTotals } from "../viewer/afterUpgrades";
import { MyPlan } from "./MyPlan";

export function PickedUpgrades() {
  const state = useAppState();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const totals = afterTotals(state.energy?.assets ?? [], state.aiAlternatives, state.chosenUpgrades);
  if (totals.upgraded === 0) return null;
  return (
    <>
      <span className="picked-upgrades" role="status" title="Glows marked ✓ show the item with the upgrade you picked">
        <span className="picked-dot" aria-hidden="true">✓</span>
        {totals.upgraded} upgrade{totals.upgraded === 1 ? "" : "s"} shown · −${Math.round(totals.usd).toLocaleString()}/yr
        {totals.heat > 0 ? ` · −${Math.round(totals.heat).toLocaleString()} kWh heat` : ""}
        <span className="muted small"> · costs ~${Math.round(totals.cost).toLocaleString()}</span>
      </span>
      <button type="button" className="button small primary picked-plan-button" onClick={() => setOpen(true)}>
        My plan →
      </button>
      {open ? <MyPlan onClose={close} /> : null}
    </>
  );
}
