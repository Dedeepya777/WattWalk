"""Rough upgrade ideas for one asset from a language model (DeepSeek), on top of the upgrade library.

The split of work keeps the numbers honest:
  * the model suggests 2-3 upgrades, each with a share of the asset's energy it would cut (low, high
    percent) and an installed price range; for an asset the engine cannot estimate (a TV, a fan) it
    also estimates the asset's electricity today;
  * the saving per year and the payback are computed here from the asset's energy and the electricity
    rate in assumptions.json, exactly like the library upgrades in asset_energy.py.

Everything the model says is checked and clamped (cut 1-95 %, prices >= 0, at most 3 ideas) and every
idea is labelled as an AI estimate. Answers are saved per audit in audits/<sid>/ai_alternatives.json,
so asking again is instant and free.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from wattwalk import config, store
from wattwalk.contracts import AiAlternativesResponse, Asset, Building, EnergyAlternative
from wattwalk.engine.asset_energy import AUTHORIZER_TEXT, AssetEnergy, _money, _r, _value, inventory_energy
from wattwalk.engine.assumptions import AssumptionContext

MAX_IDEAS = 3
CACHE_FILE = "ai_alternatives.json"
DEFAULT_MODEL = "deepseek/deepseek-flash"
TIMEOUT_S = 60

Ask = Callable[[str], str]  # prompt -> model text (JSON)


class ResearchUnavailable(RuntimeError):
    """No model is configured (no DEEPSEEK_API_KEY)."""


class ResearchFailed(RuntimeError):
    """The model could not be reached or returned nothing usable."""


def research_model_id() -> str:
    """The research model: the planner or large vision model when it is a DeepSeek id, else DeepSeek Flash."""
    for mid in (config.PLANNER_MODEL_ID, config.LARGE_VISION_MODEL_ID):
        if mid and mid.startswith("deepseek/"):
            return mid
    return DEFAULT_MODEL


def _ask_deepseek(model_id: str) -> Ask:
    if not config.DEEPSEEK_API_KEY:
        raise ResearchUnavailable("DEEPSEEK_API_KEY is not set; add it to .env to research alternatives.")

    def ask(prompt: str) -> str:
        import urllib.error
        import urllib.request

        from wattwalk.vision.detect import _normalize_deepseek_model

        body = json.dumps({
            "model": _normalize_deepseek_model(model_id),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 900,
            # Same as vision: thinking off returns clean JSON quickly.
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        base = config.DEEPSEEK_BASE_URL
        endpoint = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
        req = urllib.request.Request(endpoint, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise ResearchFailed(f"DeepSeek returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResearchFailed(f"DeepSeek not reachable: {exc}") from exc
        choices = data.get("choices") or []
        return (choices[0].get("message", {}).get("content") or "") if choices else ""

    return ask


def _describe(asset: Asset) -> str:
    seen = {k: _value(asset, k) for k in asset.attrs}
    seen = {k: v for k, v in seen.items() if v not in (None, "", "unknown")}
    return json.dumps({"item": asset.label.replace("_", " "), "seen": seen})


def build_prompt(asset: Asset, row: AssetEnergy, rate: float, library_titles: list[str]) -> str:
    today = (f"Today it uses about {row.kwh_yr[0]:g}-{row.kwh_yr[1]:g} kWh of electricity a year."
             if row.kwh_yr else
             "We have no estimate of its electricity use; estimate it as today_kwh_yr.")
    skip = f" Do not repeat these, already suggested: {', '.join(library_titles)}." if library_titles else ""
    return (
        "You help renters and landlords in a US apartment cut electricity use and indoor heat.\n"
        f"Item: {_describe(asset)}. {today} Electricity costs ${rate:.2f}/kWh.\n"
        f"Suggest {MAX_IDEAS - 1} to {MAX_IDEAS} practical upgrades or replacements for this item.{skip}\n"
        "For each give: title (max 6 words), why (max 12 words), kwh_cut_pct as [low, high] percent of this "
        "item's electricity saved, cost_usd as [low, high] typical US installed price, and who: one of "
        '"tenant", "tenant_with_approval", "owner". Be conservative and realistic.\n'
        'Reply only with JSON: {"today_kwh_yr": [low, high] or null, "ideas": [{"title": "", "why": "", '
        '"kwh_cut_pct": [0, 0], "cost_usd": [0, 0], "who": ""}]}'
    )


def _pair(value, lo: float, hi: float) -> Optional[tuple[float, float]]:
    """[a, b] of numbers, clamped to [lo, hi] and ordered; None when malformed."""
    if isinstance(value, (int, float)):
        value = [value, value]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        a, b = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    a, b = sorted((min(max(a, lo), hi), min(max(b, lo), hi)))
    return (a, b)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "idea"


def parse_ideas(text: str, row: AssetEnergy, rate: float) -> tuple[Optional[tuple[float, float]], list[dict]]:
    """Check the model's JSON and turn each idea into an EnergyAlternative dict (savings computed here)."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ResearchFailed("The model did not return JSON.") from exc
    if not isinstance(data, dict):
        raise ResearchFailed("The model did not return a JSON object.")
    today_ai = None
    kwh = row.kwh_yr
    if kwh is None:
        today_ai = _pair(data.get("today_kwh_yr"), 0, 20000)
        if today_ai is None or today_ai[1] <= 0:
            return None, []  # the item uses no electricity of its own (a vent, a door): nothing to save
        kwh = _r(*today_ai)
    out: list[dict] = []
    seen: set[str] = set()
    for idea in data.get("ideas") or []:
        if not isinstance(idea, dict) or len(out) >= MAX_IDEAS:
            continue
        title = str(idea.get("title") or "").strip()[:60]
        cut = _pair(idea.get("kwh_cut_pct"), 1, 95)
        cost = _pair(idea.get("cost_usd"), 0, 50000)
        if not title or cut is None or cost is None or _slug(title) in seen:
            continue
        seen.add(_slug(title))
        saves = _r(kwh[0] * cut[0] / 100, kwh[1] * cut[1] / 100)
        after = _r(kwh[0] - saves[0], kwh[1] - saves[1])
        saves_usd = _money(saves, rate)
        payback = None
        if saves_usd[1] > 0:
            payback = _r(cost[0] / saves_usd[1], cost[1] / saves_usd[0] if saves_usd[0] > 0 else cost[1] / saves_usd[1])
        heat_after = None
        if row.heat_kwh_yr and row.heat_kwh_yr[0] >= 0:
            heat_after = _r(row.heat_kwh_yr[0] * (1 - cut[1] / 100), row.heat_kwh_yr[1] * (1 - cut[0] / 100))
        who = str(idea.get("who") or "")
        why = str(idea.get("why") or "").strip()[:120]
        out.append(EnergyAlternative(
            upgrade_id=f"ai:{_slug(title)}",
            title=title,
            kwh_yr=after,
            usd_yr=_money(after, rate),
            heat_kwh_yr=heat_after,
            power_w=None,
            saves_kwh_yr=saves,
            saves_usd_yr=saves_usd,
            cost_usd=_r(cost[0], cost[1], 0),
            payback_years=payback,
            who=AUTHORIZER_TEXT.get(who, "check who can do it"),
            basis=f"AI estimate, not sourced: cuts {cut[0]:g}-{cut[1]:g}% of this item's electricity. {why}".strip(),
        ).model_dump())
    if not out:
        raise ResearchFailed("The model returned no usable ideas.")
    return today_ai, out


def _load_cache(sid: str) -> dict:
    path = store.audit_dir(sid) / CACHE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(sid: str, cache: dict) -> None:
    path = store.audit_dir(sid) / CACHE_FILE
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def research(sid: str, asset_id: str, inventory: list[Asset], building: Building,
             ask: Ask | None = None, refresh: bool = False) -> AiAlternativesResponse:
    """2-3 AI upgrade ideas for one asset, cached per audit. Raises KeyError for an unknown asset."""
    asset = next((a for a in inventory if a.id == asset_id), None)
    if asset is None:
        raise KeyError(asset_id)
    cache = _load_cache(sid)
    if asset_id in cache and not refresh:
        return AiAlternativesResponse(**{**cache[asset_id], "cached": True})

    ctx = AssumptionContext(building)
    rate = ctx.get("electricity_rate_usd_per_kwh")
    rows = inventory_energy(inventory, building, ctx)
    row = rows[[a.id for a in inventory].index(asset_id)]
    model_id = research_model_id()
    ask = ask or _ask_deepseek(model_id)
    text = ask(build_prompt(asset, row, rate, [alt["title"] for alt in row.alternatives]))
    today_ai, ideas = parse_ideas(text, row, rate)
    if not ideas and row.kwh_yr is None:
        result = AiAlternativesResponse(
            sid=sid, asset_id=asset_id, model_id=model_id, cached=False, alternatives=[],
            note="This item does not use electricity by itself, so there is nothing to save on it.")
        cache[asset_id] = result.model_dump(mode="json")
        _save_cache(sid, cache)
        return result
    result = AiAlternativesResponse(
        sid=sid, asset_id=asset_id, model_id=model_id, cached=False,
        today_kwh_yr=today_ai, today_usd_yr=_money(today_ai, rate) if today_ai else None,
        alternatives=ideas,
        note="Rough ideas from an AI model. Savings and payback are computed from the item's energy; "
             "the energy cut and prices are the model's estimates, not sourced.",
    )
    cache[asset_id] = result.model_dump(mode="json")
    _save_cache(sid, cache)
    return result
