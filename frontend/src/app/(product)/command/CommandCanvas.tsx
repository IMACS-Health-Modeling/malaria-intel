"use client";

import { useMemo, useState } from "react";
import { KPICard } from "@/components/ui/KPICard";
import { ThreatTicker } from "@/components/ui/ThreatTicker";
import { GlobalMap } from "@/components/command/GlobalMap";
import { BurdenTable } from "@/components/command/BurdenTable";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { color } from "@/lib/tokens";
import type {
  GlobalSummary,
  CommandCountrySummary,
  ThreatEvent,
  GlobalTimeseriesPoint,
  EndemicBoundaries,
} from "@/lib/data";

type Props = {
  summary: GlobalSummary;
  countries: CommandCountrySummary[];
  threats: ThreatEvent[];
  timeseries: GlobalTimeseriesPoint[];
  boundaries: EndemicBoundaries;
};

function fmt(n: number, suffix = ""): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B${suffix}`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M${suffix}`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K${suffix}`;
  return `${n}${suffix}`;
}

export function CommandCanvas({ summary, countries, threats, timeseries, boundaries }: Props) {
  const g = summary.global;

  const dciSignal = useMemo(() => {
    const withDci = threats.filter((t) => t.dci_score !== null && t.dci_score >= 0.3);
    const critical = withDci.filter((t) => (t.dci_score ?? 0) >= 0.8).length;
    const high     = withDci.filter((t) => (t.dci_score ?? 0) >= 0.6 && (t.dci_score ?? 0) < 0.8).length;
    const moderate = withDci.filter((t) => (t.dci_score ?? 0) >= 0.3 && (t.dci_score ?? 0) < 0.6).length;
    const affected = new Set(withDci.map((t) => t.country_iso3)).size;
    return { total: withDci.length, critical, high, moderate, countries: affected };
  }, [threats]);

  const [sidebarFilter, setSidebarFilter] = useState<"all" | "alert" | string>("all");

  const regions = useMemo(() => {
    const rs = new Set(countries.map((c) => c.region).filter(Boolean) as string[]);
    return Array.from(rs).sort();
  }, [countries]);

  const filteredCountries = useMemo(() => {
    const sorted = [...countries].sort((a, b) => b.cases - a.cases);
    if (sidebarFilter === "all") return sorted;
    if (sidebarFilter === "alert")
      return sorted.filter(
        (c) => c.alert_level === "critical" || c.alert_level === "extreme" || c.alert_level === "high"
      );
    return sorted.filter((c) => c.region === sidebarFilter);
  }, [countries, sidebarFilter]);

  // suppress timeseries unused warning until we add a chart
  void timeseries;

  return (
    <div className="flex flex-col h-full">
      {/* Threat Ticker */}
      <ThreatTicker events={threats} />

      {/* Attribution bar */}
      <div className="px-4 py-1 bg-surface-1 border-b border-surface-3 flex items-center justify-between">
        <p className="text-2xs text-txt-muted">Decision Intelligence</p>
        <p className="text-2xs text-txt-muted font-mono">WHO WMR 2024 · GF API v4 · NASA Power</p>
      </div>

      {/* KPI Bar */}
      <div className="grid grid-cols-6 gap-3 px-4 py-3 border-b border-surface-3 bg-surface-1">
        <KPICard
          label="Est. Cases"
          value={fmt(g.estimated_cases)}
          subvalue="Latest · WHO WMR 2024"
          change={g.cases_change_yoy}
          changeLabel="YoY"
          glowColor="rgba(249, 93, 47, 0.12)"
        />
        <KPICard
          label="Est. Deaths"
          value={fmt(g.estimated_deaths)}
          subvalue="Latest · WHO WMR 2024"
          change={g.deaths_change_yoy}
          changeLabel="YoY"
          glowColor="rgba(239, 68, 68, 0.12)"
        />
        <KPICard
          label="Endemic Countries"
          value={String(g.countries_endemic)}
          subvalue={`${g.countries_in_alert} in alert · WHO GHO 2023`}
          glowColor="rgba(250, 204, 21, 0.10)"
        />
        <KPICard
          label="Total Funding"
          value={g.total_funding_usd ? `$${(g.total_funding_usd / 1e9).toFixed(1)}B` : "—"}
          subvalue="Global Fund API · 2023"
          glowColor="rgba(247, 165, 29, 0.12)"
        />
        <KPICard
          label="Financing Gap"
          value={`$${(g.funding_gap_usd / 1e9).toFixed(1)}B`}
          subvalue="vs annual need · WHO GTS 2021 rev."
          glowColor="rgba(22, 163, 74, 0.10)"
        />
        <div className="glass-panel px-4 py-3 flex flex-col justify-between col-span-1">
          <div className="flex items-center gap-1 mb-1">
            <p className="text-2xs text-txt-muted font-medium uppercase tracking-wider">
              Active DCI Risk
            </p>
            <InfoTooltip
              title="Diagnostic Confusion Index (DCI) — Global Signal"
              body="Active concurrent febrile outbreaks that overlap with malaria-endemic zones, creating misdiagnosis risk. DCI ≥ 0.8 = Critical. DCI 0.6–0.8 = High. DCI 0.3–0.6 = Moderate. This signal is unique to MalariaScope — no other platform computes diagnostic interference as a transmission risk amplifier."
              side="left"
            />
          </div>
          <p className="text-xl font-display font-semibold text-txt-primary tabular-nums leading-tight">
            {dciSignal.countries}{" "}
            <span className="text-sm font-normal text-txt-muted">countries</span>
          </p>
          <p className="text-2xs text-txt-muted mt-0.5">MalariaScope · DCI model</p>
          <div className="flex items-center gap-2 mt-1">
            {dciSignal.critical > 0 && (
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded-full bg-uncertainty-very-high/15 text-uncertainty-very-high font-semibold">
                {dciSignal.critical} critical
              </span>
            )}
            {dciSignal.high > 0 && (
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded-full bg-uncertainty-high/15 text-uncertainty-high">
                {dciSignal.high} high
              </span>
            )}
            {dciSignal.moderate > 0 && (
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded-full bg-uncertainty-moderate/15 text-uncertainty-moderate">
                {dciSignal.moderate} mod
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main content: Map + Sidebar */}
      <div className="flex flex-1 overflow-hidden">
        {/* Map — 65% */}
        <div className="flex-[65] relative">
          <GlobalMap
            countries={countries}
            threats={threats}
            boundaries={boundaries}
          />

          {/* Legend */}
          <div className="absolute bottom-4 left-4 glass-panel px-3 py-2.5 flex flex-col gap-2">
            <p className="text-2xs text-txt-muted font-medium uppercase tracking-wider">
              Burden (incidence/1,000) · WHO WMR 2024
            </p>
            <div className="flex items-center gap-2">
              {[
                { label: ">300",    color: color.uncertainty.very_high },
                { label: "150-300", color: color.uncertainty.high },
                { label: "50-150",  color: color.uncertainty.moderate },
                { label: "<50",     color: color.uncertainty.low },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color, opacity: 0.55 }} />
                  <span className="text-2xs text-txt-muted">{item.label}</span>
                </div>
              ))}
            </div>
            <p className="text-2xs text-txt-muted font-medium uppercase tracking-wider mt-1">
              Active Threats
            </p>
            <div className="flex items-center gap-2">
              {[
                { label: "Arbovirus",   color: color.signal.arbovirus },
                { label: "Hemorrhagic", color: color.uncertainty.very_high },
                { label: "Bacterial",   color: "#a78bfa" },
                { label: "Conflict",    color: color.signal.conflict },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1">
                  <span
                    className="w-2 h-2 rounded-full border"
                    style={{ borderColor: item.color, backgroundColor: `${item.color}40` }}
                  />
                  <span className="text-2xs text-txt-muted">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Sidebar — 35% */}
        <div className="flex-[35] border-l border-surface-3 bg-surface-1 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-surface-3">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-display font-semibold text-txt-primary">
                {sidebarFilter === "all"
                  ? "Highest Burden"
                  : sidebarFilter === "alert"
                  ? "Countries in Alert"
                  : sidebarFilter}
              </h2>
              <span className="text-2xs text-txt-muted font-mono">{filteredCountries.length} countries</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {(["all", "alert"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setSidebarFilter(f)}
                  className={`text-2xs px-2 py-0.5 rounded-pill border transition-colors cursor-pointer ${
                    sidebarFilter === f
                      ? "bg-signal-malaria/15 border-signal-malaria/40 text-signal-malaria font-medium"
                      : "border-surface-3 text-txt-muted hover:text-txt-primary"
                  }`}
                >
                  {f === "all" ? "All" : "⚠ Alert"}
                </button>
              ))}
              {regions.map((r) => (
                <button
                  key={r}
                  onClick={() => setSidebarFilter(r)}
                  className={`text-2xs px-2 py-0.5 rounded-pill border transition-colors cursor-pointer ${
                    sidebarFilter === r
                      ? "bg-signal-climate/15 border-signal-climate/40 text-signal-climate font-medium"
                      : "border-surface-3 text-txt-muted hover:text-txt-primary"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <BurdenTable countries={filteredCountries} className="flex-1" />
        </div>
      </div>
    </div>
  );
}
