/** Building context card (plan 11.3). */
import { fileUrl } from "../api";
import type { Attr } from "../contracts";
import type { ReactNode } from "react";
import { formatCurrency, formatNumber } from "../format";
import { useAppState } from "../state";
import { SourceChip } from "./SourceChip";

function AttrLine({
  label,
  attr,
  children,
}: {
  label: string;
  attr: Attr;
  children: ReactNode;
}) {
  return (
    <div className="attr-line">
      <span className="attr-key">{label}</span>
      <span className="attr-value">{children}</span>
      <SourceChip source={attr.source} note={attr.note} />
    </div>
  );
}

export function BuildingCard() {
  const state = useAppState();
  const building = state.audit?.building ?? null;
  const running = state.audit?.status.status === "running";

  return (
    <section className="panel" aria-labelledby="building-heading">
      <div className="panel-heading">
        <h2 id="building-heading">Building</h2>
      </div>
      {!building ? (
        running ? (
          <div className="skeleton skeleton-card" />
        ) : (
          <p className="empty">Building data not loaded yet.</p>
        )
      ) : (
        <div className="building-card">
          <p className="building-address">{building.address || "Address unavailable"}</p>
          <p className="muted small">
            {building.city}
            {building.costar_property_id ? ` · CoStar ${building.costar_property_id}` : ""}
          </p>

          <div className="attr-list">
            <AttrLine label="Year built" attr={building.year_built}>
              {building.year_built.value ?? "Unknown"}
            </AttrLine>
            <AttrLine label="Units" attr={building.units}>
              {building.units.value ?? "Unknown"}
            </AttrLine>
            <AttrLine label="Asking rent" attr={building.asking_rent_usd_month}>
              {building.asking_rent_usd_month.value === null
                ? "Unknown"
                : `${formatCurrency(Number(building.asking_rent_usd_month.value))}/mo`}
            </AttrLine>
            <AttrLine label="Unit area" attr={building.unit_floor_area_m2}>
              {building.unit_floor_area_m2.value === null
                ? "Unknown"
                : `${formatNumber(Number(building.unit_floor_area_m2.value), 1)} m²`}
            </AttrLine>
          </div>

          <div className="ebewe-block">
            <h3>LA EBEWE context</h3>
            {building.ebewe ? (
              <>
                <p>
                  <strong>{formatNumber(building.ebewe.site_eui_kbtu_ft2, 1)}</strong> kBtu/ft²/yr
                  <span className="muted">
                    {" "}
                    · program year {building.ebewe.program_year} · {building.ebewe.property_type}
                  </span>
                </p>
                <p className="muted small">
                  Reported building site energy; includes gas, common areas and all end
                  uses. Context, not validation of the model.
                </p>
              </>
            ) : (
              <p className="empty">No EBEWE record for this address.</p>
            )}
          </div>

          <div className="roof-block">
            <h3>Roof / aerial</h3>
            {building.roof.status === "unavailable" || !building.roof.ortho_ref ? (
              <p className="empty">Roof data unavailable.</p>
            ) : fileUrl(state.selectedSid, building.roof.ortho_ref) ? (
              <img
                className="roof-thumb"
                src={fileUrl(state.selectedSid, building.roof.ortho_ref)}
                alt="Vexcel aerial orthophoto of the building roof"
                onError={(event) => {
                  (event.currentTarget as HTMLImageElement).style.display = "none";
                }}
                onLoad={(event) => {
                  // Fixture audits ship a 1x1 placeholder instead of a real aerial photo.
                  const img = event.currentTarget as HTMLImageElement;
                  if (img.naturalWidth <= 2 || img.naturalHeight <= 2) img.style.display = "none";
                }}
              />
            ) : (
              <p className="empty">Aerial image is not bundled in fixture mode.</p>
            )}
            <p className="muted small">Vexcel: {building.roof.status}</p>
          </div>
        </div>
      )}
    </section>
  );
}
