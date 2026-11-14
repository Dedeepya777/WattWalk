import { describe, expect, it } from "vitest";
import { energySummary, formatRange } from "./format";

describe("energy text for 3D pins and the evidence card", () => {
  it("formats single values and ranges", () => {
    expect(formatRange([3, 3], "", true)).toBe("$3");
    expect(formatRange([3.2, 19.7], "", true)).toBe("$3–20");
    expect(formatRange([9, 60], "W")).toBe("9–60 W");
    expect(formatRange([1187.4, 1187.4], "kWh")).toBe("1,187 kWh");
    expect(formatRange(null, "W")).toBe("–");
  });

  it("builds the one-line pin summary", () => {
    const base = { estimated: true, usd_yr: [236.5, 236.5] as [number, number], heat_kwh_yr: [788, 788] as [number, number] };
    expect(energySummary({ ...base, power_w: [720, 720] })).toBe("≈ $237/yr · 720 W");
    expect(energySummary({ ...base, power_w: null, heat_kwh_yr: [1187, 1187] })).toBe("≈ $237/yr · 1,187 kWh heat/yr");
    expect(energySummary({ ...base, power_w: null, heat_kwh_yr: [-500, -500] })).toBe("≈ $237/yr · removes heat");
    expect(energySummary({ estimated: false, usd_yr: null, power_w: null, heat_kwh_yr: null })).toBe("");
  });
});
