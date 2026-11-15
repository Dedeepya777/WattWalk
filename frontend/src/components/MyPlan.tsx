/**
 * "Your plan": every upgrade picked, across all the landlord's apartments, grouped by building, with one
 * total. Prints as a one-page report (Download PDF).
 */
import { useEffect } from "react";
import { useAppDispatch, useAppState, type Pick } from "../state";
import { unitName } from "./ModelPicker";

const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

/**
 * Amazon product for each small library upgrade (the same products the cards link to). Big appliances
 * (fridge, heat pump) and AI ideas are not in the shopping list.
 */
const SHOP_PRODUCTS: Record<string, { name: string; asin: string; per: string }> = {
  window_film: { name: "BDF S2 window film", asin: "B00FRLG65K", per: "window" },
  led: { name: "Philips LED A19 bulb", asin: "B0CVBMQC5R", per: "fixture" },
  smart_thermostat: { name: "Google Nest Thermostat", asin: "B08HRPDYTP", per: "apartment" },
};

/** One line per product with how many to buy (one per item it was picked for). */
function shoppingList(picks: Pick[]) {
  const counts = new Map<string, number>();
  for (const pick of picks) {
    if (SHOP_PRODUCTS[pick.upgradeId]) counts.set(pick.upgradeId, (counts.get(pick.upgradeId) ?? 0) + (pick.units ?? 1));
  }
  return [...counts.entries()].map(([id, quantity]) => ({ ...SHOP_PRODUCTS[id], quantity }));
}

interface Line {
  sid: string;
  /** The items this line covers (the same upgrade on several items of one apartment is one line). */
  assetIds: string[];
  unit: string | null;
  pick: Pick;
  count: number;
  saves: number;
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
    if (!model) continue; // an apartment no longer in the list
    const street = model ? model.address.split(",")[0].trim() : sid;
    const sameBuilding = state.testModels.filter((m) => m.address.split(",")[0].trim() === street).length;
    const unit = model && sameBuilding > 1 ? unitName(model) : null;
    const group = groups.get(street) ?? { street, saves: 0, lines: [] };
    // One line per upgrade per apartment: "Solar control window film · 7 windows".
    const byUpgrade = new Map<string, Line>();
    for (const [assetId, pick] of Object.entries(items)) {
      const amount = pick.saves * (pick.units ?? 1);
      const line = byUpgrade.get(pick.upgradeId);
      if (line) {
        line.assetIds.push(assetId);
        line.count += 1;
        line.saves += amount;
      } else {
        byUpgrade.set(pick.upgradeId, { sid, assetIds: [assetId], unit, pick, count: 1, saves: amount });
      }
      group.saves += amount;
    }
    group.lines.push(...byUpgrade.values());
    groups.set(street, group);
  }
  const ordered = [...groups.values()].sort((a, b) => b.saves - a.saves);
  ordered.forEach((g) => g.lines.sort((a, b) => b.saves - a.saves));
  const lines = ordered.flatMap((g) => g.lines);
  const picks = lines.flatMap((line) => line.assetIds.map((id) => state.picks[line.sid][id]));
  const times = (pick: Pick) => pick.units ?? 1; // a building-wide pick counts for every unit
  const saves = picks.reduce((sum, pick) => sum + pick.saves * times(pick), 0);
  const shopping = shoppingList(picks);
  const cost = picks.reduce((sum, pick) => sum + pick.cost * times(pick), 0);
  // Heat the picked items add to the rooms, before and after (only picks that know their heat).
  const heatBefore = picks.reduce((sum, pick) => sum + (pick.heatBefore ?? 0) * times(pick), 0);
  const heatAfter = picks.reduce((sum, pick) => sum + (pick.heatAfter ?? pick.heatBefore ?? 0) * times(pick), 0);
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
                <li key={`${line.sid}:${line.pick.upgradeId}`}>
                  <div>
                    <span className="pm-title">{line.pick.title}</span>
                    <span className="pm-where">
                      {(line.pick.units
                        ? [`All ${line.pick.units} units`, line.pick.item]
                        : line.count > 1
                          ? [line.unit, `${line.count} ${line.pick.item.toLowerCase()}s`]
                          : [line.unit, line.pick.item, line.pick.room]
                      )
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                  <span className="pm-save">
                    {line.pick.units ? "≈ " : ""}+{money(line.saves)}
                  </span>
                  <button
                    type="button"
                    className="pm-remove"
                    aria-label={`Remove ${line.pick.title}`}
                    title="Remove from the plan"
                    onClick={() =>
                      line.assetIds.forEach((assetId) => dispatch({ type: "removePick", sid: line.sid, assetId }))
                    }
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}

        {shopping.length ? (
          <section className="pm-shop" aria-label="Shopping list">
            <h3>Shopping list</h3>
            <ul>
              {shopping.map((item) => (
                <li key={item.asin}>
                  <span>
                    {item.name} <span className="pm-qty">× {item.quantity}</span>
                  </span>
                  <a href={`https://www.amazon.com/dp/${item.asin}`} target="_blank" rel="noopener noreferrer">
                    Buy on Amazon ↗
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  );
}
