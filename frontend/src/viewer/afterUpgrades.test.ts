import { describe, expect, it } from "vitest";
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";
import { afterRow, afterTotals, chosenAlternative } from "./afterUpgrades";

function alt(id: string, saves: [number, number], extra: Partial<EnergyAlternative> = {}): EnergyAlternative {
  return {
    upgrade_id: id, title: id, kwh_yr: null, usd_yr: null, heat_kwh_yr: null, power_w: null,
    saves_kwh_yr: [saves[0] * 3, saves[1] * 3], saves_usd_yr: saves, cost_usd: [10, 20],
    payback_years: [1, 2], who: "", basis: "", ...extra,
  };
}

const film = alt("window_film", [9, 9], { kwh_yr: [70, 70], usd_yr: [21, 21], heat_kwh_yr: [140, 140] });
const window: AssetEnergy = {
  asset_id: "w1", label: "window", room_id: "r1", estimated: true,
  kwh_yr: [100, 100], usd_yr: [30, 30], heat_kwh_yr: [200, 200], power_w: null,
  basis: "", assumed: [], note: "", alternatives: [film],
};

const ai = (ideas: EnergyAlternative[]): AiAlternativesResponse => ({
  schema_version: "1.0.0", sid: "s", asset_id: "w1", model_id: "m", cached: false,
  today_kwh_yr: null, today_usd_yr: null, alternatives: ideas, note: "",
});

describe("after upgrades", () => {
  it("finds the picked upgrade among library and AI ideas", () => {
    const shade = alt("ai:shade", [15, 15], { kwh_yr: [50, 50], usd_yr: [15, 15] });
    expect(chosenAlternative(window, undefined, undefined)).toBeNull();
    expect(chosenAlternative(window, ai([shade]), "ai:shade")).toBe(shade);
    expect(chosenAlternative(window, undefined, "ai:shade")).toBeNull();
  });

  it("uses the upgrade's own heat, or scales heat with the energy saved", () => {
    expect(afterRow(window, film).heat_kwh_yr).toEqual([140, 140]);
    const shade = alt("ai:shade", [15, 15], { kwh_yr: [50, 50], usd_yr: [15, 15] });
    expect(afterRow(window, shade).heat_kwh_yr).toEqual([100, 100]);
    expect(afterRow(window, null)).toBe(window);
  });

  it("adds up only the picked upgrades", () => {
    const fan = { ...window, asset_id: "f1" };
    expect(afterTotals([window, fan], {}, {})).toEqual({ usd: 0, heat: 0, cost: 0, upgraded: 0 });
    expect(afterTotals([window, fan], {}, { w1: "window_film" })).toEqual({ usd: 9, heat: 60, cost: 15, upgraded: 1 });
  });
});
