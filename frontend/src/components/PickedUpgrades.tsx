/** "Your plan" card in the left column: the upgrades picked so far, opening the plan. */
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
      <section className="panel plan-card" aria-labelledby="plan-card-heading">
        <div>
          <h2 id="plan-card-heading">Your plan</h2>
          <p className="muted small">
            {totals.upgraded} upgrade{totals.upgraded === 1 ? "" : "s"} · save ${Math.round(totals.usd).toLocaleString()} a year
          </p>
        </div>
        <button type="button" className="button small" onClick={() => setOpen(true)}>
          View
        </button>
      </section>
      {open ? <MyPlan onClose={close} /> : null}
    </>
  );
}
