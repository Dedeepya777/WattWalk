/** Pure maths for "My upgrade plan": the picked upgrades as lines, and their totals. */
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";
import { labelText } from "../format";
import { chosenAlternative } from "./afterUpgrades";

type Range = [number, number];

export interface PlanLine {
  assetId: string;
  item: string;
  room: string;
  alt: EnergyAlternative;
  ai: boolean;
}

/** One line per item with a picked upgrade, biggest yearly saving first. */
export function planLines(
  rows: AssetEnergy[],
  ai: Record<string, AiAlternativesResponse>,
  chosen: Record<string, string>,
  roomName: (roomId: string | null | undefined) => string,
): PlanLine[] {
  const lines: PlanLine[] = [];
  for (const row of rows) {
    const alt = chosenAlternative(row, ai[row.asset_id], chosen[row.asset_id]);
    if (!alt) continue;
    lines.push({
      assetId: row.asset_id,
      item: labelText(row.label),
      room: roomName(row.room_id),
      alt,
      ai: alt.upgrade_id.startsWith("ai:"),
    });
  }
  const mid = (r: Range) => (r[0] + r[1]) / 2;
  return lines.sort((a, b) => mid(b.alt.saves_usd_yr) - mid(a.alt.saves_usd_yr));
}

/** Sum of the cost and saving ranges, and the payback of the whole plan (low, high). */
export function planTotals(lines: PlanLine[]) {
  const cost: Range = [0, 0];
  const saves: Range = [0, 0];
  for (const { alt } of lines) {
    cost[0] += alt.cost_usd[0];
    cost[1] += alt.cost_usd[1];
    saves[0] += alt.saves_usd_yr[0];
    saves[1] += alt.saves_usd_yr[1];
  }
  let payback: Range | null = null;
  if (saves[1] > 0) payback = [cost[0] / saves[1], saves[0] > 0 ? cost[1] / saves[0] : cost[1] / saves[1]];
  return { cost, saves, payback };
}
