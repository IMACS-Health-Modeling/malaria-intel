"use client";

import { useMemo, useRef, useState, useEffect, useCallback } from "react";
import MapGL, { Source, Layer, NavigationControl } from "react-map-gl/mapbox";
import type { MapMouseEvent, MapRef, LayerProps } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";
import type { USEcosystemData, StateData, TopContractor } from "@/lib/data";
import { X, MapPin, FlaskConical, Building2, Globe } from "lucide-react";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { METRIC_META } from "@/lib/metric-metadata";
import type { MetricMeta } from "@/lib/metric-metadata";

// ── Constants ─────────────────────────────────────────────────────────────────

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN!;
const GEO_URL = "/data/us-ecosystem/us-states.json";
const MAP_STYLE = "mapbox://styles/mapbox/light-v11";

/** 5-step purple → orange → deep red choropleth */
const COLOR_STEPS = ["#c8b4e8", "#9b7ed4", "#e67a3c", "#d44f2a", "#c0392b"];
const NO_DATA_FILL = "#ede9f5";
const HOVER_FILL = "#7c3aed";
const BORDER_COLOR = "#6b7280";

const LEGEND_LABELS = ["<$10M", "$10–50M", "$50–150M", "$150–300M", "$300M+"];

const ORG_TYPE_COLORS: Record<string, string> = {
  University: "#1d499e",
  NGO: "#19bdc3",
  "Non-profit": "#19bdc3",
  "For-profit contractor": "#ED7238",
  Contractor: "#ED7238",
  Multilateral: "#8daad8",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n}`;
}

/** Map NIH funding to a choropleth color */
function getFillColor(nihUSD: number): string {
  if (nihUSD <= 0) return NO_DATA_FILL;
  if (nihUSD < 10_000_000) return COLOR_STEPS[0];
  if (nihUSD < 50_000_000) return COLOR_STEPS[1];
  if (nihUSD < 150_000_000) return COLOR_STEPS[2];
  if (nihUSD < 300_000_000) return COLOR_STEPS[3];
  return COLOR_STEPS[4];
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KPICard({ label, value, sub, accent, meta }: {
  label: string; value: string; sub?: string; accent?: string; meta?: MetricMeta;
}) {
  return (
    <div className="bg-white border border-surface-3 rounded-panel px-4 py-3 flex-1 min-w-0 shadow-sm">
      <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted mb-1 truncate">{label}</p>
      <div className="flex items-center">
        <p
          className="text-xl font-mono font-semibold text-txt-primary"
          style={accent ? { color: accent } : {}}
        >
          {value}
        </p>
        {meta && <InfoTooltip meta={meta} size={10} />}
      </div>
      {sub && <p className="text-2xs font-mono text-txt-muted mt-0.5 truncate">{sub}</p>}
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span
      className="text-2xs font-mono px-1.5 py-0.5 rounded-badge text-white font-medium whitespace-nowrap"
      style={{ backgroundColor: ORG_TYPE_COLORS[type] ?? "#777" }}
    >
      {type}
    </span>
  );
}

function MapLegend() {
  return (
    <div className="flex items-center gap-3 px-6 py-2.5 flex-wrap bg-white border-t border-surface-3">
      <span className="text-2xs font-mono text-txt-muted mr-1 shrink-0">NIH Funding:</span>
      <div className="flex items-center gap-1">
        <div className="w-4 h-3 rounded-micro border border-surface-3" style={{ backgroundColor: NO_DATA_FILL }} />
        <span className="text-2xs font-mono text-txt-muted">No data</span>
      </div>
      {COLOR_STEPS.map((color, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className="w-4 h-3 rounded-micro" style={{ backgroundColor: color }} />
          <span className="text-2xs font-mono text-txt-muted">{LEGEND_LABELS[i]}</span>
        </div>
      ))}
    </div>
  );
}

function HoverTooltip({ name, data, x, y, containerW }: {
  name: string; data: StateData | null; x: number; y: number; containerW: number;
}) {
  const tooltipW = 200;
  const left = x + 16 + tooltipW > containerW ? x - tooltipW - 8 : x + 14;
  return (
    <div
      className="pointer-events-none absolute z-20 bg-white border border-surface-3 rounded-panel shadow-overlay px-3 py-2.5"
      style={{ left, top: y - 10, transform: "translateY(-50%)", minWidth: 160 }}
    >
      <p className="text-xs font-semibold text-txt-primary mb-1.5">{name}</p>
      {data ? (
        <div className="space-y-0.5">
          <p className="text-2xs font-mono text-txt-muted">
            NIH: <span className="text-txt-secondary font-medium">{fmtUSD(data.nih_grants_usd)}</span>
          </p>
          <p className="text-2xs font-mono text-txt-muted">
            Federal: <span className="text-txt-secondary font-medium">{fmtUSD(data.usaspending_usd)}</span>
          </p>
          <p className="text-2xs font-mono text-txt-muted">
            {data.org_count} orgs · {data.clinical_trials} trials
          </p>
          <p className="text-2xs font-mono mt-1" style={{ color: "#9b7ed4" }}>
            Click to explore →
          </p>
        </div>
      ) : (
        <p className="text-2xs font-mono text-txt-muted">No data available</p>
      )}
    </div>
  );
}

function StatePopup({ summary, onClose }: { summary: StateData; onClose: () => void }) {
  const [detail, setDetail] = useState<StateData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    setLoading(true); setDetail(null);
    let cancelled = false;
    fetch(`/data/us-ecosystem/state-detail/${summary.code}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled) { setDetail(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [summary.code]);

  const data = detail ?? summary;
  const orgs = data.top_orgs ?? [];
  const totalFunding = data.nih_grants_usd + data.usaspending_usd;

  return (
    <div
      className="absolute inset-0 z-30 flex items-center justify-center"
      style={{ background: "rgba(15, 25, 40, 0.45)", backdropFilter: "blur(2px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog" aria-modal="true"
        className="bg-white rounded-panel shadow-overlay w-[520px] max-h-[80vh] flex flex-col overflow-hidden"
        style={{ animation: "fadeInUp 0.18s ease-out" }}
      >
        <div className="px-6 pt-5 pb-4 border-b border-surface-3 flex items-start justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <MapPin size={14} style={{ color: "#9b7ed4" }} className="shrink-0" />
              <p className="text-2xs font-mono uppercase tracking-[0.14em] text-txt-muted">US Ecosystem</p>
            </div>
            <h2 className="text-2xl font-bold text-txt-primary leading-tight">{data.name}</h2>
            <p className="text-xs text-txt-muted mt-1 font-mono">
              {data.org_count} organizations across {data.countries_reached} countries
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-panel hover:bg-surface-2 text-txt-muted hover:text-txt-primary transition-colors mt-0.5 shrink-0">
            <X size={16} />
          </button>
        </div>

        <div className="grid grid-cols-4 gap-0 border-b border-surface-3 shrink-0">
          {[
            { icon: <FlaskConical size={13} />, label: "NIH Grants", value: fmtUSD(data.nih_grants_usd), color: "#9b7ed4", meta: METRIC_META.nih_grants_state },
            { icon: <Building2 size={13} />, label: "Federal Awards", value: fmtUSD(data.usaspending_usd), color: "#ED7238", meta: METRIC_META.usaspending_state },
            { icon: <FlaskConical size={13} />, label: "Clinical Trials", value: String(data.clinical_trials), color: "#e67a3c", meta: undefined },
            { icon: <Globe size={13} />, label: "Countries", value: String(data.countries_reached), color: "#8daad8", meta: undefined },
          ].map((stat, i) => (
            <div key={i} className="px-4 py-3 text-center border-r last:border-r-0 border-surface-3">
              <div className="flex items-center justify-center gap-1 mb-1" style={{ color: stat.color }}>
                {stat.icon}
                <p className="text-2xs font-mono uppercase tracking-[0.1em] text-txt-muted">{stat.label}</p>
              </div>
              <div className="flex items-center justify-center">
                <p className="text-lg font-mono font-semibold text-txt-primary">{stat.value}</p>
                {stat.meta && <InfoTooltip meta={stat.meta} size={10} />}
              </div>
            </div>
          ))}
        </div>

        <div className="px-6 py-3 border-b border-surface-3 shrink-0">
          <div className="flex items-center justify-between mb-2">
            <p className="text-2xs font-mono text-txt-muted uppercase tracking-[0.1em]">Total Funding Footprint</p>
            <p className="text-xs font-mono font-semibold text-txt-primary">{fmtUSD(totalFunding)}</p>
          </div>
          <div className="flex h-2 rounded-pill overflow-hidden gap-px">
            {totalFunding > 0 && (<>
              <div className="h-full" style={{ width: `${Math.round((data.nih_grants_usd / totalFunding) * 100)}%`, backgroundColor: "#9b7ed4" }} />
              <div className="h-full" style={{ width: `${Math.round((data.usaspending_usd / totalFunding) * 100)}%`, backgroundColor: "#ED7238" }} />
            </>)}
          </div>
          <div className="flex items-center gap-4 mt-1.5">
            <div className="flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: "#9b7ed4" }} />
              <span className="text-2xs font-mono text-txt-muted">NIH Research</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: "#ED7238" }} />
              <span className="text-2xs font-mono text-txt-muted">Federal Field Awards</span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm text-txt-muted animate-pulse font-mono">Loading organizations…</p>
            </div>
          ) : orgs.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm text-txt-muted">No organization detail available.</p>
            </div>
          ) : (
            <>
              <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted px-6 py-3 border-b border-surface-3 sticky top-0 bg-white">
                Key Organizations ({orgs.length})
              </p>
              {orgs.map((org, i) => (
                <div key={`${org.name}-${i}`} className="px-6 py-3 border-b border-surface-3 last:border-b-0 hover:bg-surface-1 transition-colors">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-sm font-medium text-txt-primary leading-snug">{org.name}</span>
                    <TypeBadge type={org.type} />
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-2xs text-txt-muted font-mono truncate max-w-[280px]">{org.countries.join(", ")}</p>
                    <span className="text-xs font-mono text-txt-muted ml-2 shrink-0">{fmtUSD(org.usd)}</span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function OrgTypeBreakdown({ contractors }: { contractors: TopContractor[] }) {
  const groups: Record<string, number> = {};
  for (const c of contractors) {
    const type = c.type === "Non-profit" ? "NGO" : c.type === "Contractor" ? "For-profit contractor" : c.type;
    if (type === "Multilateral") continue;
    groups[type] = (groups[type] ?? 0) + c.amount_usd;
  }
  const entries = Object.entries(groups).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const max = entries[0]?.[1] ?? 1;
  return (
    <div className="px-6 py-4 border-b border-surface-3">
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted">US Partner Type — USAID Awards</p>
        <p className="text-2xs font-mono text-txt-muted">{fmtUSD(total)} total</p>
      </div>
      <div className="space-y-2.5">
        {entries.map(([type, amt]) => {
          const color = ORG_TYPE_COLORS[type] ?? "#999";
          return (
            <div key={type}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <span className="text-xs font-medium text-txt-primary">{type}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xs font-mono text-txt-muted">{Math.round((amt / total) * 100)}%</span>
                  <span className="text-xs font-mono text-txt-secondary font-medium">{fmtUSD(amt)}</span>
                </div>
              </div>
              <div className="h-1.5 bg-surface-3 rounded-pill overflow-hidden">
                <div className="h-full rounded-pill" style={{ width: `${Math.round((amt / max) * 100)}%`, backgroundColor: color }} />
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-2xs text-txt-muted/70 mt-3 font-mono">Excl. multilateral pass-through (Global Fund $11.8B)</p>
    </div>
  );
}

function StateList({ states, maxNIH, onSelect }: {
  states: StateData[]; maxNIH: number; onSelect: (s: StateData) => void;
}) {
  const sorted = [...states]
    .sort((a, b) => (b.nih_grants_usd + b.usaspending_usd) - (a.nih_grants_usd + a.usaspending_usd))
    .slice(0, 35);
  return (
    <div className="flex flex-col">
      <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted px-6 py-3 border-b border-surface-3">
        Top States by Activity — Click to explore
      </p>
      {sorted.map((s) => (
        <button key={s.code} onClick={() => onSelect(s)} className="text-left px-6 py-3 border-b border-surface-3 hover:bg-surface-1 transition-colors group">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-txt-primary group-hover:text-[#9b7ed4] transition-colors">{s.name}</span>
            <span className="text-xs font-mono text-txt-muted">{fmtUSD(s.nih_grants_usd)}</span>
          </div>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xs text-txt-muted font-mono">{s.org_count} orgs</span>
            <span className="text-2xs text-txt-muted font-mono">{s.clinical_trials} trials</span>
            <span className="text-2xs text-txt-muted font-mono">{s.countries_reached} countries</span>
          </div>
          <div className="h-1 bg-surface-3 rounded-pill overflow-hidden">
            <div className="h-full rounded-pill" style={{ width: `${maxNIH > 0 ? Math.round((s.nih_grants_usd / maxNIH) * 100) : 0}%`, backgroundColor: "#9b7ed4" }} />
          </div>
        </button>
      ))}
    </div>
  );
}

function TopContractorsPanel({ contractors }: { contractors: TopContractor[] }) {
  const implementers = contractors.filter((c) => c.rank !== 1);
  const maxAmt = Math.max(...implementers.map((c) => c.amount_usd), 1);
  return (
    <div className="flex flex-col">
      <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted px-6 py-3 border-b border-surface-3">
        Top USAID Implementing Partners (2019–2024)
      </p>
      {implementers.map((c) => {
        const color = ORG_TYPE_COLORS[c.type] ?? "#999";
        return (
          <div key={c.rank} className="px-6 py-3 border-b border-surface-3 hover:bg-surface-1 transition-colors">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-txt-primary truncate max-w-[220px]">{c.name}</span>
              <span className="text-xs font-mono text-txt-muted ml-2 shrink-0">{fmtUSD(c.amount_usd)}</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded-badge text-white" style={{ backgroundColor: color }}>{c.type}</span>
              {c.hq_state && <span className="text-2xs font-mono text-txt-muted">{c.hq_state}</span>}
            </div>
            <div className="h-1 bg-surface-3 rounded-pill overflow-hidden">
              <div className="h-full rounded-pill" style={{ width: `${Math.round((c.amount_usd / maxAmt) * 100)}%`, backgroundColor: color, opacity: 0.75 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Mapbox USA Map ────────────────────────────────────────────────────────────

function USAMap({
  stateByName,
  onSelect,
}: {
  stateByName: Map<string, StateData>;
  onSelect: (s: StateData) => void;
}) {
  const mapRef = useRef<MapRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [geoJSON, setGeoJSON] = useState<GeoJSON.FeatureCollection | null>(null);
  const [hoveredName, setHoveredName] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{
    name: string; data: StateData | null; x: number; y: number;
  } | null>(null);

  // Load GeoJSON once
  useEffect(() => {
    fetch(GEO_URL).then((r) => r.json()).then(setGeoJSON);
  }, []);

  // Build Mapbox fill-color expression: match by name
  const fillColorExpr = useMemo(() => {
    const matchArgs: (string | string[])[] = [];
    for (const [name, state] of stateByName) {
      if (state.nih_grants_usd > 0) {
        matchArgs.push(name, getFillColor(state.nih_grants_usd));
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const dataExpr: any = matchArgs.length > 0
      ? ["match", ["get", "name"], ...matchArgs, NO_DATA_FILL]
      : NO_DATA_FILL;

    // Overlay hover color on top
    return [
      "case",
      ["==", ["get", "name"], hoveredName ?? ""],
      HOVER_FILL,
      dataExpr,
    ];
  }, [stateByName, hoveredName]);

  const fillLayer: LayerProps = {
    id: "states-fill",
    type: "fill",
    paint: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      "fill-color": fillColorExpr as any,
      "fill-opacity": 0.88,
    },
  };

  const borderLayer: LayerProps = {
    id: "states-border",
    type: "line",
    paint: {
      "line-color": BORDER_COLOR,
      "line-width": 0.6,
      "line-opacity": 0.7,
    },
  };

  const handleMouseMove = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (feature) {
        const name = feature.properties?.name as string;
        setHoveredName(name);
        setTooltip({
          name,
          data: stateByName.get(name) ?? null,
          x: e.point.x,
          y: e.point.y,
        });
      } else {
        setHoveredName(null);
        setTooltip(null);
      }
    },
    [stateByName]
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredName(null);
    setTooltip(null);
  }, []);

  const handleClick = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (feature) {
        const name = feature.properties?.name as string;
        const state = stateByName.get(name);
        if (state) onSelect(state);
      }
    },
    [stateByName]
  );

  const containerW = containerRef.current?.offsetWidth ?? 800;

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <MapGL
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={{ longitude: -97, latitude: 38, zoom: 3.2 }}
        mapStyle={MAP_STYLE}
        style={{ width: "100%", height: "100%" }}
        interactiveLayerIds={["states-fill"]}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        cursor={hoveredName && stateByName.has(hoveredName) ? "pointer" : "grab"}
        reuseMaps
      >
        <NavigationControl position="top-right" showCompass={false} />

        {geoJSON && (
          <Source id="us-states" type="geojson" data={geoJSON}>
            <Layer {...fillLayer} />
            <Layer {...borderLayer} />
          </Source>
        )}
      </MapGL>

      {/* Tooltip */}
      {tooltip && (
        <HoverTooltip
          name={tooltip.name}
          data={tooltip.data}
          x={tooltip.x}
          y={tooltip.y}
          containerW={containerW}
        />
      )}
    </div>
  );
}

// ── Main Canvas ───────────────────────────────────────────────────────────────

export function EcosystemCanvas({ data }: { data: USEcosystemData }) {
  const [sidebarTab, setSidebarTab] = useState<"states" | "contractors">("states");
  const [selectedState, setSelectedState] = useState<StateData | null>(null);

  const { stateByName, maxNIH, activeStates, totalFederal, maxCountries } = useMemo(() => ({
    stateByName: new Map<string, StateData>(data.states.map((s) => [s.name, s])),
    maxNIH: Math.max(...data.states.map((s) => s.nih_grants_usd), 1),
    activeStates: data.states.filter((s) => s.nih_grants_usd > 0 || s.usaspending_usd > 0).length,
    totalFederal: data.states.reduce((sum, s) => sum + s.usaspending_usd, 0),
    maxCountries: Math.max(...data.states.map((s) => s.countries_reached), 0),
  }), [data.states]);

  return (
    <div className="flex h-full">
      {/* LEFT: map */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* KPI strip */}
        <div className="flex gap-2 px-6 pt-4 pb-3 border-b border-surface-3 bg-white">
          <KPICard label="NIH Research Grants" value={fmtUSD(data.total_nih_usd)} sub="malaria R&D portfolio" accent="#9b7ed4" meta={METRIC_META.nih_grants_state} />
          <KPICard label="Federal Field Awards" value={fmtUSD(totalFederal)} sub="USAID implementation" accent="#e67a3c" meta={METRIC_META.usaspending_state} />
          <KPICard label="US Organizations" value={String(data.total_orgs)} sub="universities, NGOs, firms" />
          <KPICard label="Clinical Trials" value={String(data.total_trials)} sub="active & recruiting" accent="#d44f2a" />
          <KPICard label="Active States" value={String(activeStates)} sub={`${maxCountries} countries reached`} />
        </div>

        {/* Map (flex-1, Mapbox fills it) */}
        <div className="flex-1 relative overflow-hidden">
          <USAMap stateByName={stateByName} onSelect={setSelectedState} />
          {selectedState && (
            <StatePopup summary={selectedState} onClose={() => setSelectedState(null)} />
          )}
        </div>

        {/* Legend */}
        <MapLegend />
      </div>

      {/* RIGHT: sidebar */}
      <div className="w-[380px] flex flex-col border-l border-surface-3 bg-white shrink-0">
        <div className="px-6 pt-5 pb-4 border-b border-surface-3">
          <p className="text-2xs font-mono uppercase tracking-[0.16em] text-txt-muted mb-1.5">Chapter 03 · American Innovation</p>
          <h2 className="text-lg font-bold text-txt-primary leading-tight mb-2">WHO IN AMERICA DOES THIS WORK</h2>
          <p className="text-xs text-txt-muted leading-relaxed">
            {activeStates} states have active malaria research portfolios. US universities,
            NGOs, and contractors operate in {maxCountries}+ countries worldwide.
          </p>
        </div>

        {data.top_contractors && data.top_contractors.length > 0 && (
          <OrgTypeBreakdown contractors={data.top_contractors} />
        )}

        {data.top_contractors && data.top_contractors.length > 0 && (
          <div className="flex border-b border-surface-3 shrink-0">
            {(["states", "contractors"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setSidebarTab(tab)}
                className="flex-1 py-2.5 text-2xs font-mono uppercase tracking-[0.1em] transition-colors"
                style={{
                  color: sidebarTab === tab ? "#9b7ed4" : "#999",
                  borderBottom: sidebarTab === tab ? "2px solid #9b7ed4" : "2px solid transparent",
                }}
              >
                {tab === "states" ? "State Activity" : "Implementers"}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto min-h-0">
          {sidebarTab === "states" ? (
            <StateList states={data.states} maxNIH={maxNIH} onSelect={setSelectedState} />
          ) : (
            <TopContractorsPanel contractors={data.top_contractors ?? []} />
          )}
        </div>
      </div>

      <style>{`
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(12px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
