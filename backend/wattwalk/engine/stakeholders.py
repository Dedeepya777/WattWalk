"""Stakeholder mapping and evidence levels.

Owner: Person 1.
See plan/plan.md section 10.7 and Appendix A.2.
"""
from __future__ import annotations

from typing import Any

from wattwalk.contracts import Asset, PlanRequest, WhoPays


def who_pays(upgrade: dict[str, Any], req: PlanRequest) -> WhoPays:
    """Determine who pays, who saves, and what approval is required."""
    authorizer = upgrade["authorizer"]
    role = req.role
    saves = "tenant" if req.tenant_pays_electric else "owner"

    if role == "owner":
        if authorizer == "owner":
            return WhoPays(pays="owner", saves=saves, approval="owner_decision")
        elif authorizer == "tenant":
            return WhoPays(pays="owner_or_tenant", saves=saves, approval="none")
        elif authorizer == "tenant_with_approval":
            return WhoPays(pays="owner", saves=saves, approval="none")
        else:
            raise ValueError(f"Unknown authorizer: {authorizer}")
    else:  # role == "tenant"
        if authorizer == "tenant":
            return WhoPays(pays="tenant", saves=saves, approval="none")
        elif authorizer == "tenant_with_approval":
            return WhoPays(pays="tenant", saves=saves, approval="landlord_approval")
        else:
            # Not reachable under valid candidate filtering
            return WhoPays(pays="owner", saves=saves, approval="owner_decision")


def evidence_level(upgrade: dict[str, Any], inventory: list[Asset]) -> str:
    """Determine evidence level: verified if all target assets have known values for depends_on_attrs."""
    depends = upgrade.get("depends_on_attrs", [])
    if not depends:
        return "verified"

    target_assets = [a for a in inventory if a.label in upgrade["applies_to"]]
    if not target_assets:
        return "verified"

    for asset in target_assets:
        for attr_name in depends:
            attr = asset.attrs.get(attr_name)
            if attr is None or attr.value is None:
                return "partly_unverified"

    return "verified"
