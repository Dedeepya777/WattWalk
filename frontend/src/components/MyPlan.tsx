/**
 * "Your plan": every upgrade picked across the landlord's apartments, once per upgrade (what to do and
 * buy), with the buildings it covers underneath. Prints as a clean one-page report (Download PDF).
 */
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useAppDispatch, useAppState, type Pick } from "../state";
import { unitName } from "./ModelPicker";

const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

/** Amazon product for each small library upgrade (the same products the cards link to). */
const SHOP_PRODUCTS: Record<string, string> = {
  window_film: "B00FRLG65K", // BDF S2 window film, one per window
  led: "B0CVBMQC5R", // Philips Ultra Efficient LED A19, one per light fixture
  smart_thermostat: "B08HRPDYTP", // Google Nest Thermostat, one per apartment
};

interface Place {
  street: string;
  saves: number;
  count: number;
  /** Items per apartment ("Studio - 662SF" -> 3); empty for a building with one apartment. */
  apartments: Map<string, number>;
  refs: { sid: string; assetId: string }[];
}

interface Action {
  upgradeId: string;
  title: string;
  item: string;
  saves: number;
  count: number;
  places: Place[];
}

const plural = (n: number, word: string) => `${n} ${word.toLowerCase()}${n === 1 ? "" : "s"}`;

export function MyPlan({ onClose }: { onClose: () => void }) {
  const state = useAppState();
  const dispatch = useAppDispatch();

  // One entry per upgrade (what to do), with the buildings it covers; biggest saving first.
  const actions = new Map<string, Action>();
  const picks: Pick[] = [];
  for (const [sid, items] of Object.entries(state.picks)) {
    const model = state.testModels.find((m) => m.sid === sid);
    if (!model) continue; // an apartment no longer in the list
    const street = model.address.split(",")[0].trim();
    const sameBuilding = state.testModels.filter((m) => m.address.split(",")[0].trim() === street).length;
    for (const [assetId, pick] of Object.entries(items)) {
      const amount = pick.saves * (pick.units ?? 1);
      const quantity = pick.units ?? 1;
      picks.push(pick);
      const action = actions.get(pick.upgradeId) ?? {
        upgradeId: pick.upgradeId, title: pick.title, item: pick.item, saves: 0, count: 0, places: [],
      };
      action.saves += amount;
      action.count += quantity;
      let place = action.places.find((p) => p.street === street);
      if (!place) {
        place = { street, saves: 0, count: 0, apartments: new Map(), refs: [] };
        action.places.push(place);
      }
      place.saves += amount;
      place.count += quantity;
      place.refs.push({ sid, assetId });
      if (sameBuilding > 1) {
        const name = unitName(model);
        place.apartments.set(name, (place.apartments.get(name) ?? 0) + quantity);
      }
      actions.set(pick.upgradeId, action);
    }
  }
  const ordered = [...actions.values()].sort((a, b) => b.saves - a.saves);
  ordered.forEach((a) => a.places.sort((x, y) => y.saves - x.saves));

  const times = (pick: Pick) => pick.units ?? 1;
  const saves = picks.reduce((sum, pick) => sum + pick.saves * times(pick), 0);
  const cost = picks.reduce((sum, pick) => sum + pick.cost * times(pick), 0);
  const heatBefore = picks.reduce((sum, pick) => sum + (pick.heatBefore ?? 0) * times(pick), 0);
  const heatAfter = picks.reduce((sum, pick) => sum + (pick.heatAfter ?? pick.heatBefore ?? 0) * times(pick), 0);
  const heatCut = heatBefore > 0 ? Math.round(((heatBefore - heatAfter) / heatBefore) * 100) : 0;
  const today = new Date().toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (picks.length === 0) onClose();
  }, [picks.length, onClose]);

  // Printing: only the plan goes on paper (the app is taken out of the page while printing).
  const print = () => {
    document.body.classList.add("printing-plan");
    const done = () => {
      document.body.classList.remove("printing-plan");
      window.removeEventListener("afterprint", done);
    };
    window.addEventListener("afterprint", done);
    window.print();
  };

  // Rendered outside the app so the printed page holds just the plan, once.
  return createPortal(
    <div className="modal-backdrop my-plan-backdrop" role="presentation" onClick={onClose}>
      <div
        className="my-plan plan-min"
        role="dialog"
        aria-modal="true"
        aria-labelledby="my-plan-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="my-plan-top">
          <span className="my-plan-place">
            <span className="pm-brand">WattWalk</span> upgrade plan · {today}
          </span>
          <div className="my-plan-actions">
            <button type="button" className="button primary" onClick={print}>
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

        {ordered.map((action) => {
          const asin = SHOP_PRODUCTS[action.upgradeId];
          return (
            <section key={action.upgradeId} className="pm-action">
              <div className="pm-action-head">
                <div>
                  <h3>{action.title}</h3>
                  <span className="pm-where">{plural(action.count, action.item)}</span>
                </div>
                <span className="pm-save">{money(action.saves)} a year</span>
                {asin ? (
                  <a
                    className="pm-buy"
                    href={`https://www.amazon.com/dp/${asin}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`Buy ${action.count} on Amazon (set the quantity there)`}
                  >
                    Buy {action.count} ↗
                  </a>
                ) : (
                  <span />
                )}
              </div>
              <ul>
                {action.places.map((place) => (
                  <li key={place.street}>
                    <span className="pm-place">
                      {place.street}
                      <span className="pm-where">
                        {place.apartments.size
                          ? [...place.apartments.entries()].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(" · ")
                          : plural(place.count, action.item)}
                      </span>
                    </span>
                    <span className="pm-place-save">{money(place.saves)}</span>
                    <button
                      type="button"
                      className="pm-remove"
                      aria-label={`Remove ${action.title} in ${place.street}`}
                      title="Remove from the plan"
                      onClick={() =>
                        place.refs.forEach((ref) => dispatch({ type: "removePick", sid: ref.sid, assetId: ref.assetId }))
                      }
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}

        <button
          type="button"
          className="pm-clear"
          onClick={() => {
            if (window.confirm("Remove all upgrades from every building?")) dispatch({ type: "clearPicks" });
          }}
        >
          Clear plan
        </button>
      </div>
    </div>,
    document.body,
  );
}
