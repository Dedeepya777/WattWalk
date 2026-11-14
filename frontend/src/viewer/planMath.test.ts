import { describe, expect, it } from "vitest";
import type { AssetEnergy, EnergyAlternative } from "../contracts";
import { planLines, planTotals } from "./planMath";

function alt(id: string, saves: [number, number], cost: [number, number]): EnergyAlternative {
  return {
    upgrade_id: id, title: id, kwh_yr: null, usd_yr: null, heat_kwh_yr: null, power_w: null,
    saves_kwh_yr: [0, 0], saves_usd_yr: saves, cost_usd: cost, payback_years: null, who: "", basis: "",
  };
}

function row(id: string, alts: EnergyAlternative[]): AssetEnergy {
  return {
    asset_id: id, label: "window", room_id: "r1", estimated: true, kwh_yr: [100, 100], usd_yr: [30, 30],
    heat_kwh_yr: [200, 200], power_w: null, basis: "", assumed: [], note: "", alternatives: alts,
  };
}

describe("my plan", () => {
  const rows = [row("a", [alt("film", [5, 7], [10, 20])]), row("b", [alt("led", [40, 60], [50, 80])]), row("c", [])];

  it("lists only picked upgrades, biggest saving first", () => {
    const lines = planLines(rows, {}, { a: "film", b: "led" }, () => "Kitchen");
    expect(lines.map((l) => l.alt.upgrade_id)).toEqual(["led", "film"]);
    expect(lines[0]).toMatchObject({ assetId: "b", item: "Window", room: "Kitchen", ai: false });
  });

  it("adds up cost and saving and gives the plan's payback", () => {
    const totals = planTotals(planLines(rows, {}, { a: "film", b: "led" }, () => ""));
    expect(totals.cost).toEqual([60, 100]);
    expect(totals.saves).toEqual([45, 67]);
    expect(totals.payback?.[0]).toBeCloseTo(60 / 67);
    expect(totals.payback?.[1]).toBeCloseTo(100 / 45);
  });
});
