"""Vision vocabulary and prompt texts (plan 7.3, 8.3.1, 8.5, Appendix E.1 and E.2). Owner: Person 2.

VOCAB is the single backend source of allowed attributes; it must match plan section 7.3.
"""
from __future__ import annotations

from ..contracts import ASSET_LABELS

# Allowed values per (label, attribute). A list means a closed set of strings; a tuple means a
# numeric (min, max) range; "int" ranges are listed in INT_ATTRS. "unknown" is always accepted
# from a model and becomes null with source needs_verification.
VOCAB: dict[str, dict[str, list[str] | tuple[float, float]]] = {
    "window": {
        "panes": ["single", "double"],
        "shading": ["blinds", "curtains", "shutters", "none"],
        "width_m": (0.2, 5.0),
        "height_m": (0.2, 5.0),
        "area_m2": (0.04, 25.0),  # derived: width_m x height_m
    },
    "ceiling_light": {"bulb_type": ["led", "cfl", "incandescent"], "bulb_count": (1, 12)},
    "lamp": {"bulb_type": ["led", "cfl", "incandescent"], "bulb_count": (1, 12)},
    "thermostat": {"thermostat_type": ["smart", "digital", "dial"]},
    "refrigerator": {"style": ["top_freezer", "bottom_freezer", "side_by_side", "french_door"], "age_years": (0, 60)},
}
for _label in ASSET_LABELS:
    VOCAB.setdefault(_label, {})

INT_ATTRS = {"bulb_count"}

# Attributes a model may report, in the order they are stored on an observation.
MODEL_ATTRS: dict[str, list[str]] = {
    "window": ["shading", "width_m", "height_m"],
    "ceiling_light": ["bulb_type", "bulb_count"],
    "lamp": ["bulb_type", "bulb_count"],
    "thermostat": ["thermostat_type"],
    "refrigerator": ["style"],
}

# Non-visual attributes: always needs_verification with a fixed note, whatever a model says (8.3.4).
NON_VISUAL: dict[tuple[str, str], str] = {
    ("window", "panes"): "glazing not determinable from image",
    ("refrigerator", "age_years"): "age not determinable from appearance",
}

# Key attribute per label for routing (7.3). Labels not listed have no key attribute.
KEY_ATTR: dict[str, str] = {
    "window": "shading",
    "ceiling_light": "bulb_type",
    "lamp": "bulb_type",
    "thermostat": "thermostat_type",
}

# Attributes a user can answer in a question dialog (rule R7).
USER_ANSWERABLE = {"bulb_type", "thermostat_type"}

# Order in which attributes are stored on an observation (matches shared/examples/observations.json).
ATTR_ORDER: dict[str, list[str]] = {
    "window": ["panes", "shading", "width_m", "height_m", "area_m2"],
    "ceiling_light": ["bulb_type", "bulb_count"],
    "lamp": ["bulb_type", "bulb_count"],
    "thermostat": ["thermostat_type"],
    "refrigerator": ["style", "age_years"],
}

DETECT_PROMPT = """You are inspecting one face of a 360-degree photo of an apartment for an energy audit.
The image is {w} x {h} pixels.

Find every visible object from this list and nothing else:
window, window_ac, mini_split, supply_vent, thermostat, ceiling_light, lamp, refrigerator,
range_gas, range_electric, dishwasher, washer, dryer, ceiling_fan, water_heater.

What the labels mean:
- window: glass in an outside wall that shows the OUTDOORS (sky, trees, buildings, daylight).
  NOT a window: a mirror (it shows the inside of the room, often a camera on a tripod), a door,
  closet or cabinet doors, a picture or poster, a TV screen, a shower curtain.
- window_ac: a box unit sitting inside a window opening. A long white unit high on a wall is a
  mini_split. A flat metal or white box with a door on a wall is an electrical panel (not on the list).
- ceiling_light: a light fixture attached to the ceiling or high on a wall. A small round smoke
  detector is not a light.
- lamp: a floor, table, desk or wall lamp whose shade, base or bulb is visible.
- ceiling_fan: blades hanging from the ceiling. A table, rug or shelf is not a fan.

For each object return its label, a bounding box [x0, y0, x1, y1] in pixels of this image
(x to the right, y down, origin top-left), and only these attributes:
- window: shading ("blinds" | "curtains" | "shutters" | "none" | "unknown"),
          width_m (number), height_m (number)
- ceiling_light or lamp: bulb_type ("led" | "cfl" | "incandescent" | "unknown"), bulb_count (integer)
- thermostat: thermostat_type ("smart" | "digital" | "dial" | "unknown")
- refrigerator: style ("top_freezer" | "bottom_freezer" | "side_by_side" | "french_door" | "unknown")

Rules:
- If you are not sure an object is on the list, leave it out. An empty list is a good answer.
- Report an attribute value only if it is clearly visible. Otherwise use "unknown".
- Never guess bulb wattage, window glazing, appliance age, or equipment efficiency.
- Give each object exactly one label and report it once.
- If the image is too dark, blurry or obstructed to inspect, set "image_ok" to false.

Return only JSON, no other text:
{"image_ok": true, "detections": [{"label": "...", "bbox": [0, 0, 0, 0], "attrs": {}}]}"""

ATTR_PROMPT = """This is a close crop of a {label} from an apartment photo.
Report only these attributes for a {label}: {allowed_attrs_with_values}.
Use "unknown" for anything not clearly visible. Never guess wattage, glazing, age or efficiency.
Return only JSON, no other text: {"attrs": {...}}"""


# Second look (not in the plan; added after real-scan testing): each detection with one of these
# labels is cropped and sent back with a narrow, NEUTRAL question (the detector's guess is not shown:
# telling the model the guess made it repeat the guess). The answer decides the detection:
#   - the same label: kept;
#   - another label from VOCAB (e.g. window_ac -> mini_split, lamp -> ceiling_light): relabelled;
#   - anything else (mirror, doorway, picture...): dropped.
# Results on hand-checked Cherokee crops (2026-11-14, qwen2.5vl:7b): old keep/drop prompt 17/20,
# neutral prompt with relabelling 20/20 on two runs (fixed: doorway read as a window, mini split
# read as a window AC, ceiling fixture read as a lamp).
# Set SECOND_LOOK_LABELS to an empty dict to switch it off.
SECOND_LOOK_LABELS: dict[str, list[str]] = {
    "window": ["window", "mirror", "doorway", "door", "cabinet", "picture", "screen", "curtain", "wall", "other"],
    "window_ac": ["window_ac", "mini_split", "electrical_panel", "vent", "other"],
    "ceiling_light": ["ceiling_light", "smoke_detector", "vent", "other"],
    "ceiling_fan": ["ceiling_fan", "table", "furniture", "other"],
    "lamp": ["lamp", "ceiling_light", "picture", "mirror", "other"],
}

SECOND_LOOK_HINTS: dict[str, str] = {
    "window": ("A window is glass in a wall that shows the outdoors. A mirror shows the inside of the room. "
               "A doorway is an open passage you could walk through into another room."),
    "window_ac": ("A window_ac is a box unit sitting in a window opening. A mini_split is a long, flat, white "
                  "unit mounted high on a wall, not in a window."),
    "ceiling_light": ("A ceiling_light is a light fixture on the ceiling or high on a wall. A smoke detector is "
                      "a small round plastic disc with no bulb."),
    "ceiling_fan": "A ceiling fan has blades hanging from the ceiling.",
    "lamp": ("A lamp stands on the floor or a table, or is a wall lamp with a shade or arm. A ceiling_light "
             "is fixed flat to the ceiling."),
}

VERIFY_PROMPT = """This is a close crop from an apartment photo.
What is the main object in the crop? Choose exactly one of: {choices}.
{hints}
Return only JSON, no other text: {"object": "..."}"""


def verify_prompt(label: str) -> str:
    return (VERIFY_PROMPT.replace("{choices}", ", ".join(SECOND_LOOK_LABELS[label]))
            .replace("{hints}", SECOND_LOOK_HINTS.get(label, "")))


def detect_prompt(w: int, h: int) -> str:
    # str.replace, not str.format: the prompt contains literal JSON braces.
    return DETECT_PROMPT.replace("{w}", str(w)).replace("{h}", str(h))


def _describe(label: str, attr: str) -> str:
    allowed = VOCAB[label][attr]
    if isinstance(allowed, list):
        return f'{attr} (' + " | ".join(f'"{v}"' for v in allowed + ["unknown"]) + ")"
    return f"{attr} ({'integer' if attr in INT_ATTRS else 'number'})"


def attr_prompt(label: str) -> str:
    allowed = ", ".join(_describe(label, a) for a in MODEL_ATTRS.get(label, []))
    return (ATTR_PROMPT.replace("{label}", label.replace("_", " "))
            .replace("{allowed_attrs_with_values}", allowed or "none"))
