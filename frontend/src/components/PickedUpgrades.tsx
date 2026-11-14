/** Heat map: one clear button for the upgrades picked so far, opening "Your plan". */
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
      <button
        type="button"
        className="plan-cta"
        onClick={() => setOpen(true)}
        title="Glows marked ✓ show the item with the upgrade you picked"
      >
        <span className="plan-cta-count" aria-hidden="true">{totals.upgraded}</span>
        <span className="plan-cta-text">
          <strong>See your plan</strong>
          <span>Save ${Math.round(totals.usd).toLocaleString()} a year</span>
        </span>
        <span className="plan-cta-arrow" aria-hidden="true">→</span>
      </button>
      {open ? <MyPlan onClose={close} /> : null}
    </>
  );
}
