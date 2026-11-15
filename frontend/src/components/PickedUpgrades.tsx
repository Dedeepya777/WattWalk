/** "Your plan" card in the left column: upgrades picked across all apartments, opening the plan. */
import { useCallback, useState } from "react";
import { useAppState } from "../state";
import { MyPlan } from "./MyPlan";

export function PickedUpgrades() {
  const state = useAppState();
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const picks = Object.values(state.picks).flatMap((items) => Object.values(items));
  if (picks.length === 0) return null;
  const saves = picks.reduce((sum, pick) => sum + pick.saves * (pick.units ?? 1), 0);
  return (
    <>
      <section className="panel plan-card" aria-labelledby="plan-card-heading">
        <div>
          <h2 id="plan-card-heading">Your plan</h2>
          <p className="muted small">Save ${Math.round(saves).toLocaleString()} a year</p>
        </div>
        <button type="button" className="button small" onClick={() => setOpen(true)}>
          View
        </button>
      </section>
      {open ? <MyPlan onClose={close} /> : null}
    </>
  );
}
