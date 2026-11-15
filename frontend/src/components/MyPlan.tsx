/**
 * "My upgrade plan": every upgrade picked in the heat map cards, with cost, saving and payback, and the
 * totals. Prints as a one-page report (Print / Save as PDF) a renter can hand to the landlord.
 */
import { useEffect } from "react";
import { formatRange } from "../format";
import { useAppDispatch, useAppState } from "../state";
import { afterTotals } from "../viewer/afterUpgrades";
import { planLines, planTotals } from "../viewer/planMath";
import { formatPayback } from "./EnergyAlternatives";

export function MyPlan({ onClose }: { onClose: () => void }) {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const rooms = new Map((state.audit?.rooms ?? []).map((room) => [room.id, room.label]));
  const lines = planLines(
    state.energy?.assets ?? [],
    state.aiAlternatives,
    state.chosenUpgrades,
    (id) => (id ? rooms.get(id) ?? "" : ""),
  );
  const totals = planTotals(lines);
  const address = state.testModels.find((model) => model.sid === state.selectedSid)?.address ?? state.selectedSid ?? "";
  const anyAi = lines.some((line) => line.ai);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (lines.length === 0) onClose();
  }, [lines.length, onClose]);

  const heat = afterTotals(state.energy?.assets ?? [], state.aiAlternatives, state.chosenUpgrades).heat;
  const count = lines.length;

  return (
    <div className="modal-backdrop my-plan-backdrop" role="presentation" onClick={onClose}>
      <div
        className="my-plan"
        role="dialog"
        aria-modal="true"
        aria-labelledby="my-plan-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="my-plan-top">
          <span className="my-plan-place">{address}</span>
          <div className="my-plan-actions">
            <button type="button" className="button primary" onClick={() => window.print()}>
              Download PDF
            </button>
            <button type="button" className="button" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </div>

        <header className="my-plan-hero">
          <p className="my-plan-kicker">Your plan</p>
          <h2 id="my-plan-title">
            Save <span className="my-plan-money">{formatRange(totals.saves, "", true)}</span> a year
          </h2>
          <dl className="my-plan-stats">
            <div>
              <dt>To install</dt>
              <dd>{formatRange(totals.cost, "", true)}</dd>
            </div>
            <div>
              <dt>Pays for itself in</dt>
              <dd>{totals.payback ? formatPayback(totals.payback) : "–"}</dd>
            </div>
            {heat > 0 ? (
              <div>
                <dt>Less heat a year</dt>
                <dd>{Math.round(heat).toLocaleString()} kWh</dd>
              </div>
            ) : null}
          </dl>
        </header>

        <h3 className="my-plan-steps-title">
          {count === 1 ? "1 upgrade" : `${count} upgrades`}, biggest saving first
        </h3>
        <ol className="my-plan-steps">
          {lines.map((line, index) => {
            const free = line.alt.cost_usd[1] <= 0;
            return (
              <li key={line.assetId} className="my-plan-step">
                <span className="my-plan-num" aria-hidden="true">{index + 1}</span>
                <div className="my-plan-step-body">
                  <div className="my-plan-step-title">
                    {line.alt.title}
                    {line.ai ? <span className="my-plan-ai">estimate</span> : null}
                  </div>
                  <div className="my-plan-step-sub">
                    {line.item}
                    {line.room ? `, ${line.room}` : ""} ·{" "}
                    {free
                      ? "free"
                      : `${formatRange(line.alt.cost_usd, "", true)}, pays back in ${formatPayback(line.alt.payback_years)}`}
                  </div>
                </div>
                <span className="my-plan-step-save">
                  +{formatRange(line.alt.saves_usd_yr, "", true)}
                  <small>/yr</small>
                </span>
                <button
                  type="button"
                  className="my-plan-remove"
                  aria-label={`Remove ${line.alt.title}`}
                  title="Remove from the plan"
                  onClick={() => dispatch({ type: "chooseUpgrade", assetId: line.assetId, upgradeId: null })}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ol>

        <p className="my-plan-note">
          Estimates from the apartment scan.{anyAi ? " AI ideas are rough guesses." : ""}
        </p>
      </div>
    </div>
  );
}
