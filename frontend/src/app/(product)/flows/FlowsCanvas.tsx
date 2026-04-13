"use client";

import { useEffect, useRef, useState } from "react";
import { geoNaturalEarth1, geoPath } from "d3";
import * as topojson from "topojson-client";
import { ChapterHero } from "@/components/ui/ChapterHero";
import type { WorldMapData, CountryFlow } from "@/lib/data";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  return (n / 1e6).toFixed(0) + "M";
}

function fmtNum(n: number): string {
  return n.toLocaleString();
}

// ── Colour scale ──────────────────────────────────────────────────────────────

const NAVY_STEPS = ["#c8d5ee", "#8daad8", "#5280c0", "#2a5aaa", "#1d499e"];
const HIGHLIGHT = "#1d499e";

function getColor(value: number, max: number): string {
  if (max === 0) return NAVY_STEPS[0];
  const pct = value / max;
  const idx = Math.min(4, Math.floor(pct * 5));
  return NAVY_STEPS[idx];
}

// ── ISO3 ↔ ISO numeric mapping (ISO 3166-1 numeric) ──────────────────────────
// Covers all 27 PMI/GF countries in world-map.json

const ISO3_TO_NUM: Record<string, number> = {
  MOZ: 508, TZA: 834, NGA: 566, ETH: 231, UGA: 800,
  KEN: 404, GHA: 288, MDG: 450, MWI: 454, ZMB: 894,
  COD: 180, MLI: 466, SEN: 686, CMR: 120, BFA: 854,
  GIN: 324, ZWE: 716, RWA: 646, TGO: 768, BEN: 204,
  SDN: 729, AGO:  24, LSO: 426, SWZ: 748, MMR: 104,
  PNG: 598, HTI: 332,
};

const NUM_TO_ISO3: Record<number, string> = Object.fromEntries(
  Object.entries(ISO3_TO_NUM).map(([k, v]) => [v, k])
);

// ── Program chip ──────────────────────────────────────────────────────────────

function programChipClass(program: string): string {
  if (program === "PMI")         return "bg-accent-orange/10 text-accent-orange border border-accent-orange/20";
  if (program === "Global Fund") return "bg-accent-navy/10 text-accent-navy border border-accent-navy/20";
  if (program === "PEPFAR")      return "bg-accent-teal/10 text-accent-teal border border-accent-teal/20";
  return "bg-surface-2 text-txt-muted border border-surface-3";
}

// ── Topojson type shim ────────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type WorldTopo = any;

// ── Component ─────────────────────────────────────────────────────────────────

type MapView = "allocation" | "actual";

export function FlowsCanvas({ data }: { data: WorldMapData }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims]                 = useState({ width: 900, height: 560 });
  const [topo, setTopo]                 = useState<WorldTopo>(null);
  const [selectedCountry, setSelectedCountry] = useState<CountryFlow | null>(null);
  const [hoveredISO, setHoveredISO]     = useState<string | null>(null);
  const [mapView, setMapView]           = useState<MapView>("allocation");

  const flowsByISO = Object.fromEntries(data.flows.map((f) => [f.iso3, f]));

  const getValue = (f: CountryFlow) =>
    mapView === "actual" ? (f.usaspending_actual_usd ?? 0) : f.us_allocation_usd;

  const maxAlloc   = Math.max(...data.flows.map((f) => f.us_allocation_usd));
  const maxActual  = Math.max(...data.flows.map((f) => f.usaspending_actual_usd ?? 0));
  const maxVal     = mapView === "actual" ? maxActual : maxAlloc;

  const top10      = [...data.flows]
    .sort((a, b) => getValue(b) - getValue(a))
    .filter((f) => getValue(f) > 0)
    .slice(0, 10);

  // Fetch world-atlas 110m topojson (~680KB, fast CDN)
  useEffect(() => {
    fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json")
      .then((r) => r.json())
      .then(setTopo)
      .catch(() => {});
  }, []);

  // Track container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const e = entries[0];
      if (e) setDims({ width: e.contentRect.width, height: e.contentRect.height });
    });
    ro.observe(el);
    if (el.clientWidth > 0) setDims({ width: el.clientWidth, height: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // Build SVG path list
  const paths = (() => {
    if (!topo || dims.width === 0) return [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const countries = topojson.feature(topo, topo.objects.countries) as any;
    const projection = geoNaturalEarth1().fitSize([dims.width, dims.height], countries);
    const pathGen    = geoPath(projection);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (countries.features as any[]).map((feat: any) => {
      const numId = Number(feat.id);
      const iso3  = NUM_TO_ISO3[numId] ?? null;
      const flow  = iso3 ? (flowsByISO[iso3] ?? null) : null;
      const fill  = flow ? getColor(getValue(flow), maxVal) : "#e8edf4";
      return { d: pathGen(feat) ?? "", iso3, flow, fill };
    });
  })();

  return (
    <div className="flex h-full w-full">
      {/* ── LEFT: SVG world map ── */}
      <div ref={containerRef} className="flex-1 relative bg-[#f4f7fb] min-h-0">
        {!topo && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="font-mono text-sm text-txt-muted animate-pulse">Loading world map…</p>
          </div>
        )}

        <svg
          viewBox={`0 0 ${dims.width} ${dims.height}`}
          preserveAspectRatio="xMidYMid meet"
          className="w-full h-full"
        >
          {paths.map(({ d, iso3, flow, fill }, i) => {
            const isHovered = hoveredISO !== null && hoveredISO === iso3;
            return (
              <path
                key={i}
                d={d}
                fill={isHovered && flow ? HIGHLIGHT : fill}
                stroke={flow ? "#ffffff" : "#dde5f0"}
                strokeWidth={flow ? 0.6 : 0.4}
                style={{ cursor: flow ? "pointer" : "default", transition: "fill 0.12s" }}
                onMouseEnter={() => iso3 && setHoveredISO(iso3)}
                onMouseLeave={() => setHoveredISO(null)}
                onClick={() => flow && setSelectedCountry(flow)}
              >
                {iso3 && <title>{flow?.name ?? iso3}</title>}
              </path>
            );
          })}
        </svg>

        {/* Toggle */}
        <div className="absolute top-4 right-4 flex rounded-badge border border-surface-3 bg-white/90 backdrop-blur-sm shadow-card overflow-hidden">
          {(["allocation", "actual"] as MapView[]).map((v) => (
            <button
              key={v}
              onClick={() => setMapView(v)}
              className="px-3 py-1.5 text-2xs font-mono transition-colors"
              style={{
                background: mapView === v ? "#1d499e" : "transparent",
                color: mapView === v ? "white" : "#6b7a8d",
              }}
            >
              {v === "allocation" ? "PMI Allocation" : "USAID Actual"}
            </button>
          ))}
        </div>

        {/* Colour legend */}
        <div className="absolute bottom-5 left-4 bg-white/90 backdrop-blur-sm border border-surface-3 rounded-panel px-3 py-2 shadow-card">
          <p className="text-2xs font-mono text-txt-muted uppercase tracking-wider mb-1.5">
            {mapView === "allocation" ? "PMI Allocation" : "USAID Actual Spend"}
          </p>
          <div className="flex items-center gap-1">
            {NAVY_STEPS.map((c, i) => (
              <div key={i} className="w-6 h-3 rounded-micro" style={{ backgroundColor: c }} />
            ))}
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-2xs font-mono text-txt-muted">Low</span>
            <span className="text-2xs font-mono text-txt-muted">
              {mapView === "allocation" ? "$195M+" : `$${Math.round(maxActual / 1e6)}M+`}
            </span>
          </div>
        </div>

        {/* Country count badge */}
        <div className="absolute top-4 left-4 bg-white/90 backdrop-blur-sm border border-surface-3 rounded-badge px-3 py-1.5 shadow-card">
          <span className="text-2xs font-mono text-txt-muted">
            <span className="text-accent-navy font-semibold">{data.flows.length}</span> PMI priority countries
          </span>
        </div>
      </div>

      {/* ── RIGHT: Sidebar ── */}
      <div className="w-[380px] flex flex-col h-full border-l border-surface-3 bg-white shrink-0">
        {/* Chapter header — stays visible while content below scrolls */}
        <ChapterHero
          eyebrow="Chapter 02 — The Deployment"
          headline="WHERE EVERY DOLLAR GOES"
          subheadline="27 PMI priority countries receive US malaria investment. Click any highlighted country to explore allocation, burden, and active programs."
          accentColor="#1d499e"
        />

        {/* Scrollable content below the chapter header */}
        <div className="flex-1 flex flex-col overflow-y-auto min-h-0">

        {/* Aggregate KPI strip */}
        {selectedCountry === null && (
          <div className="grid grid-cols-2 gap-2 px-6 py-4 border-b border-surface-3 bg-surface-1">
            {[
              { label: "Total US Allocation", value: `$${(data.flows.reduce((s, f) => s + f.us_allocation_usd, 0) / 1e9).toFixed(1)}B` },
              { label: "PMI Countries", value: String(data.flows.length) },
              { label: "Total Cases (2023)", value: `${(data.flows.reduce((s, f) => s + f.malaria_cases, 0) / 1e6).toFixed(0)}M` },
              { label: "Total Deaths (2023)", value: `${(data.flows.reduce((s, f) => s + f.malaria_deaths, 0) / 1e3).toFixed(0)}K` },
            ].map((kpi) => (
              <div key={kpi.label} className="bg-white rounded-panel px-3 py-2 border border-surface-3">
                <p className="text-2xs font-mono text-txt-muted uppercase tracking-[0.1em] mb-0.5">{kpi.label}</p>
                <p className="text-base font-mono font-bold text-txt-primary">{kpi.value}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex-1 px-6 py-6">
          {selectedCountry === null ? (
            /* Top Recipients List */
            <div>
              <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted mb-4">
                Top Recipients — {mapView === "allocation" ? "PMI Allocation" : "USAID Actual (2019–2024)"}
              </p>
              <div className="flex flex-col gap-3">
                {top10.map((country, i) => {
                  const val = getValue(country);
                  const barPct = (val / maxVal) * 100;
                  return (
                    <button
                      key={country.iso3}
                      onClick={() => setSelectedCountry(country)}
                      className="flex items-center gap-3 text-left hover:bg-surface-1 -mx-2 px-2 py-1 rounded-badge transition-colors group"
                    >
                      <span className="font-mono text-2xs text-txt-muted w-4 shrink-0 text-right">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-txt-primary truncate mb-1 group-hover:text-accent-navy transition-colors">
                          {country.name}
                        </p>
                        <div className="h-1.5 w-full bg-accent-navy/10 rounded-pill overflow-hidden">
                          <div
                            className="h-full bg-accent-navy rounded-pill"
                            style={{ width: `${barPct}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-2xs font-mono text-txt-muted shrink-0">
                        ${fmtUSD(val)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Country Detail Card */
            <div className="animate-fade-in">
              <button
                onClick={() => setSelectedCountry(null)}
                className="flex items-center gap-1 text-2xs font-mono text-txt-muted hover:text-txt-primary mb-5 transition-colors"
              >
                ← Back to list
              </button>

              <h2 className="text-xl font-bold text-txt-primary mb-1">{selectedCountry.name}</h2>
              <div className="flex items-center gap-4 mb-5">
                <p className="text-sm font-mono text-accent-orange">
                  PMI Allocation: ${fmtUSD(selectedCountry.us_allocation_usd)}
                </p>
                {(selectedCountry.usaspending_actual_usd ?? 0) > 0 && (
                  <p className="text-sm font-mono text-accent-teal">
                    USAID Actual: ${fmtUSD(selectedCountry.usaspending_actual_usd!)}
                  </p>
                )}
              </div>

              {/* Burden */}
              <div className="mb-5 p-4 bg-surface-1 rounded-panel border border-surface-3">
                <p className="text-2xs font-mono uppercase tracking-wider text-txt-muted mb-3">
                  Malaria Burden
                </p>
                <div className="flex gap-4">
                  <div className="flex-1">
                    <p className="text-2xs font-mono text-txt-muted mb-0.5">Cases</p>
                    <p className="text-sm font-mono font-medium text-txt-primary">
                      {fmtNum(selectedCountry.malaria_cases)}
                    </p>
                  </div>
                  <div className="flex-1">
                    <p className="text-2xs font-mono text-txt-muted mb-0.5">Deaths</p>
                    <p className="text-sm font-mono font-medium text-txt-primary">
                      {fmtNum(selectedCountry.malaria_deaths)}
                    </p>
                  </div>
                </div>
              </div>

              {/* GF disbursed */}
              {selectedCountry.gf_disbursed_usd != null && selectedCountry.gf_disbursed_usd > 0 && (
                <div className="mb-5 p-4 bg-surface-1 rounded-panel border border-surface-3">
                  <p className="text-2xs font-mono uppercase tracking-wider text-txt-muted mb-3">
                    Global Fund (Malaria)
                  </p>
                  <div className="flex gap-4">
                    <div className="flex-1">
                      <p className="text-2xs font-mono text-txt-muted mb-0.5">Disbursed</p>
                      <p className="text-sm font-mono font-medium text-accent-teal">
                        ${fmtUSD(selectedCountry.gf_disbursed_usd)}
                      </p>
                    </div>
                    {selectedCountry.gf_committed_usd != null && selectedCountry.gf_committed_usd > 0 && (
                      <div className="flex-1">
                        <p className="text-2xs font-mono text-txt-muted mb-0.5">Committed</p>
                        <p className="text-sm font-mono font-medium text-txt-secondary">
                          ${fmtUSD(selectedCountry.gf_committed_usd)}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Programs */}
              <div className="mb-5">
                <p className="text-2xs font-mono uppercase tracking-wider text-txt-muted mb-2">
                  Active Programs
                </p>
                <div className="flex flex-wrap gap-2">
                  {selectedCountry.programs.map((p) => (
                    <span
                      key={p}
                      className={`text-2xs font-mono px-2 py-1 rounded-badge ${programChipClass(p)}`}
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>

              {/* Funding vs Burden */}
              <div className="p-4 bg-surface-1 rounded-panel border border-surface-3">
                <p className="text-2xs font-mono uppercase tracking-wider text-txt-muted mb-3">
                  Funding vs Burden
                </p>
                <div className="flex gap-4 mb-3">
                  <div className="flex-1">
                    <p className="text-2xs font-mono text-txt-muted mb-0.5">Funding Rank</p>
                    <p className="text-lg font-mono font-bold text-accent-navy">
                      #{selectedCountry.funding_rank}
                    </p>
                  </div>
                  <div className="flex-1">
                    <p className="text-2xs font-mono text-txt-muted mb-0.5">Burden Rank</p>
                    <p className="text-lg font-mono font-bold text-signal-malaria">
                      #{selectedCountry.burden_rank}
                    </p>
                  </div>
                </div>
                {selectedCountry.burden_rank > selectedCountry.funding_rank ? (
                  <div className="flex items-center gap-2 text-2xs font-mono text-amber-600 bg-amber-50 border border-amber-200 rounded-badge px-3 py-2">
                    <span>⚠</span>
                    <span>Underfunded relative to burden</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-2xs font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-badge px-3 py-2">
                    <span>✓</span>
                    <span>Well-funded relative to burden</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-surface-3 bg-surface-1">
          <p className="text-2xs font-mono text-txt-muted leading-relaxed">
            Does the money match the burden? Compare funding rank vs malaria burden rank. Click any country on the map or list to explore.
          </p>
        </div>

        </div> {/* end scrollable content */}
      </div>
    </div>
  );
}
