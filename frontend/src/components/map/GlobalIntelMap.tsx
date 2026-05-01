"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { CommandCountrySummary, ThreatEvent, EndemicBoundaries } from "@/lib/data";
import { useIntelStore } from "@/lib/store";
import { color, EVENT_COLORS } from "@/lib/tokens";

type Props = {
  countries: CommandCountrySummary[];
  threats: ThreatEvent[];
  boundaries?: EndemicBoundaries;
  onCountryClick?: (iso3: string) => void;
  interactive?: boolean;
};

const CARTO_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-base": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors &copy; <a href='https://carto.com/'>CARTO</a>",
    },
    "carto-labels": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
    },
  },
  layers: [
    { id: "base",   type: "raster", source: "carto-base"   },
    // Labels rendered AFTER data layers via addLayer — inserted in setupChoropleth
  ],
};

export function GlobalIntelMap({
  countries,
  threats,
  boundaries,
  onCountryClick,
  interactive = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const pulseRef     = useRef<number>(0);
  const propsRef     = useRef({ countries, threats, boundaries, onCountryClick });
  propsRef.current   = { countries, threats, boundaries, onCountryClick };

  const { activeLayers } = useIntelStore();
  const activeLayersRef  = useRef(activeLayers);
  activeLayersRef.current = activeLayers;

  /* ── Init map ─────────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: CARTO_STYLE,
      center:  [20, 5],
      zoom:    2.2,
      minZoom: 1.5,
      maxZoom: 9,
      attributionControl: false,
      pitchWithRotate: false,
      dragRotate: false,
      interactive,
    });

    if (interactive) {
      map.addControl(
        new maplibregl.NavigationControl({ showCompass: false }),
        "bottom-right"
      );
    }

    const hoverPopup = new maplibregl.Popup({
      closeButton:  false,
      closeOnClick: false,
      className:    "malariaintel-popup",
      offset:       14,
    });

    map.on("load", () => {
      const { countries: c, threats: t, boundaries: b, onCountryClick: onClick } =
        propsRef.current;
      setupChoropleth(map, b, c, hoverPopup, onClick);
      setupThreats(map, t, hoverPopup);

      // Add labels on top of all data layers
      map.addSource("carto-labels-top", {
        type: "raster",
        tiles: ["https://a.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png"],
        tileSize: 256,
      });
      map.addLayer({ id: "labels-top", type: "raster", source: "carto-labels-top", paint: { "raster-opacity": 0.85 } });

      startPulse(map, pulseRef);
      syncLayerVisibility(map, activeLayersRef.current);
    });

    mapRef.current = map;

    return () => {
      cancelAnimationFrame(pulseRef.current);
      hoverPopup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Update data when props change ────────────────────────────────────── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map?.loaded()) return;

    if (boundaries) {
      const lookup = new Map(countries.map((c) => [c.iso3, c]));
      const enriched = enrichBoundaries(boundaries, lookup);
      const src = map.getSource("endemic-boundaries") as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(enriched as unknown as GeoJSON.FeatureCollection);
    }

    const threatSrc = map.getSource("threats") as maplibregl.GeoJSONSource | undefined;
    if (threatSrc) threatSrc.setData(threatsToGeoJSON(threats));
  }, [countries, threats, boundaries]);

  /* ── Sync layer visibility ─────────────────────────────────────────────── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map?.loaded()) return;
    syncLayerVisibility(map, activeLayers);
  }, [activeLayers]);

  return <div ref={containerRef} className="w-full h-full" />;
}

/* ── Layer visibility sync ──────────────────────────────────────────────── */

const BURDEN_LAYERS   = ["choropleth-fill", "choropleth-line", "choropleth-highlight"];
const OUTBREAK_LAYERS = ["threats-pulse", "threats-core"];

function syncLayerVisibility(map: maplibregl.Map, layers: string[]) {
  const hasBurden    = layers.includes("burden");
  const hasOutbreaks = layers.includes("outbreaks");

  BURDEN_LAYERS.forEach((id) => {
    if (map.getLayer(id))
      map.setLayoutProperty(id, "visibility", hasBurden ? "visible" : "none");
  });
  OUTBREAK_LAYERS.forEach((id) => {
    if (map.getLayer(id))
      map.setLayoutProperty(id, "visibility", hasOutbreaks ? "visible" : "none");
  });
}

/* ── Choropleth ─────────────────────────────────────────────────────────── */

function enrichBoundaries(
  boundaries: EndemicBoundaries,
  lookup: Map<string, CommandCountrySummary>
) {
  return {
    ...boundaries,
    features: boundaries.features.map((f) => {
      const c = lookup.get(f.properties.iso3);
      return {
        ...f,
        properties: {
          ...f.properties,
          incidence:         c?.incidence_per_1000  ?? 0,
          cases:             c?.cases               ?? 0,
          deaths:            c?.deaths              ?? 0,
          cases_change_yoy:  c?.cases_change_yoy    ?? null,
          llin_coverage:     c?.llin_coverage       ?? null,
          funding_per_capita:c?.funding_per_capita  ?? null,
          elimination_phase: c?.elimination_phase   ?? null,
          alert_level:       c?.alert_level         ?? null,
        },
      };
    }),
  };
}

function setupChoropleth(
  map: maplibregl.Map,
  boundaries: EndemicBoundaries | undefined,
  countries: CommandCountrySummary[],
  popup: maplibregl.Popup,
  onCountryClick?: (iso3: string) => void
) {
  if (!boundaries) return;

  const lookup   = new Map(countries.map((c) => [c.iso3, c]));
  const enriched = enrichBoundaries(boundaries, lookup);

  map.addSource("endemic-boundaries", {
    type: "geojson",
    data: enriched as unknown as GeoJSON.FeatureCollection,
  });

  /* Filled choropleth — tuned for Positron light base */
  map.addLayer({
    id:     "choropleth-fill",
    type:   "fill",
    source: "endemic-boundaries",
    paint:  {
      "fill-color": [
        "interpolate", ["linear"], ["get", "incidence"],
        0,   "rgba(16,  185, 129, 0.0)",   // no malaria → transparent
        1,   "rgba(253, 224, 71,  0.45)",  // very low → soft yellow
        50,  "rgba(249, 115, 22,  0.58)",  // moderate → orange
        150, "rgba(239, 68,  68,  0.70)",  // high → red
        300, "rgba(185, 28,  28,  0.82)",  // very high → deep red
      ],
      "fill-opacity": 1,
    },
  });

  /* Country borders — subtle on Positron */
  map.addLayer({
    id:     "choropleth-line",
    type:   "line",
    source: "endemic-boundaries",
    paint:  {
      "line-color": [
        "interpolate", ["linear"], ["get", "incidence"],
        0,   "rgba(180,180,180,0.35)",
        50,  "rgba(249,115,22,0.55)",
        150, "rgba(239,68,68,0.65)",
        300, "rgba(185,28,28,0.75)",
      ],
      "line-width":   0.8,
      "line-opacity": 1,
    },
  });

  /* Highlight (hover) */
  map.addLayer({
    id:     "choropleth-highlight",
    type:   "fill",
    source: "endemic-boundaries",
    paint:  { "fill-color": "#ffffff", "fill-opacity": 0 },
    filter: ["==", ["get", "iso3"], ""],
  });

  map.on("mousemove", "choropleth-fill", (e) => {
    const threatFeats = map.queryRenderedFeatures(e.point, { layers: ["threats-core"] });
    if (threatFeats.length > 0) {
      map.setFilter("choropleth-highlight", ["==", ["get", "iso3"], ""]);
      map.setPaintProperty("choropleth-highlight", "fill-opacity", 0);
      popup.remove();
      return;
    }

    map.getCanvas().style.cursor = "pointer";
    const feat = e.features?.[0];
    if (!feat) return;

    const p          = feat.properties as Record<string, unknown>;
    const iso3       = p.iso3 as string;
    const name       = p.name as string;
    const incidence  = Number(p.incidence);
    const cases      = Number(p.cases);
    const deaths     = Number(p.deaths);
    const changeYoy  = p.cases_change_yoy != null ? Number(p.cases_change_yoy) : null;
    const llin       = p.llin_coverage    != null ? Number(p.llin_coverage)    : null;
    const fpc        = p.funding_per_capita != null ? Number(p.funding_per_capita) : null;
    const phase      = p.elimination_phase as string | null ?? null;

    map.setFilter("choropleth-highlight", ["==", ["get", "iso3"], iso3]);
    map.setPaintProperty("choropleth-highlight", "fill-opacity", 0.1);

    const casesStr  = cases  >= 1e6 ? `${(cases  / 1e6).toFixed(1)}M` : `${(cases  / 1e3).toFixed(0)}K`;
    const deathsStr = deaths >= 1e3 ? `${(deaths / 1e3).toFixed(1)}K` : String(deaths);

    popup
      .setLngLat(e.lngLat)
      .setHTML(popupHTML(name, incidence, casesStr, deathsStr, changeYoy, llin, fpc, phase))
      .addTo(map);
  });

  map.on("mouseleave", "choropleth-fill", () => {
    map.getCanvas().style.cursor = "";
    map.setFilter("choropleth-highlight", ["==", ["get", "iso3"], ""]);
    map.setPaintProperty("choropleth-highlight", "fill-opacity", 0);
    popup.remove();
  });

  map.on("click", "choropleth-fill", (e) => {
    const iso3 = e.features?.[0]?.properties?.iso3;
    if (iso3 && onCountryClick) onCountryClick(iso3);
  });
}

/* ── Threat markers ─────────────────────────────────────────────────────── */

function threatsToGeoJSON(threats: ThreatEvent[]) {
  return {
    type: "FeatureCollection" as const,
    features: threats.map((t) => ({
      type:       "Feature" as const,
      properties: {
        event_id:     t.event_id,
        disease:      t.disease,
        event_type:   t.event_type,
        country_name: t.country_name,
        admin1:       t.admin1,
        severity:     t.severity,
        narrative:    t.narrative,
        dci_score:    t.dci_score,
        color:        EVENT_COLORS[t.event_type] ?? "#90a7bf",
      },
      geometry: { type: "Point" as const, coordinates: [t.lng, t.lat] },
    })),
  };
}

function setupThreats(
  map: maplibregl.Map,
  threats: ThreatEvent[],
  _sharedPopup: maplibregl.Popup
) {
  map.addSource("threats", { type: "geojson", data: threatsToGeoJSON(threats) });

  map.addLayer({
    id:     "threats-pulse",
    type:   "circle",
    source: "threats",
    paint:  {
      "circle-radius": [
        "interpolate", ["linear"], ["get", "severity"],
        0, 8, 0.5, 14, 1, 20,
      ],
      "circle-color":          ["get", "color"],
      "circle-opacity":        0.18,
      "circle-stroke-width":   1.5,
      "circle-stroke-color":   ["get", "color"],
      "circle-stroke-opacity": 0.35,
    },
  });

  map.addLayer({
    id:     "threats-core",
    type:   "circle",
    source: "threats",
    paint:  {
      "circle-radius": [
        "interpolate", ["linear"], ["get", "severity"],
        0, 4, 0.5, 6, 1, 9,
      ],
      "circle-color":        ["get", "color"],
      "circle-opacity":      0.95,
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
    },
  });

  const threatPopup = new maplibregl.Popup({
    closeButton:  false,
    closeOnClick: false,
    className:    "malariaintel-popup",
    offset:       14,
  });

  map.on("mousemove", "threats-core", (e) => {
    map.getCanvas().style.cursor = "pointer";
    const feat = e.features?.[0];
    if (!feat) return;

    const p          = feat.properties as Record<string, unknown>;
    const eventColor = p.color as string;
    const dci        = p.dci_score != null ? Number(p.dci_score) : null;

    threatPopup
      .setLngLat(e.lngLat)
      .setHTML(threatPopupHTML(p, eventColor, dci))
      .addTo(map);
  });

  map.on("mouseleave", "threats-core", () => {
    map.getCanvas().style.cursor = "";
    threatPopup.remove();
  });
}

/* ── Pulse animation ─────────────────────────────────────────────────────── */

function startPulse(
  map: maplibregl.Map,
  frameRef: React.MutableRefObject<number>
) {
  const BASE      = [8, 14, 20];
  const AMPLITUDE = 7;

  function tick() {
    if (!map.getLayer("threats-pulse")) return;
    const t       = (performance.now() % 2400) / 2400;
    const scale   = 1 + AMPLITUDE * Math.sin(t * Math.PI);
    const opacity = 0.3 * (1 - t * 0.75);

    map.setPaintProperty("threats-pulse", "circle-radius", [
      "interpolate", ["linear"], ["get", "severity"],
      0, BASE[0] + scale, 0.5, BASE[1] + scale, 1, BASE[2] + scale,
    ]);
    map.setPaintProperty("threats-pulse", "circle-opacity", opacity);
    map.setPaintProperty("threats-pulse", "circle-stroke-opacity", opacity * 0.7);

    frameRef.current = requestAnimationFrame(tick);
  }

  frameRef.current = requestAnimationFrame(tick);
}

/* ── Popup HTML helpers ──────────────────────────────────────────────────── */

function incidenceColor(v: number) {
  if (v >= 300) return color.uncertainty.very_high;
  if (v >= 150) return color.uncertainty.high;
  if (v >= 50)  return color.uncertainty.moderate;
  if (v > 0)    return color.uncertainty.low;
  return color.surface[3];
}

function popupHTML(
  name: string,
  incidence: number,
  cases: string,
  deaths: string,
  changeYoy: number | null,
  llin: number | null,
  fpc: number | null,
  phase: string | null,
) {
  const trendArrow = changeYoy == null ? ""
    : changeYoy > 0
      ? `<span style="color:#ef4444;font-size:10px;"> ▲${changeYoy.toFixed(1)}%</span>`
      : `<span style="color:#10b981;font-size:10px;"> ▼${Math.abs(changeYoy).toFixed(1)}%</span>`;

  const phaseTag = phase
    ? `<div style="margin-top:8px;padding-top:7px;border-top:1px solid #eaecf4;">` +
      `<span style="font-size:10px;font-family:'IBM Plex Mono',monospace;color:#8a9ab2;text-transform:uppercase;letter-spacing:0.05em;">Phase</span> ` +
      `<span style="font-size:10px;color:#0f1729;font-weight:600;">${phase}</span></div>`
    : "";

  const extraRows =
    (llin != null
      ? `<span style="font-size:11px;">ITN coverage</span><span style="font-weight:600;text-align:right;">${llin.toFixed(0)}%</span>`
      : "") +
    (fpc != null
      ? `<span style="font-size:11px;">Funding /capita</span><span style="font-weight:600;text-align:right;">$${fpc.toFixed(2)}</span>`
      : "");

  return (
    `<div style="font-family:'IBM Plex Mono',monospace;font-size:12px;color:#0f1729;background:rgba(255,255,255,0.97);padding:12px 15px;border-radius:14px;border:1px solid rgba(255,255,255,0.9);box-shadow:0 8px 28px rgba(0,0,0,0.15);min-width:200px;max-width:240px;">` +
    `<div style="display:flex;align-items:center;gap:7px;margin-bottom:9px;">` +
    `<span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:${incidenceColor(incidence)};flex-shrink:0;"></span>` +
    `<span style="font-weight:700;font-size:13px;font-family:'ff-tisa-web-pro',serif;line-height:1.2;">${name}</span>` +
    `</div>` +
    `<div style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;color:#4a5470;">` +
    `<span style="font-size:11px;">Incidence</span><span style="color:#0f1729;font-weight:700;text-align:right;">${incidence.toFixed(1)}<span style="font-weight:400;color:#8a9ab2;font-size:10px;"> /1K</span></span>` +
    `<span style="font-size:11px;">Cases</span><span style="font-weight:600;text-align:right;">${cases}${trendArrow}</span>` +
    `<span style="font-size:11px;">Deaths</span><span style="font-weight:600;text-align:right;">${deaths}</span>` +
    extraRows +
    `</div>` +
    phaseTag +
    `</div>`
  );
}

function threatPopupHTML(
  p: Record<string, unknown>,
  eventColor: string,
  dci: number | null
) {
  return (
    `<div style="font-family:'ff-tisa-web-pro',serif;font-size:12px;color:#0f1729;background:rgba(255,255,255,0.97);padding:11px 15px;border-radius:12px;border:1px solid rgba(255,255,255,0.9);box-shadow:0 6px 24px rgba(0,0,0,0.14);max-width:270px;">` +
    `<div style="font-weight:700;font-size:13px;margin-bottom:2px;color:${eventColor};">${p.disease}</div>` +
    `<div style="color:#4a5470;margin-bottom:5px;">${p.country_name} · ${p.admin1}</div>` +
    `<div style="color:#6b7f99;font-size:11px;line-height:1.45;">${p.narrative}</div>` +
    (dci !== null
      ? `<div style="margin-top:7px;padding-top:7px;border-top:1px solid #eaecf4;font-size:11px;display:flex;align-items:center;gap:6px;"><span style="color:#8a9ab2;">DCI Score</span><span style="color:#d4890a;font-weight:700;font-family:'IBM Plex Mono',monospace;">${dci.toFixed(2)}</span></div>`
      : "") +
    `</div>`
  );
}
