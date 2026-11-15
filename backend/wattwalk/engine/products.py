"""Real products for upgrades, shown as one clickable link per upgrade in the energy card.

Library upgrades (upgrades.json) have one hand-picked product each, linked straight to its Amazon page
(checked 14 Nov 2026 that each lands on the product). AI ideas name a product and get a first-result
link built here; the model never supplies a URL, so links cannot be made up.
"""
from __future__ import annotations

import urllib.parse

# A "jump to the first result" search limited to amazon.com: the click lands on the product's page.
FIRST_RESULT_LINK = "https://duckduckgo.com/?q={query}"

LIBRARY_PRODUCTS: dict[str, dict] = {
    "led": {
        "name": "Philips Ultra Efficient LED A19 Light Bulb",
        "why": "uses about 4 W for 60 W of light",
        "url": "https://www.amazon.com/dp/B0CVBMQC5R",
    },
    "window_film": {
        "name": "BDF S2 Window Film Heat Control",
        "why": "solar control film, peel-and-stick",
        "url": "https://www.amazon.com/dp/B00FRLG65K",
    },
    "smart_thermostat": {
        "name": "Google Nest Thermostat",
        "why": "ENERGY STAR certified smart thermostat",
        "url": "https://www.amazon.com/dp/B08HRPDYTP",
    },
    "fridge": {
        "name": "GE ENERGY STAR Top-Freezer Refrigerator",
        "why": "ENERGY STAR certified",
        "url": "https://www.amazon.com/dp/B0BNLZCJPC",
    },
    "heat_pump": {
        "name": "MRCOOL DIY Ductless Mini-Split Heat Pump",
        "why": "inverter heat pump, single zone",
        "url": "https://www.amazon.com/dp/B0B39GVPKS",
    },
}


def product_link(name: str) -> str:
    """Link that opens the first amazon.com result for the exact product name."""
    return FIRST_RESULT_LINK.format(query=urllib.parse.quote_plus(f"\\ site:amazon.com {name}"))


def library_products(upgrade_id: str) -> list[dict]:
    """The one product for a library upgrade, in ProductSuggestion shape (price shown on Amazon)."""
    product = LIBRARY_PRODUCTS.get(upgrade_id)
    if not product:
        return []
    return [{"name": product["name"], "approx_price_usd": None, "why": product["why"], "url": product["url"]}]
