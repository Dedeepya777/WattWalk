"""Assumptions and upgrade library loader and context.

Owner: Person 1.
See plan/plan.md section 10 and Appendix A.2.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from wattwalk import config
from wattwalk.contracts import AssumptionUsed, Building


def load_assumptions(path: Path | None = None) -> dict[str, Any]:
    p = path or (config.CONTRACTS_DIR / "assumptions.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_upgrades(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or (config.CONTRACTS_DIR / "upgrades.json")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["upgrades"]


TABLE_KEYS = {
    "cooling_kwh_per_m2_yr",
    "window_solar_cooling_kwh_per_m2_yr",
    "heat_share_window_weight_per_m2",
}

FRACTION_KEYS = {
    "window_film_reduction",
    "window_film_cap_fraction",
    "thermostat_hvac_savings_fraction",
}


class AssumptionContext:
    """Resolves scalar assumptions for city and vintage, records usage, and applies overrides."""

    def __init__(self, building: Building, overrides: dict[str, float] | None = None, assumptions_data: dict[str, Any] | None = None):
        self._raw_data = assumptions_data or load_assumptions()
        self._assumptions = self._raw_data.get("assumptions", {})
        self._building = building
        self._city = building.city

        yb = building.year_built.value
        if yb is not None and isinstance(yb, (int, float)):
            if yb < 1980:
                self._vintage = "pre1980"
            elif yb > 2005:
                self._vintage = "post2005"
            else:
                self._vintage = "1980_2005"
        else:
            self._vintage = "1980_2005"

        self._overrides: dict[str, float] = {}
        self._used: dict[str, AssumptionUsed] = {}

        if overrides:
            self._validate_and_set_overrides(overrides)

    def _validate_and_set_overrides(self, overrides: dict[str, float]) -> None:
        for k, v in overrides.items():
            if k not in self._assumptions:
                raise ValueError(f"Unknown override key: {k}")
            if k in TABLE_KEYS:
                raise ValueError(f"Table assumption cannot be overridden: {k}")
            if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) or v < 0:
                raise ValueError(f"Override value for {k} must be a finite non-negative number, got: {v}")
            if k in FRACTION_KEYS and v > 1.0:
                raise ValueError(f"Override value for fraction {k} cannot exceed 1.0, got: {v}")
            self._overrides[k] = float(v)

    @property
    def city(self) -> str:
        return self._city

    @property
    def vintage(self) -> str:
        return self._vintage

    def get(self, key: str) -> float:
        """Resolve assumption key, applying override if present and recording usage."""
        if key not in self._assumptions:
            raise ValueError(f"Unknown assumption key: {key}")

        rec = self._assumptions[key]
        unit = rec.get("unit", "")

        if key in self._overrides:
            val = self._overrides[key]
            status = "user_override"
            source = "user override"
        else:
            status = rec.get("status", "unverified_default")
            source = rec.get("source", "")
            if "value" in rec:
                val = rec["value"]
            elif "by_city" in rec:
                val = rec["by_city"][self._city]
            elif "by_city_vintage" in rec:
                val = rec["by_city_vintage"][self._city][self._vintage]
            else:
                raise ValueError(f"Assumption {key} has no scalar or resolved value")

        self._used[key] = AssumptionUsed(
            key=key,
            value=val,
            unit=unit,
            status=status,
            source=source,
        )
        return float(val)

    def used(self) -> list[AssumptionUsed]:
        """Return all assumptions used, ordered alphabetically by key."""
        return [self._used[k] for k in sorted(self._used.keys())]
