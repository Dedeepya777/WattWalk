"""Single entry point from the agent and API to the other owners' modules. Owner: Person 3.

A plain import list: each name is the owner's real function with the canonical signature from
shared/contracts/README.md section 5. There are no fallbacks. If an owner's module fails to import,
importing this module (and therefore the API) fails at startup with the real traceback.
Fixture behaviour comes only from the run mode (config.RUN_MODE_OVERRIDE and the owners' own
fixture modes), never from this module.

The agent and API call these through the module (P.get_geometry(...)) so tests can monkeypatch them.
"""
from __future__ import annotations

# Person 2: vision first. wattwalk.inventory and wattwalk.vision import each other; importing the
# vision package first lets the cycle resolve (importing inventory first raises ImportError).
from ..vision.walk import inspect_view, plan_views, resolve  # noqa: I001
from ..vision.types import AskFn, InspectResult, ResolveResult, ViewTask
from ..inventory import apply_correction, build_inventory, compute_coverage
# Person 1: data adapters and engine
from ..data.building import get_building
from ..data.matterport import get_geometry
from ..engine import explain_template, heat_shares, plan

__all__ = [
    "get_geometry", "get_building", "plan", "heat_shares", "explain_template",
    "plan_views", "inspect_view", "resolve", "build_inventory", "compute_coverage", "apply_correction",
    "ViewTask", "InspectResult", "ResolveResult", "AskFn",
]
