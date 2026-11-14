/** Display formatting only (plan 5.3 and 11.4).  No business logic here. */
import type { AssetLabel, Attr, Source, WhoPays } from "./contracts";
import { SOURCE_LABEL } from "./contracts";

const wholeUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const centsUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const decimal = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatCurrency(value: number | null | undefined, cents = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return cents ? centsUsd.format(value) : wholeUsd.format(value);
}

export function formatCostRange(low: number, high: number): string {
  if (low === high) return formatCurrency(low);
  return `${formatCurrency(low)} to ${formatCurrency(high)}`;
}

export function formatKwh(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${decimal.format(value)} kWh/yr`;
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (digits === 0) return integer.format(value);
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(share: number | null | undefined): string {
  if (share === null || share === undefined || Number.isNaN(share)) return "n/a";
  return `${decimal.format(share * 100)}%`;
}

export function formatPayback(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "not reached";
  return `${value.toFixed(2)} years`;
}

export function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function formatIso(value: string | null | undefined): string {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const LABEL_TEXT: Record<AssetLabel, string> = {
  window: "Window",
  window_ac: "Window AC",
  mini_split: "Mini-split",
  supply_vent: "Supply vent",
  thermostat: "Thermostat",
  ceiling_light: "Ceiling light",
  lamp: "Lamp",
  refrigerator: "Refrigerator",
  range_gas: "Gas range",
  range_electric: "Electric range",
  dishwasher: "Dishwasher",
  washer: "Washer",
  dryer: "Dryer",
  ceiling_fan: "Ceiling fan",
  water_heater: "Water heater",
};

export function labelText(label: AssetLabel | string): string {
  return LABEL_TEXT[label as AssetLabel] ?? titleCase(label);
}

const ATTR_TEXT: Record<string, string> = {
  panes: "Glazing panes",
  shading: "Shading",
  width_m: "Width",
  height_m: "Height",
  area_m2: "Area",
  bulb_type: "Bulb type",
  bulb_count: "Bulb count",
  thermostat_type: "Thermostat type",
  style: "Style",
  age_years: "Age",
};

export function attrText(key: string): string {
  return ATTR_TEXT[key] ?? titleCase(key);
}

export function attrValueText(key: string, attr: Attr): string {
  if (attr.value === null || attr.value === undefined) return "Unknown";
  if (typeof attr.value === "number") {
    if (key === "width_m" || key === "height_m") return `${formatNumber(attr.value, 2)} m`;
    if (key === "area_m2") return `${formatNumber(attr.value, 1)} m²`;
    if (key === "bulb_count") return `${formatNumber(attr.value)} bulbs`;
    if (key === "age_years") return `${formatNumber(attr.value, 1)} years`;
    return formatNumber(attr.value, 1);
  }
  return String(attr.value).replace(/_/g, " ");
}

export function sourceText(source: Source): string {
  return SOURCE_LABEL[source] ?? source;
}

export function whoPaysText(who: WhoPays): string {
  const pays =
    who.pays === "owner_or_tenant" ? "owner or tenant" : who.pays;
  const approval =
    who.approval === "landlord_approval"
      ? "landlord approval needed"
      : who.approval === "owner_decision"
        ? "owner decision"
        : "no approval";
  return `${pays} pays · ${who.saves} saves · ${approval}`;
}

export function evidenceText(level: "verified" | "partly_unverified"): string {
  return level === "verified" ? "Verified" : "Partly unverified";
}

export function reasonText(code: string): string {
  const map: Record<string, string> = {
    not_authorized: "Not authorized",
    already_efficient: "Already efficient",
    over_budget: "Over budget",
    unverified_evidence: "Unverified evidence",
    stay_too_short: "Stay too short",
    mutually_exclusive: "Mutually exclusive",
    missing_dependency: "Missing dependency",
    not_selected: "Not selected",
  };
  return map[code] ?? titleCase(code);
}

export function objectiveText(objective: string): string {
  const map: Record<string, string> = {
    max_bill: "Maximize bill savings",
    max_kwh: "Maximize energy saved",
    best_value: "Best value (payback)",
    conservative: "Conservative (upper costs)",
  };
  return map[objective] ?? titleCase(objective);
}

export function titleCase(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Count attributes whose only honest source is needs_verification. */
export function unknownAttrCount(attrs: Record<string, Attr>): number {
  return Object.values(attrs).filter((attr) => attr.source === "needs_verification").length;
}
