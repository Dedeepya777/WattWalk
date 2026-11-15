/**
 * "Your plan": every upgrade picked, across all the landlord's apartments, grouped by building, with one
 * total. Prints as a one-page report (Download PDF).
 */
import { useEffect } from "react";
import { useAppDispatch, useAppState, type Pick } from "../state";
import { unitName } from "./ModelPicker";

const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

interface Line {
  sid: string;
  assetId: string;
  unit: string | null;
  pick: Pick;
}

interface Group {
  street: string;
  saves: number;
  lines: Line[];
}

export function MyPlan({ onClose }: { onClose: () => void }) {
  const state = useAppState();
  const dispatch = useAppDispatch();

  // Group every pick by building (street), then by apartment; biggest saving first.
  const groups = new Map<string, Group>();
  for (const [sid, items] of Object.entries(state.picks)) {
    const model = state.testModels.find((m) => m.sid === sid);
    const street = model ? model.address.split(",")[0].trim() : sid;
    const sameBuilding = state.testModels.filter((m) => m.address.split(",")[0].trim() === street).length;
    const unit = model && sameBuilding > 1 ? unitName(model) : null;
    const group = groups.get(street) ?? { street, saves: 0, lines: [] };
    for (const [assetId, pick] of Object.entries(items)) {
      group.lines.push({ sid, assetId, unit, pick });
      group.saves += pick.saves;
    }
    groups.set(street, group);
  }
  const ordered = [...groups.values()].sort((a, b) => b.saves - a.saves);
  ordered.forEach((g) => g.lines.sort((a, b) => b.pick.saves - a.pick.saves));
  const lines = ordered.flatMap((g) => g.lines);
  const saves = lines.reduce((sum, l) => sum + l.pick.saves, 0);
  const cost = lines.reduce((sum, l) => sum + l.pick.cost, 0);
  // Heat the picked items add to the rooms, before and after (only picks that know their heat).
  const heatBefore = lines.reduce((sum, l) => sum + (l.pick.heatBefore ?? 0), 0);
  const heatAfter = lines.reduce((sum, l) => sum + (l.pick.heatAfter ?? l.pick.heatBefore ?? 0), 0);
  const heatCut = heatBefore > 0 ? Math.round(((heatBefore - heatAfter) / heatBefore) * 100) : 0;

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
        className="my-plan plan-min"
        role="dialog"
        aria-modal="true"
        aria-labelledby="my-plan-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="my-plan-top">
          <span className="my-plan-place">Your plan</span>
          <div className="my-plan-actions">
            <button type="button" className="button primary" onClick={() => window.print()}>
              Download PDF
            </button>
            <button type="button" className="button" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </div>

        <header className="pm-hero">
          <h2 id="my-plan-title" className="sr-only">
            Save {money(saves)} a year{heatCut > 0 ? `, ${heatCut}% less heat` : ""}
          </h2>
          <div className="pm-stats" aria-hidden="true">
            <div>
              <span className="pm-stat pm-stat-money">{money(saves)}</span>
              <span className="pm-stat-label">saved a year</span>
            </div>
            {heatCut > 0 ? (
              <div>
                <span className="pm-stat pm-stat-heat">{heatCut}%</span>
                <span className="pm-stat-label">less heat in these rooms</span>
              </div>
            ) : null}
          </div>
          {cost > 0 ? <p>about {money(cost)} to install</p> : null}
        </header>

        {ordered.map((group) => (
          <section key={group.street} className="pm-building">
            <div className="pm-building-head">
              <h3>{group.street}</h3>
              <span>{money(group.saves)} a year</span>
            </div>
            <ul>
              {group.lines.map((line) => (
                <li key={`${line.sid}:${line.assetId}`}>
                  <div>
                    <span className="pm-title">{line.pick.title}</span>
                    <span className="pm-where">
                      {[line.unit, line.pick.item, line.pick.room].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                  <span className="pm-save">+{money(line.pick.saves)}</span>
                  <button
                    type="button"
                    className="pm-remove"
                    aria-label={`Remove ${line.pick.title}`}
                    title="Remove from the plan"
                    onClick={() => dispatch({ type: "removePick", sid: line.sid, assetId: line.assetId })}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
