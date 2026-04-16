"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { CommandCountrySummary, ThreatEvent, EndemicBoundaries } from "@/lib/data";
import { color, EVENT_COLORS } from "@/lib/tokens";

type Props = {
  countries: CommandCountrySummary[];
  threats: ThreatEvent[];
  boundaries?: EndemicBoundaries;
  onCountryClick?: (iso3: string) => void;
};

export function GlobalMap({ countries, threats, boundaries, onCountryClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pulseRef = useRef<number>(0);

  const propsRef = useRef({ countries, threats, boundaries, onCountryClick });
  propsRef.current = { countries, threats, boundaries, onCountryClick };

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          "carto-voyager": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}@2x.png",
            ],
            tileSize: 256,
            attribution: "&copy; CartoDB &copy; OpenStreetMap",
          },
        },
        layers: [
          {
            id: "carto-voyager-layer",
            type: "raster",
            source: "carto-voyager",
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [20, 5],
      zoom: 2.2,
      minZoom: 1.5,
      maxZoom: 8,
      attributionControl: false,
      pitchWithRotate: false,
      dragRotate: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      className: "malariaintel-popup",
      offset: 14,
    });

    map.on("load", () => {
      const { countries: c, threats: t, boundaries: b, onCountryClick: onClick } = propsRef.current;
      setupChoropleth(map, b, c, hoverPopup, onClick);
      setupThreats(map, t, hoverPopup);
      startPulse(map, pulseRef);
    });

    mapRef.current = map;

    return () => {
      cancelAnimationFrame(pulseRef.current);
      hoverPopup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.loaded()) return;

    if (boundaries) {
      const countryLookup = new Map<string, CommandCountrySummary>();
      countries.forEach((c) => countryLookup.set(c.iso3, c));
      const enriched = enrichBoundaries(boundaries, countryLookup);
      const src = map.getSource("endemic-boundaries") as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(enriched as unknown as GeoJSON.FeatureCollection);
    }

    const threatGeo = threatsToGeoJSON(threats);
    const threatSrc = map.getSource("threats") as maplibregl.GeoJSONSource | undefined;
    if (threatSrc) threatSrc.setData(threatGeo);
  }, [countries, threats, boundaries]);

  return <div ref={containerRef} className="w-full h-full" />;
}

/* ── Choropleth ─────────────────────────────────────────────────────────── */

function enrichBoundaries(
  boundaries: EndemicBoundaries,
  countryLookup: Map<string, CommandCountrySummary>
) {
  return {
    ...boundaries,
    features: boundaries.features.map((f) => {
      const c = countryLookup.get(f.properties.iso3);
      return {
        ...f,
        properties: {
          ...f.properties,
          incidence: c?.incidence_per_1000 ?? 0,
          cases: c?.cases ?? 0,
          deaths: c?.deaths ?? 0,
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

  const countryLookup = new Map<string, CommandCountrySummary>();
  countries.forEach((c) => countryLookup.set(c.iso3, c));
  const enriched = enrichBoundaries(boundaries, countryLookup);

  map.addSource("endemic-boundaries", {
    type: "geojson",
    data: enriched as unknown as GeoJSON.FeatureCollection,
  });

  map.addLayer({
    id: "choropleth-fill",
    type: "fill",
    source: "endemic-boundaries",
    paint: {
      "fill-color": [
        "interpolate", ["linear"], ["get", "incidence"],
        0,   "rgba(5, 150, 105, 0.18)",
        50,  "rgba(202, 138, 4, 0.28)",
        150, "rgba(234, 88, 12, 0.38)",
        300, "rgba(220, 38, 38, 0.50)",
      ],
      "fill-opacity": 0.7,
    },
  });

  map.addLayer({
    id: "choropleth-line",
    type: "line",
    source: "endemic-boundaries",
    paint: {
      "line-color": [
        "interpolate", ["linear"], ["get", "incidence"],
        0,   color.uncertainty.low,
        50,  color.uncertainty.moderate,
        150, color.uncertainty.high,
        300, color.uncertainty.very_high,
      ],
      "line-width": 1.2,
      "line-opacity": 0.5,
    },
  });

  map.addLayer({
    id: "choropleth-highlight",
    type: "fill",
    source: "endemic-boundaries",
    paint: { "fill-color": "#0f1729", "fill-opacity": 0 },
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

    const p = feat.properties as Record<string, unknown>;
    const iso3 = p.iso3 as string;
    const name = p.name as string;
    const incidence = Number(p.incidence);
    const cases = Number(p.cases);
    const deaths = Number(p.deaths);

    map.setFilter("choropleth-highlight", ["==", ["get", "iso3"], iso3]);
    map.setPaintProperty("choropleth-highlight", "fill-opacity", 0.08);

    const casesStr = cases >= 1e6 ? `${(cases / 1e6).toFixed(1)}M` : `${(cases / 1e3).toFixed(0)}K`;
    const deathsStr = deaths >= 1e3 ? `${(deaths / 1e3).toFixed(1)}K` : String(deaths);

    popup
      .setLngLat(e.lngLat)
      .setHTML(
        `<div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;color:#0f1729;background:#fff;padding:10px 14px;border-radius:10px;border:1px solid #e8ecf1;box-shadow:0 4px 16px rgba(15,23,41,0.12);min-width:170px;">` +
        `<div style="font-weight:600;font-size:13px;margin-bottom:6px;display:flex;align-items:center;gap:6px;">` +
        `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${incidenceToHex(incidence)};"></span>${name}</div>` +
        `<div style="display:grid;grid-template-columns:auto 1fr;gap:2px 10px;color:#3d4f66;">` +
        `<span>Incidence</span><span style="color:#0f1729;font-weight:600;font-family:'IBM Plex Mono',monospace;text-align:right;">${incidence.toFixed(1)}<span style="font-weight:400;color:#6b7f99;font-size:10px;"> /1K</span></span>` +
        `<span>Cases</span><span style="color:#0f1729;font-weight:500;text-align:right;">${casesStr}</span>` +
        `<span>Deaths</span><span style="color:#0f1729;font-weight:500;text-align:right;">${deathsStr}</span>` +
        `</div></div>`
      )
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

/* ── Threat circles ──────────────────────────────────────────────────────── */

function threatsToGeoJSON(threats: ThreatEvent[]) {
  return {
    type: "FeatureCollection" as const,
    features: threats.map((t) => ({
      type: "Feature" as const,
      properties: {
        event_id: t.event_id,
        disease: t.disease,
        event_type: t.event_type,
        country_name: t.country_name,
        admin1: t.admin1,
        severity: t.severity,
        narrative: t.narrative,
        dci_score: t.dci_score,
        color: EVENT_COLORS[t.event_type] ?? "#90a7bf",
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
    id: "threats-pulse",
    type: "circle",
    source: "threats",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 0, 6, 0.5, 10, 1, 14],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.25,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": ["get", "color"],
      "circle-stroke-opacity": 0.4,
    },
  });

  map.addLayer({
    id: "threats-core",
    type: "circle",
    source: "threats",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "severity"], 0, 3, 0.5, 5, 1, 7],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.9,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#ffffff",
    },
  });

  const threatPopup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    className: "malariaintel-popup",
    offset: 14,
  });

  map.on("mousemove", "threats-core", (e) => {
    map.getCanvas().style.cursor = "pointer";
    const feat = e.features?.[0];
    if (!feat) return;

    const p = feat.properties as Record<string, unknown>;
    const eventColor = p.color as string;
    const dci = p.dci_score != null ? Number(p.dci_score) : null;

    threatPopup
      .setLngLat(e.lngLat)
      .setHTML(
        `<div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;color:#0f1729;background:#fff;padding:10px 14px;border-radius:10px;border:1px solid #e8ecf1;box-shadow:0 4px 16px rgba(15,23,41,0.12);max-width:260px;">` +
        `<div style="font-weight:600;font-size:13px;margin-bottom:2px;color:${eventColor};">${p.disease}</div>` +
        `<div style="color:#3d4f66;margin-bottom:4px;">${p.country_name} · ${p.admin1}</div>` +
        `<div style="color:#6b7f99;font-size:11px;line-height:1.4;">${p.narrative}</div>` +
        (dci !== null
          ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e8ecf1;font-size:11px;"><span style="color:#6b7f99;">DCI Score:</span> <span style="color:#d4890a;font-weight:600;font-family:'IBM Plex Mono',monospace;">${dci.toFixed(2)}</span></div>`
          : "") +
        `</div>`
      )
      .addTo(map);
  });

  map.on("mouseleave", "threats-core", () => {
    map.getCanvas().style.cursor = "";
    threatPopup.remove();
  });
}

/* ── Pulse animation ─────────────────────────────────────────────────────── */

function startPulse(map: maplibregl.Map, frameRef: React.MutableRefObject<number>) {
  const BASE = [6, 10, 14];
  const AMPLITUDE = 6;

  function tick() {
    if (!map.getLayer("threats-pulse")) return;

    const t = (performance.now() % 2000) / 2000;
    const scale = 1 + AMPLITUDE * Math.sin(t * Math.PI);
    const opacity = 0.35 * (1 - t * 0.7);

    map.setPaintProperty("threats-pulse", "circle-radius", [
      "interpolate", ["linear"], ["get", "severity"],
      0,   BASE[0] + scale,
      0.5, BASE[1] + scale,
      1,   BASE[2] + scale,
    ]);
    map.setPaintProperty("threats-pulse", "circle-opacity", opacity);
    map.setPaintProperty("threats-pulse", "circle-stroke-opacity", opacity * 0.8);

    frameRef.current = requestAnimationFrame(tick);
  }

  frameRef.current = requestAnimationFrame(tick);
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function incidenceToHex(incidence: number): string {
  if (incidence >= 300) return color.uncertainty.very_high;
  if (incidence >= 150) return color.uncertainty.high;
  if (incidence >= 50)  return color.uncertainty.moderate;
  if (incidence > 0)    return color.uncertainty.low;
  return color.surface[3];
}
