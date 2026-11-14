/**
 * "After upgrades" what-if: each item with the upgrade the user picked in its card (library or AI
 * idea), so the heat map can show the apartment as it would be. Pure functions, shared by the 3D glows
 * and the totals.
 */
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";

type Range = [number, number];

const mid = (r: Range | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);

/** All ideas for an item: the upgrade library's plus any AI ideas fetched for it. */
export function allAlternatives(row: AssetEnergy, ai?: AiAlternativesResponse): EnergyAlternative[] {
  return [...row.alternatives, ...(ai?.alternatives ?? [])];
}

/** The upgrade picked for this item, or null when none is picked (or it no longer exists). */
export function chosenAlternative(row: AssetEnergy, ai: AiAlternativesResponse | undefined, upgradeId: string | undefined) {
  if (!upgradeId) return null;
  return allAlternatives(row, ai).find((alt) => alt.upgrade_id === upgradeId) ?? null;
}

/**
 * The item after an upgrade. Heat follows the upgrade's own after-heat when it has one; otherwise heat
 * added to the room shrinks in proportion to the electricity saved (a unit that removes heat keeps its
 * value). With no upgrade, or an item without an estimate, the row is returned unchanged.
 */
export function afterRow(row: AssetEnergy, alt: EnergyAlternative | null): AssetEnergy {
  if (!alt || !row.estimated) return row;
  const kwh = alt.kwh_yr ?? row.kwh_yr;
  const usd = alt.usd_yr ?? (row.usd_yr ? ([
    Math.max(0, row.usd_yr[0] - alt.saves_usd_yr[1]),
    Math.max(0, row.usd_yr[1] - alt.saves_usd_yr[0]),
  ] as Range) : null);
  let heat = alt.heat_kwh_yr ?? row.heat_kwh_yr;
  if (!alt.heat_kwh_yr && row.heat_kwh_yr && row.heat_kwh_yr[0] >= 0 && row.kwh_yr && alt.kwh_yr) {
    const share = mid(alt.kwh_yr) / Math.max(1e-9, mid(row.kwh_yr));
    heat = [row.heat_kwh_yr[0] * share, row.heat_kwh_yr[1] * share];
  }
  return { ...row, kwh_yr: kwh, usd_yr: usd, heat_kwh_yr: heat, power_w: alt.power_w ?? row.power_w };
}

/** Yearly money and heat saved by the picked upgrades, plus their total cost (midpoints). */
export function afterTotals(
  rows: AssetEnergy[],
  ai: Record<string, AiAlternativesResponse>,
  chosen: Record<string, string>,
) {
  let usd = 0;
  let heat = 0;
  let cost = 0;
  let upgraded = 0;
  for (const row of rows) {
    const alt = chosenAlternative(row, ai[row.asset_id], chosen[row.asset_id]);
    if (!alt) continue;
    upgraded += 1;
    usd += mid(alt.saves_usd_yr);
    cost += mid(alt.cost_usd);
    const before = mid(row.heat_kwh_yr);
    const after = mid(afterRow(row, alt).heat_kwh_yr);
    if (before > 0) heat += Math.max(0, before - after);
  }
  return { usd, heat, cost, upgraded };
}
