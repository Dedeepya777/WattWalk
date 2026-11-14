import { describe, expect, it } from "vitest";
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";
import { afterRow, afterTotals, bestAlternative } from "./afterUpgrades";

function alt(id: string, saves: [number, number], extra: Partial<EnergyAlternative> = {}): EnergyAlternative {
  return {
    upgrade_id: id, title: id, kwh_yr: null, usd_yr: null, heat_kwh_yr: null, power_w: null,
    saves_kwh_yr: [saves[0] * 3, saves[1] * 3], saves_usd_yr: saves, cost_usd: [10, 20],
    payback_years: [1, 2], who: "", basis: "", ...extra,
  };
}

const window: AssetEnergy = {
  asset_id: "w1", label: "window", room_id: "r1", estimated: true,
  kwh_yr: [100, 100], usd_yr: [30, 30], heat_kwh_yr: [200, 200], power_w: null,
  basis: "", assumed: [], note: "",
  alternatives: [alt("window_film", [9, 9], { kwh_yr: [70, 70], usd_yr: [21, 21], heat_kwh_yr: [140, 140] })],
};

const ai = (ideas: EnergyAlternative[]): AiAlternativesResponse => ({
  schema_version: "1.0.0", sid: "s", asset_id: "w1", model_id: "m", cached: false,
  today_kwh_yr: null, today_usd_yr: null, alternatives: ideas, note: "",
});

describe("after upgrades", () => {
  it("picks the upgrade that saves the most, library or AI", () => {
    expect(bestAlternative(window)?.upgrade_id).toBe("window_film");
    const better = alt("ai:low_e", [12, 14], { kwh_yr: [55, 60], usd_yr: [16, 18], heat_kwh_yr: [110, 120] });
    expect(bestAlternative(window, ai([better]))?.upgrade_id).toBe("ai:low_e");
  });

  it("uses the upgrade's own heat, or scales heat with the energy saved", () => {
    expect(afterRow(window).heat_kwh_yr).toEqual([140, 140]);
    const noHeat = alt("ai:shade", [15, 15], { kwh_yr: [50, 50], usd_yr: [15, 15] });
    expect(afterRow(window, ai([noHeat])).heat_kwh_yr).toEqual([100, 100]);
  });

  it("leaves items without an upgrade unchanged and adds up the savings", () => {
    const fan = { ...window, asset_id: "f1", alternatives: [] };
    expect(afterRow(fan)).toBe(fan);
    expect(afterTotals([window, fan], {})).toEqual({ usd: 9, heat: 60, upgraded: 1 });
  });
});
