import { describe, expect, it } from "vitest";
import type { AssetEnergy } from "../contracts";
import { NOT_ESTIMATED, REMOVES_HEAT, buildScale, gradient, legendLabels, pinColor, position, toHex } from "./energyColor";

function row(id: string, usd: [number, number] | null, heat: [number, number] | null, estimated = true): AssetEnergy {
  return {
    asset_id: id, label: "lamp", room_id: "r1", estimated, kwh_yr: usd, usd_yr: usd, heat_kwh_yr: heat,
    power_w: null, basis: "", assumed: [], note: "",
  };
}

const rows = [
  row("led", [3, 3], [10, 10]),
  row("chandelier", [237, 237], [788, 788]),
  row("ac", [500, 500], [-1300, -1300]),
  row("dryer", null, null, false),
];

describe("pin colours by energy", () => {
  it("details mode keeps the original colours", () => {
    expect(buildScale(rows, "details")).toBeNull();
    expect(pinColor(rows[0], null)).toBeNull();
  });

  it("cheapest asset is blue, most expensive is red, on a log scale", () => {
    const scale = buildScale(rows, "cost")!;
    expect(scale.min).toBe(3);
    expect(scale.max).toBe(500);
    expect(toHex(pinColor(rows[0], scale)!)).toBe(toHex(gradient(0)));
    expect(toHex(pinColor(rows[2], scale)!)).toBe(toHex(gradient(1)));
    // log scale: $237 sits well into the red half, not near the bottom
    expect(position(237, scale)).toBeGreaterThan(0.8);
  });

  it("heat mode: AC that removes heat is cyan, no estimate is grey", () => {
    const scale = buildScale(rows, "heat")!;
    expect(scale.min).toBe(10);
    expect(scale.max).toBe(788);
    expect(pinColor(rows[2], scale)).toEqual(REMOVES_HEAT);
    expect(pinColor(rows[3], scale)).toEqual(NOT_ESTIMATED);
    expect(pinColor(undefined, scale)).toEqual(NOT_ESTIMATED);
  });

  it("legend labels", () => {
    expect(legendLabels(buildScale(rows, "cost")!)).toEqual({ title: "Cost per year", low: "$3", high: "$500" });
    expect(legendLabels(buildScale(rows, "heat")!).high).toBe("788 kWh");
  });
});
