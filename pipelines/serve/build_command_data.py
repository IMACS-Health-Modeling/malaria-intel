"""
L2 — Build Command page JSON for the frontend.
Queries PostgreSQL and produces JSON that matches the TypeScript types in data.ts exactly:

  serving/v1/command/global-summary.json    → GlobalSummary
  serving/v1/command/countries.json         → CommandCountrySummary[]
  serving/v1/command/active-threats.json    → ThreatEvent[]
  serving/v1/command/global-timeseries.json → GlobalTimeseriesPoint[]
  serving/v1/command/endemic-boundaries.json → EndemicBoundaries (GeoJSON)

Usage:
    python -m pipelines.serve.build_command_data [--dry-run] [--skip-boundaries]
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.logger import PipelineLogger
from pipelines.utils.db import fetchall, fetchone
from pipelines.utils.s3 import put_json, serving_key, BUCKET

LATEST_YEAR = 2023   # WMR data lag: 2024 report covers 2023
PREV_YEAR   = 2022

# WHO GTS target 2025: ~$7.3B/year
WHO_GTS_TARGET_USD = 7_300_000_000

# Natural Earth 110m countries — stable, ~1.4 MB
NE_COUNTRIES_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)


# ── Alert / DCI level helpers ───────────────────────────────────────────────

def alert_level(incidence: float | None) -> str:
    if incidence is None:      return "none"
    if incidence >= 150:       return "critical"
    if incidence >= 50:        return "high"
    if incidence >= 10:        return "moderate"
    if incidence >= 1:         return "low"
    return "none"


def dci_level(score: float | None) -> str:
    if score is None:  return "none"
    if score >= 0.8:   return "critical"
    if score >= 0.6:   return "high"
    if score >= 0.4:   return "moderate"
    if score >= 0.2:   return "low"
    return "negligible"


# ── Dedup helper ────────────────────────────────────────────────────────────

_SOURCE_PRIORITY = "CASE source_code WHEN 'wmr_2025' THEN 1 WHEN 'wmr_2024' THEN 2 ELSE 3 END"


def _dedup_sum(metric: str, year: int) -> float | None:
    row = fetchone(
        f"""SELECT SUM(value) AS total FROM (
                SELECT DISTINCT ON (iso3) iso3, value
                FROM malaria.fact_burden
                WHERE metric=%s AND year=%s
                  AND source_code IN ('wmr_2025','wmr_2024','who_gho')
                ORDER BY iso3, {_SOURCE_PRIORITY}
            ) deduped""",
        (metric, year),
    )
    return float(row["total"]) if row and row["total"] is not None else None


# ── Build functions — output matches TypeScript types exactly ───────────────

def build_countries() -> list[dict]:
    """Per-country burden → CommandCountrySummary[]"""
    rows = fetchall(
        """SELECT
               dc.iso3, dc.name, dc.region, dc.lat, dc.lng, dc.is_endemic,
               inc.value  AS incidence,
               cas.value  AS cases_est,
               dth.value  AS deaths_est,
               cas_prev.value AS cases_prev,
               itn.value  AS itn_use_pct
           FROM malaria.dim_country dc
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='incidence_per_1000'
               ORDER BY year DESC LIMIT 1
           ) inc ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='cases_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1
                                          WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
           ) cas ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='deaths_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1
                                          WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
           ) dth ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='cases_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1
                                          WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
           ) cas_prev ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_intervention
               WHERE iso3=dc.iso3 AND indicator='itn_use_pct'
               ORDER BY year DESC LIMIT 1
           ) itn ON TRUE
           WHERE inc.value IS NOT NULL OR cas.value IS NOT NULL
           ORDER BY COALESCE(cas.value, 0) DESC""",
        (LATEST_YEAR, LATEST_YEAR, PREV_YEAR),
    )

    countries = []
    for r in rows:
        cases      = float(r["cases_est"] or 0)
        cases_prev = float(r["cases_prev"] or 0)
        # Store as decimal fraction (0.054 = +5.4%) to match frontend convention
        yoy_decimal = (
            round((cases - cases_prev) / cases_prev, 4)
            if cases_prev > 0 else None
        )
        inc = r["incidence"]
        countries.append({
            "iso3":             r["iso3"],
            "name":             r["name"],
            "region":           r["region"],
            "lat":              float(r["lat"])  if r["lat"]  else None,
            "lng":              float(r["lng"])  if r["lng"]  else None,
            "incidence_per_1000": round(float(inc), 2) if inc else 0.0,
            "cases":            round(cases),
            "deaths":           round(float(r["deaths_est"] or 0)),
            "cases_change_yoy": yoy_decimal,
            "deaths_change_yoy": None,
            "itn_use_pct":      round(float(r["itn_use_pct"]), 1) if r["itn_use_pct"] else None,
            "alert_level":      alert_level(float(inc) if inc else None),
            "is_endemic":       bool(r["is_endemic"]),
            "data_year":        LATEST_YEAR,
        })
    return countries


def build_global_summary(countries: list[dict]) -> dict:
    """World-level KPI bar → GlobalSummary (with nested global: {})"""
    cases_total      = _dedup_sum("cases_estimated",  LATEST_YEAR) or 0
    cases_prev       = _dedup_sum("cases_estimated",  PREV_YEAR)   or 0
    deaths_total     = _dedup_sum("deaths_estimated", LATEST_YEAR) or 0
    deaths_prev      = _dedup_sum("deaths_estimated", PREV_YEAR)   or 0

    funding_row = fetchone(
        """SELECT SUM(amount_usd) AS total FROM malaria.fact_funding
           WHERE disease='malaria' AND year=%s AND amount_usd > 0""",
        (LATEST_YEAR,),
    )
    dci_row = fetchone(
        """SELECT COUNT(*) AS n FROM malaria.fact_outbreak
           WHERE dci_score >= 0.6 AND (status IS NULL OR status != 'closed')""",
        None,
    )
    at_risk = fetchone(
        """SELECT COUNT(DISTINCT iso3) AS n FROM malaria.fact_burden
           WHERE metric='incidence_per_1000' AND year=%s AND value > 1.0""",
        (LATEST_YEAR,),
    )

    cases_yoy  = round((cases_total  - cases_prev)  / cases_prev  * 100, 1) if cases_prev  > 0 else 0.0
    deaths_yoy = round((deaths_total - deaths_prev) / deaths_prev * 100, 1) if deaths_prev > 0 else 0.0
    # Avoid IEEE-754 negative zero (-0.0) which serializes as "-0.0" in JSON
    if cases_yoy  == 0: cases_yoy  = 0.0
    if deaths_yoy == 0: deaths_yoy = 0.0

    total_funding = float(funding_row["total"] or 0) if funding_row else 0.0
    funding_gap   = max(0.0, WHO_GTS_TARGET_USD - total_funding)

    return {
        "period": str(LATEST_YEAR),
        "global": {
            "estimated_cases":       round(cases_total),
            "estimated_deaths":      round(deaths_total),
            "countries_endemic":     int(at_risk["n"] or 0) if at_risk else 0,
            "countries_in_alert":    int(dci_row["n"] or 0) if dci_row else 0,
            "pf_proportion":         0.95,   # WHO WMR 2024: ~95% Pf
            "pv_proportion":         0.03,
            "cases_change_yoy":      cases_yoy,
            "deaths_change_yoy":     deaths_yoy,
            "funding_gap_usd":       round(funding_gap),
            "total_funding_usd":     round(total_funding),
            "active_febrile_overlaps": int(dci_row["n"] or 0) if dci_row else 0,
        },
        "top_burden_countries": countries[:10],
    }


_MALARIA_KEYWORDS = {"malaria", "plasmodium", "falciparum", "vivax", "malariae", "ovale"}


def build_active_threats() -> list[dict]:
    """Active outbreak events → ThreatEvent[]"""
    rows = fetchall(
        """SELECT
               fo.event_id, fo.disease, fo.event_type,
               fo.country_iso3,
               dc.name      AS country_name,
               dc.lat       AS country_lat,
               dc.lng       AS country_lng,
               fo.lat       AS event_lat,
               fo.lng       AS event_lng,
               fo.start_date, fo.end_date, fo.status,
               fo.cases_reported, fo.deaths_reported,
               fo.dci_score, fo.severity_score, fo.narrative,
               fo.source, fo.source_url
           FROM malaria.fact_outbreak fo
           LEFT JOIN malaria.dim_country dc ON dc.iso3 = fo.country_iso3
           WHERE (fo.status IS NULL OR fo.status != 'closed')
             AND fo.start_date >= NOW() - INTERVAL '365 days'
           ORDER BY fo.dci_score DESC NULLS LAST, fo.start_date DESC
           LIMIT 100"""
    )

    threats = []
    for r in rows:
        # Use event lat/lng when available; fall back to country centroid
        lat = float(r["event_lat"]) if r["event_lat"] is not None else (float(r["country_lat"]) if r["country_lat"] else 0.0)
        lng = float(r["event_lng"]) if r["event_lng"] is not None else (float(r["country_lng"]) if r["country_lng"] else 0.0)
        is_malaria = any(kw in (r["disease"] or "").lower() for kw in _MALARIA_KEYWORDS)
        threats.append({
            "event_id":              r["event_id"],
            "disease":               r["disease"] or "Unknown",
            "event_type":            r["event_type"] or "outbreak",
            "country_iso3":          r["country_iso3"],
            "country_name":          r["country_name"] or r["country_iso3"],
            "admin1":                "",
            "severity":              round(float(r["severity_score"]), 2) if r["severity_score"] else 0.5,
            "start_date":            str(r["start_date"]) if r["start_date"] else "",
            "status":                r["status"] or "active",
            "cases_reported":        r["cases_reported"],
            "deaths_reported":       r["deaths_reported"],
            "overlap_with_malaria_zone": 1 if is_malaria else 0,
            "dci_score":             round(float(r["dci_score"]), 3) if r["dci_score"] else None,
            "source":                r["source"] or "",
            "lat":                   lat,
            "lng":                   lng,
            "narrative":             (r["narrative"] or "")[:300],
        })

    # Malaria events first, then by DCI score
    threats.sort(key=lambda t: (0 if t["overlap_with_malaria_zone"] else 1, -(t["dci_score"] or 0)))
    return threats


def build_global_timeseries() -> list[dict]:
    """World malaria cases/deaths 2000–present → GlobalTimeseriesPoint[]"""
    rows = fetchall(
        f"""SELECT year, metric, SUM(value) AS total
            FROM (
                SELECT DISTINCT ON (iso3, year, metric) iso3, year, metric, value
                FROM malaria.fact_burden
                WHERE metric IN ('cases_estimated','deaths_estimated')
                  AND source_code IN ('wmr_2025','wmr_2024','who_gho')
                  AND year >= 2000
                ORDER BY iso3, year, metric, {_SOURCE_PRIORITY}
            ) deduped
            GROUP BY year, metric
            ORDER BY year, metric"""
    )

    by_year: dict[int, dict] = {}
    for r in rows:
        yr = r["year"]
        if yr not in by_year:
            by_year[yr] = {"year": yr, "cases": None, "deaths": None}
        if r["metric"] == "cases_estimated":
            by_year[yr]["cases"] = float(r["total"] or 0)
        else:
            by_year[yr]["deaths"] = float(r["total"] or 0)

    # Convert to frontend types: cases_millions, deaths_thousands
    result = []
    for d in sorted(by_year.values(), key=lambda x: x["year"]):
        result.append({
            "year":             d["year"],
            "cases_millions":   round(d["cases"] / 1e6, 2) if d["cases"] else None,
            "deaths_thousands": round(d["deaths"] / 1e3, 1) if d["deaths"] else None,
            "incidence_per_1000": None,  # requires population denominator
            "llin_coverage":    None,
            "act_coverage":     None,
        })
    return result


def build_endemic_boundaries(countries: list[dict]) -> dict:
    """Download Natural Earth 110m and filter to endemic countries → EndemicBoundaries GeoJSON"""
    endemic_isos = {c["iso3"] for c in countries if c.get("incidence_per_1000", 0) > 0 or c.get("is_endemic")}

    req = urllib.request.Request(NE_COUNTRIES_URL, headers={"User-Agent": "malaria-intel-pipeline"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ne = json.loads(resp.read())

    features = []
    for f in ne.get("features", []):
        props = f.get("properties", {})
        # ADM0_A3 is more reliable than ISO_A3 (which can be -99)
        iso3 = props.get("ADM0_A3") or props.get("ISO_A3") or ""
        if iso3 in endemic_isos:
            features.append({
                "type": "Feature",
                "properties": {
                    "iso3": iso3,
                    "name": props.get("NAME") or props.get("ADMIN") or "",
                },
                "geometry": f["geometry"],
            })

    return {"type": "FeatureCollection", "features": features}


# ── Runner ──────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, skip_boundaries: bool = False) -> None:
    log = PipelineLogger("build_command_data", dry_run=dry_run)

    with log.step("Build country data"):
        countries = build_countries()
        log.info(f"  {len(countries)} countries with burden data")

    with log.step("Build global summary"):
        summary = build_global_summary(countries)
        g = summary["global"]
        log.info(f"  Cases: {g['estimated_cases']:,}  Deaths: {g['estimated_deaths']:,}")
        log.info(f"  Cases YoY: {g['cases_change_yoy']:+.1f}%  Countries endemic: {g['countries_endemic']}")

    with log.step("Build active threats"):
        threats = build_active_threats()
        log.info(f"  {len(threats)} active outbreak events")

    with log.step("Build global timeseries"):
        timeseries = build_global_timeseries()
        log.info(f"  {len(timeseries)} year-points (2000–{LATEST_YEAR})")

    boundaries = None
    if not skip_boundaries:
        with log.step("Build endemic boundaries (Natural Earth 110m)"):
            try:
                boundaries = build_endemic_boundaries(countries)
                log.info(f"  {len(boundaries['features'])} endemic country polygons")
            except Exception as e:
                log.info(f"  WARNING: boundaries download failed: {e}")
                boundaries = None

    if not dry_run:
        with log.step("Upload to S3 serving layer"):
            put_json(serving_key("command", "global-summary.json"),    summary)
            put_json(serving_key("command", "countries.json"),         countries)
            put_json(serving_key("command", "active-threats.json"),    threats)
            put_json(serving_key("command", "global-timeseries.json"), timeseries)
            if boundaries is not None:
                put_json(serving_key("command", "endemic-boundaries.json"), boundaries)
            log.info(f"  Uploaded to s3://{BUCKET}/serving/v1/command/")
    else:
        log.info("[DRY RUN] Would write serving JSON files:")
        log.info(f"  global-summary.json  — {len(summary['global'])} global fields")
        log.info(f"  countries.json       — {len(countries)} countries")
        log.info(f"  active-threats.json  — {len(threats)} threats")
        log.info(f"  global-timeseries.json — {len(timeseries)} year-points")
        if boundaries:
            log.info(f"  endemic-boundaries.json — {len(boundaries['features'])} polygons")

    log.finish(records=len(countries))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("--skip-boundaries",  action="store_true",
                        help="Skip the Natural Earth download (use if already on S3)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, skip_boundaries=args.skip_boundaries)
