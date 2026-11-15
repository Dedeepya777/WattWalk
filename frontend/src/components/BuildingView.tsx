/**
 * Building overview for a landlord: every scanned unit ranked by yearly energy cost, with its heat, its
 * biggest heat source and its best fix, and a building-wide estimate (the audited units' average times the
 * building's unit count). Opened from a building card in the sidebar.
 */
import { useEffect, useMemo, useState } from "react";
import { ApiFailure, getAssetEnergy, getAudit } from "../api";
import type { AssetEnergyResponse, AuditResponse, EnergyAlternative } from "../contracts";
import { labelText } from "../format";
import { useAppDispatch, useAppState } from "../state";
import { formatPayback } from "./EnergyAlternatives";
import { groupModels, unitName } from "./ModelPicker";

const mid = (r: [number, number] | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);
const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

interface UnitData {
  sid: string;
  name: string;
  status: "audited" | "not_audited" | "running" | "error";
  cost: number;
  heat: number;
  topSource: string | null;
  bestFix: EnergyAlternative | null;
  /** Every item's best upgrade together: yearly saving and install cost (midpoints). */
  saveAll: number;
  installAll: number;
  fixes: number;
  buildingUnits: number | null;
}

function summarize(sid: string, name: string, audit: AuditResponse | null, energy: AssetEnergyResponse | null): UnitData {
  if (!audit) return { sid, name, status: "not_audited", cost: 0, heat: 0, topSource: null, bestFix: null, saveAll: 0, installAll: 0, fixes: 0, buildingUnits: null };
  const units = audit.building?.units?.value;
  const buildingUnits = typeof units === "number" && units > 0 ? units : null;
  if (audit.status.status === "running") {
    return { sid, name, status: "running", cost: 0, heat: 0, topSource: null, bestFix: null, saveAll: 0, installAll: 0, fixes: 0, buildingUnits };
  }
  if (!energy) return { sid, name, status: "not_audited", cost: 0, heat: 0, topSource: null, bestFix: null, saveAll: 0, installAll: 0, fixes: 0, buildingUnits };
  const bySource = new Map<string, number>();
  let best: EnergyAlternative | null = null;
  let saveAll = 0;
  let installAll = 0;
  let fixes = 0;
  for (const row of energy.assets) {
    const heat = mid(row.heat_kwh_yr);
    if (heat > 0) bySource.set(row.label, (bySource.get(row.label) ?? 0) + heat);
    let itemBest: EnergyAlternative | null = null;
    for (const alt of row.alternatives) {
      if (!best || mid(alt.saves_usd_yr) > mid(best.saves_usd_yr)) best = alt;
      if (mid(alt.saves_usd_yr) > 0 && (!itemBest || mid(alt.saves_usd_yr) > mid(itemBest.saves_usd_yr))) itemBest = alt;
    }
    if (itemBest) {
      saveAll += mid(itemBest.saves_usd_yr);
      installAll += mid(itemBest.cost_usd);
      fixes += 1;
    }
  }
  const sources = [...bySource.entries()].sort((a, b) => b[1] - a[1]);
  const heat = sources.reduce((sum, [, kwh]) => sum + kwh, 0);
  return {
    sid,
    name,
    status: "audited",
    cost: mid(energy.total_usd_yr),
    heat,
    topSource: sources.length ? `${labelText(sources[0][0])}s ${Math.round((sources[0][1] / heat) * 100)}%` : null,
    bestFix: best,
    saveAll,
    installAll,
    fixes,
    buildingUnits,
  };
}

export function BuildingView() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const group = useMemo(
    () => groupModels(state.testModels).find((g) => g.key === state.buildingView) ?? null,
    [state.buildingView, state.testModels],
  );
  const [units, setUnits] = useState<UnitData[] | null>(null);

  useEffect(() => {
    if (!group) return undefined;
    let cancelled = false;
    setUnits(null);
    Promise.all(
      group.models.map(async (model) => {
        const name = group.models.length > 1 ? unitName(model) : model.address.split(",")[0];
        let audit: AuditResponse | null = null;
        let energy: AssetEnergyResponse | null = null;
        try {
          audit = await getAudit(model.sid);
        } catch (error) {
          if (!(error instanceof ApiFailure && error.status === 404)) {
            return { sid: model.sid, name, status: "error", cost: 0, heat: 0, topSource: null, bestFix: null, saveAll: 0, installAll: 0, fixes: 0, buildingUnits: null } as UnitData;
          }
        }
        if (audit && audit.status.status === "completed") {
          try {
            energy = await getAssetEnergy(model.sid);
          } catch {
            energy = null;
          }
        }
        return summarize(model.sid, name, audit, energy);
      }),
    ).then((rows) => {
      if (!cancelled) setUnits(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [group]);

  if (!group) return null;
  const audited = (units ?? []).filter((u) => u.status === "audited").sort((a, b) => b.cost - a.cost);
  const others = (units ?? []).filter((u) => u.status !== "audited");
  const avgCost = audited.length ? audited.reduce((s, u) => s + u.cost, 0) / audited.length : 0;
  const buildingUnits = (units ?? []).map((u) => u.buildingUnits).find((n) => n !== null) ?? null;
  const scale = buildingUnits ?? audited.length; // whole building when its unit count is known
  const spend = avgCost * scale;
  const avgSave = audited.length ? audited.reduce((s, u) => s + u.saveAll, 0) / audited.length : 0;
  const avgInstall = audited.length ? audited.reduce((s, u) => s + u.installAll, 0) / audited.length : 0;
  const save = avgSave * scale;
  const install = avgInstall * scale;
  const share = spend > 0 ? Math.min(1, save / spend) : 0;
  const payback = save > 0 ? install / save : null;
  const maxCost = audited[0]?.cost ?? 1;
  const open = (sid: string) => {
    dispatch({ type: "selectSid", sid });
    dispatch({ type: "view", view: "3d" });
  };

  return (
    <div className="building-view">
      <header className="bv-head">
        <p className="bv-kicker">Building overview</p>
        <h2>{group.street}</h2>
        <p className="bv-sub">
          Los Angeles · {group.models.length} unit{group.models.length === 1 ? "" : "s"} scanned
          {buildingUnits ? ` · ${buildingUnits} units in the building` : ""} · {audited.length} audited
        </p>
      </header>

      {units === null ? (
        <div className="bv-loading">Loading the units…</div>
      ) : (
        <>
          {audited.length ? (
            <section className="bv-money" aria-label="What the building spends and could save">
              <div className="bv-money-row">
                <div className="bv-money-item">
                  <span className="bv-total-label">{buildingUnits ? "The building spends" : "These units spend"}</span>
                  <span className="bv-money-value">≈ {money(spend)}</span>
                  <span className="bv-total-unit">a year on energy{buildingUnits ? `, ${buildingUnits} units` : ""}</span>
                </div>
                <span className="bv-money-arrow" aria-hidden="true">→</span>
                <div className="bv-money-item">
                  <span className="bv-total-label">Smart upgrades could save</span>
                  <span className="bv-money-value bv-save">≈ {money(save)}</span>
                  <span className="bv-total-unit">
                    a year ({Math.round(share * 100)}% less)
                    {install > 0 ? ` · ≈ ${money(install)} to install` : ""}
                    {payback !== null && install > 0 ? ` · pays back in ${formatPayback([payback, payback])}` : ""}
                  </span>
                </div>
              </div>
              <div className="bv-money-bar" aria-hidden="true">
                <span className="bv-money-keep" style={{ flexGrow: 1 - share }} />
                <span className="bv-money-saved" style={{ flexGrow: share }} />
              </div>
              <p className="bv-money-note">
                Based on {audited.length} audited unit{audited.length === 1 ? "" : "s"} (average {money(avgCost)} a year each)
                {buildingUnits ? `, scaled to all ${buildingUnits} units` : ""}. The best upgrade for each item, from the
                upgrade library.
              </p>
            </section>
          ) : (
            <p className="bv-money-note">Audit a unit to see what this building spends and could save.</p>
          )}

          <ol className="bv-units">
            {audited.map((unit, index) => (
              <li key={unit.sid}>
                <button type="button" className="bv-unit" onClick={() => open(unit.sid)}>
                  <span className="bv-rank">{index + 1}</span>
                  <span className="bv-unit-main">
                    <span className="bv-unit-name">{unit.name}</span>
                    <span className="bv-unit-detail">
                      {Math.round(unit.heat).toLocaleString()} kWh of heat a year
                      {unit.topSource ? ` · mostly ${unit.topSource.toLowerCase()}` : ""}
                    </span>
                    <span className="bv-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(4, (unit.cost / maxCost) * 100)}%` }} />
                    </span>
                  </span>
                  <span className="bv-unit-fix">
                    {unit.bestFix ? (
                      <>
                        <span className="bv-fix-title">Top fix: {unit.bestFix.title}</span>
                        <span className="bv-fix-detail">
                          {unit.fixes > 1
                            ? `${unit.fixes} upgrades save ${money(unit.saveAll)}/yr`
                            : `saves ${money(mid(unit.bestFix.saves_usd_yr))}/yr`}
                          {unit.fixes <= 1 && unit.bestFix.payback_years ? ` · pays back in ${formatPayback(unit.bestFix.payback_years)}` : ""}
                        </span>
                      </>
                    ) : (
                      <span className="bv-fix-detail">No fix in the library yet</span>
                    )}
                  </span>
                  <span className="bv-unit-cost">
                    {money(unit.cost)}
                    <small>/yr</small>
                  </span>
                </button>
              </li>
            ))}
          </ol>

          {others.length ? (
            <div className="bv-others">
              <p className="bv-others-title">Not audited yet</p>
              <ul>
                {others.map((unit) => (
                  <li key={unit.sid}>
                    <button type="button" className="bv-other" onClick={() => open(unit.sid)}>
                      <span>{unit.name}</span>
                      <span className="bv-other-status">
                        {unit.status === "running" ? "Auditing…" : unit.status === "error" ? "Could not load" : "Open to audit →"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
