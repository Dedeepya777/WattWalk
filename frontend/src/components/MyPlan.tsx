/**
 * "My upgrade plan": every upgrade picked in the heat map cards, with cost, saving and payback, and the
 * totals. Prints as a one-page report (Print / Save as PDF) a renter can hand to the landlord.
 */
import { useEffect } from "react";
import { formatRange } from "../format";
import { useAppDispatch, useAppState } from "../state";
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

  return (
    <div className="modal-backdrop my-plan-backdrop" role="presentation" onClick={onClose}>
      <div
        className="my-plan"
        role="dialog"
        aria-modal="true"
        aria-labelledby="my-plan-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="my-plan-head">
          <div>
            <p className="my-plan-kicker">WattWalk · upgrade plan</p>
            <h2 id="my-plan-title">{address}</h2>
            <p className="my-plan-date">{new Date().toLocaleDateString(undefined, { dateStyle: "long" })}</p>
          </div>
          <div className="my-plan-actions">
            <button type="button" className="button primary" onClick={() => window.print()}>
              Print / Save as PDF
            </button>
            <button type="button" className="button" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </header>

        <section className="my-plan-totals" aria-label="Plan totals">
          <div>
            <span className="my-plan-big">{formatRange(totals.saves, "", true)}</span>
            <span className="my-plan-unit">saved per year</span>
          </div>
          <div>
            <span className="my-plan-big">{formatRange(totals.cost, "", true)}</span>
            <span className="my-plan-unit">to install</span>
          </div>
          <div>
            <span className="my-plan-big">{totals.payback ? formatPayback(totals.payback) : "–"}</span>
            <span className="my-plan-unit">to pay back</span>
          </div>
        </section>

        <table className="my-plan-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Upgrade</th>
              <th className="num">Saves / yr</th>
              <th className="num">Cost</th>
              <th className="num">Pays back</th>
              <th className="my-plan-remove-col" aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const free = line.alt.cost_usd[1] <= 0;
              return (
                <tr key={line.assetId}>
                  <td>
                    <strong>{line.item}</strong>
                    {line.room ? <span className="my-plan-room">{line.room}</span> : null}
                  </td>
                  <td>
                    {line.alt.title}
                    {line.ai ? <span className="my-plan-ai">AI estimate</span> : null}
                    <span className="my-plan-who">{line.alt.who}</span>
                  </td>
                  <td className="num my-plan-save">{formatRange(line.alt.saves_usd_yr, "", true)}</td>
                  <td className="num">{free ? "Free" : formatRange(line.alt.cost_usd, "", true)}</td>
                  <td className="num">{free ? "Now" : formatPayback(line.alt.payback_years)}</td>
                  <td className="my-plan-remove-col">
                    <button
                      type="button"
                      className="my-plan-remove"
                      aria-label={`Remove ${line.alt.title}`}
                      title="Remove from the plan"
                      onClick={() => dispatch({ type: "chooseUpgrade", assetId: line.assetId, upgradeId: null })}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <p className="my-plan-note">
          Ranges are estimates from the apartment scan and published assumptions; prices are typical installed
          costs.{anyAi ? " Lines marked AI estimate are rough suggestions from an AI model, not sourced." : ""}
        </p>
      </div>
    </div>
  );
}
