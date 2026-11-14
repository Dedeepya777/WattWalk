/**
 * "After upgrades" what-if: each item with its single best upgrade applied (library and AI ideas),
 * so the heat map can show the apartment as it would be. Pure functions, shared by the 3D glows and
 * the totals.
 */
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";

type Range = [number, number];

const mid = (r: Range | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);

/** All ideas for an item: the upgrade library's plus any AI ideas fetched for it. */
export function allAlternatives(row: AssetEnergy, ai?: AiAlternativesResponse): EnergyAlternative[] {
  return [...row.alternatives, ...(ai?.alternatives ?? [])];
}

/** The one upgrade that saves the most money per year (midpoint), or null when none saves anything. */
export function bestAlternative(row: AssetEnergy, ai?: AiAlternativesResponse): EnergyAlternative | null {
  let best: EnergyAlternative | null = null;
  for (const alt of allAlternatives(row, ai)) {
    if (mid(alt.saves_usd_yr) <= 0) continue;
    if (!best || mid(alt.saves_usd_yr) > mid(best.saves_usd_yr)) best = alt;
  }
  return best;
}

/**
 * The item after its best upgrade. Heat follows the upgrade's own after-heat when it has one; otherwise
 * heat added to the room shrinks in proportion to the electricity saved (a unit that removes heat keeps
 * its value). Items without an upgrade are returned unchanged.
 */
export function afterRow(row: AssetEnergy, ai?: AiAlternativesResponse): AssetEnergy {
  const best = bestAlternative(row, ai);
  if (!best || !row.estimated) return row;
  const kwh = best.kwh_yr ?? row.kwh_yr;
  const usd = best.usd_yr ?? (row.usd_yr ? ([
    Math.max(0, row.usd_yr[0] - best.saves_usd_yr[1]),
    Math.max(0, row.usd_yr[1] - best.saves_usd_yr[0]),
  ] as Range) : null);
  let heat = best.heat_kwh_yr ?? row.heat_kwh_yr;
  if (!best.heat_kwh_yr && row.heat_kwh_yr && row.heat_kwh_yr[0] >= 0 && row.kwh_yr && best.kwh_yr) {
    const share = mid(best.kwh_yr) / Math.max(1e-9, mid(row.kwh_yr));
    heat = [row.heat_kwh_yr[0] * share, row.heat_kwh_yr[1] * share];
  }
  return { ...row, kwh_yr: kwh, usd_yr: usd, heat_kwh_yr: heat, power_w: best.power_w ?? row.power_w };
}

/** Yearly money and heat saved across the apartment if every item gets its best upgrade (midpoints). */
export function afterTotals(rows: AssetEnergy[], ai: Record<string, AiAlternativesResponse>) {
  let usd = 0;
  let heat = 0;
  let upgraded = 0;
  for (const row of rows) {
    const best = bestAlternative(row, ai[row.asset_id]);
    if (!best || !row.estimated) continue;
    upgraded += 1;
    usd += mid(best.saves_usd_yr);
    const before = mid(row.heat_kwh_yr);
    const after = mid(afterRow(row, ai[row.asset_id]).heat_kwh_yr);
    if (before > 0) heat += Math.max(0, before - after);
  }
  return { usd, heat, upgraded };
}
