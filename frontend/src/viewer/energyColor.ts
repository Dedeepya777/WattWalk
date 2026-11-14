/**
 * Pin colours by energy (step 3 of the energy view). Pure functions shared by the 2D plan and the 3D
 * tour, so both show the same colour for the same asset.
 *
 * Modes: "details" keeps the original colours (green = all details known, amber = some unknown);
 * "cost" colours by cost per year; "heat" by heat added to the room per year. The scale is relative to
 * this apartment (lowest to highest estimated asset) and logarithmic, because costs span two orders of
 * magnitude ($3 LED to $237 chandelier) and a linear scale would paint almost everything blue.
 * Assets that move heat outside (AC) are cyan; assets with no estimate are grey.
 */
import type { AssetEnergy } from "../contracts";

export type PinColorMode = "details" | "cost" | "heat";

/** Colour channels 0..1 (the Showcase SDK's tag colour format). */
export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export interface EnergyScale {
  mode: Exclude<PinColorMode, "details">;
  min: number;
  max: number;
}

const LOW: Rgb = { r: 0.23, g: 0.51, b: 0.96 }; // blue
const MID: Rgb = { r: 0.98, g: 0.8, b: 0.08 }; // yellow
const HIGH: Rgb = { r: 0.94, g: 0.27, b: 0.27 }; // red
export const REMOVES_HEAT: Rgb = { r: 0.13, g: 0.83, b: 0.93 }; // cyan
export const NOT_ESTIMATED: Rgb = { r: 0.42, g: 0.45, b: 0.5 }; // grey

const mid = (range: [number, number]) => (range[0] + range[1]) / 2;

/** The number a mode colours by: cost (midpoint $/yr) or heat (midpoint kWh/yr; negative removes heat). */
export function metric(row: AssetEnergy, mode: Exclude<PinColorMode, "details">): number | null {
  if (!row.estimated) return null;
  const range = mode === "cost" ? row.usd_yr : row.heat_kwh_yr;
  return range ? mid(range) : null;
}

/** Lowest and highest positive value among the assets; null when there is nothing to colour. */
export function buildScale(rows: AssetEnergy[], mode: PinColorMode): EnergyScale | null {
  if (mode === "details") return null;
  const values = rows.map((row) => metric(row, mode)).filter((v): v is number => v !== null && v > 0);
  if (values.length === 0) return null;
  return { mode, min: Math.min(...values), max: Math.max(...values) };
}

function mix(a: Rgb, b: Rgb, t: number): Rgb {
  return { r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t };
}

/** Position 0..1 of a value on the log scale (0 = lowest asset, 1 = highest). */
export function position(value: number, scale: EnergyScale): number {
  if (scale.max <= scale.min) return 1;
  const t = (Math.log(value) - Math.log(scale.min)) / (Math.log(scale.max) - Math.log(scale.min));
  return Math.min(1, Math.max(0, t));
}

/** Blue → yellow → red along the scale. */
export function gradient(t: number): Rgb {
  return t <= 0.5 ? mix(LOW, MID, t / 0.5) : mix(MID, HIGH, (t - 0.5) / 0.5);
}

/** The colour of one pin, or null to keep the "details" colours. */
export function pinColor(row: AssetEnergy | undefined, scale: EnergyScale | null): Rgb | null {
  if (!scale) return null;
  if (!row) return NOT_ESTIMATED;
  const value = metric(row, scale.mode);
  if (value === null) return NOT_ESTIMATED;
  if (value < 0) return REMOVES_HEAT;
  if (value === 0) return gradient(0);
  return gradient(position(value, scale));
}

export function toHex(c: Rgb): string {
  const h = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0");
  return `#${h(c.r)}${h(c.g)}${h(c.b)}`;
}

/** Legend labels for the two ends of the scale. */
export function legendLabels(scale: EnergyScale): { low: string; high: string; title: string } {
  if (scale.mode === "cost") {
    return { title: "Cost per year", low: `$${Math.round(scale.min)}`, high: `$${Math.round(scale.max)}` };
  }
  const kwh = (v: number) => `${Math.round(v).toLocaleString()} kWh`;
  return { title: "Heat into the room per year", low: kwh(scale.min), high: kwh(scale.max) };
}

/** CSS linear-gradient matching gradient(): for the legend bar. */
export const LEGEND_CSS = `linear-gradient(90deg, ${toHex(LOW)}, ${toHex(MID)}, ${toHex(HIGH)})`;
