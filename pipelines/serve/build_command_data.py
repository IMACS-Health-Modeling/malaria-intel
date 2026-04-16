"""
L2 — Build Command page JSON for the frontend.
Queries PostgreSQL and produces:
  serving/v1/command/global-summary.json      — KPI bar data
  serving/v1/command/countries.json           — per-country burden + DCI context
  serving/v1/command/active-threats.json      — WHO DON / ProMED active outbreaks
  serving/v1/command/global-timeseries.json   — world malaria 2000-present

Usage:
    python -m pipelines.serve.build_command_data [--dry-run]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.logger import PipelineLogger
from pipelines.utils.db import fetchall, fetchone
from pipelines.utils.s3 import put_json, serving_key, BUCKET

LATEST_YEAR = 2023   # WMR data lag: 2024 report covers 2023
PREV_YEAR   = 2022


# ── Alert level ────────────────────────────────────────────────────────────

def alert_level(incidence: float | None) -> str:
    if incidence is None:
        return "none"
    if incidence >= 150: return "critical"
    if incidence >= 50:  return "high"
    if incidence >= 10:  return "moderate"
    if incidence >= 1:   return "low"
    return "none"


def dci_level(score: float | None) -> str:
    if score is None:    return "none"
    if score >= 0.8:     return "critical"
    if score >= 0.6:     return "high"
    if score >= 0.4:     return "moderate"
    if score >= 0.2:     return "low"
    return "negligible"


# ── Queries ────────────────────────────────────────────────────────────────

# Source priority for deduplication: prefer most recent WMR, fall back to WHO GHO
_SOURCE_PRIORITY = "CASE source_code WHEN 'wmr_2025' THEN 1 WHEN 'wmr_2024' THEN 2 ELSE 3 END"


def _dedup_sum(metric: str, year: int) -> float | None:
    """Sum burden values across countries using one source per country (source priority)."""
    row = fetchone(
        f"""SELECT SUM(value) as total FROM (
                SELECT DISTINCT ON (iso3) iso3, value
                FROM malaria.fact_burden
                WHERE metric=%s AND year=%s
                  AND source_code IN ('wmr_2025','wmr_2024','who_gho')
                ORDER BY iso3, {_SOURCE_PRIORITY}
            ) deduped""",
        (metric, year),
    )
    return float(row["total"]) if row and row["total"] is not None else None


def build_global_summary() -> dict:
    """World-level KPI bar: cases, deaths, funding, DCI signal."""
    # Latest year global cases — deduplicated: one source per country
    cases_total = _dedup_sum("cases_estimated", LATEST_YEAR) or 0
    cases_prev_total = _dedup_sum("cases_estimated", PREV_YEAR) or 0
    deaths_total = _dedup_sum("deaths_estimated", LATEST_YEAR) or 0
    # Global Fund disbursements latest year (exclude negative adjustment rows)
    funding_row = fetchone(
        """SELECT SUM(amount_usd) as total FROM malaria.fact_funding
           WHERE disease='malaria' AND year=%s AND amount_usd > 0""",
        (LATEST_YEAR,),
    )
    # DCI signal: count of high-DCI (>=0.6) active outbreaks
    dci_row = fetchone(
        """SELECT COUNT(*) as n, MAX(dci_score) as max_dci
           FROM malaria.fact_outbreak
           WHERE dci_score >= 0.6
             AND (status IS NULL OR status != 'closed')""",
        None,
    )
    # Countries at risk (incidence > 1/1000)
    at_risk = fetchone(
        """SELECT COUNT(DISTINCT iso3) as n FROM malaria.fact_burden
           WHERE metric='incidence_per_1000' AND year=%s AND value > 1.0""",
        (LATEST_YEAR,),
    )

    yoy_pct = None
    if cases_prev_total > 0:
        yoy_pct = round((cases_total - cases_prev_total) / cases_prev_total * 100, 1)

    return {
        "year":            LATEST_YEAR,
        "cases_estimated": round(cases_total),
        "cases_yoy_pct":   yoy_pct,
        "deaths_estimated": round(deaths_total),
        "funding_usd":     round(float(funding_row["total"] or 0)) if funding_row else None,
        "dci_signal": {
            "high_dci_events": int(dci_row["n"] or 0) if dci_row else 0,
            "max_dci_score":   round(float(dci_row["max_dci"] or 0), 3) if dci_row else 0,
            "level":           dci_level(float(dci_row["max_dci"] or 0)) if dci_row else "none",
        },
        "countries_at_risk": int(at_risk["n"] or 0) if at_risk else 0,
    }


def build_countries() -> list[dict]:
    """Per-country burden summary for choropleth + sidebar table."""
    rows = fetchall(
        """SELECT
               dc.iso3, dc.name, dc.region, dc.lat, dc.lng, dc.is_endemic,
               inc.value AS incidence,
               inc.year  AS incidence_year,
               cas.value AS cases_est,
               dth.value AS deaths_est,
               cas_prev.value AS cases_prev,
               itn.value AS itn_use_pct
           FROM malaria.dim_country dc
           LEFT JOIN LATERAL (
               SELECT value, year FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='incidence_per_1000'
               ORDER BY year DESC LIMIT 1
           ) inc ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='cases_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1 WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
           ) cas ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='deaths_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1 WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
           ) dth ON TRUE
           LEFT JOIN LATERAL (
               SELECT value FROM malaria.fact_burden
               WHERE iso3=dc.iso3 AND metric='cases_estimated' AND year=%s
                 AND source_code IN ('wmr_2025','wmr_2024','who_gho')
               ORDER BY CASE source_code WHEN 'wmr_2025' THEN 1 WHEN 'wmr_2024' THEN 2 ELSE 3 END LIMIT 1
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
        cases = float(r["cases_est"] or 0)
        cases_prev = float(r["cases_prev"] or 0)
        yoy = round((cases - cases_prev) / cases_prev * 100, 1) if cases_prev > 0 else None
        inc = r["incidence"]
        countries.append({
            "iso3":          r["iso3"],
            "name":          r["name"],
            "region":        r["region"],
            "lat":           r["lat"],
            "lng":           r["lng"],
            "is_endemic":    r["is_endemic"],
            "incidence":     round(float(inc), 2) if inc else None,
            "cases_est":     round(cases) if cases else None,
            "deaths_est":    round(float(r["deaths_est"] or 0)) if r["deaths_est"] else None,
            "cases_yoy_pct": yoy,
            "itn_use_pct":   round(float(r["itn_use_pct"]), 1) if r["itn_use_pct"] else None,
            "alert_level":   alert_level(float(inc) if inc else None),
        })
    return countries


_MALARIA_DISEASE_KEYWORDS = {"malaria", "plasmodium", "falciparum", "vivax", "malariae", "ovale"}


def _is_malaria_event(disease: str | None) -> bool:
    if not disease:
        return False
    d = disease.lower()
    return any(kw in d for kw in _MALARIA_DISEASE_KEYWORDS)


def build_active_threats() -> list[dict]:
    """Active outbreak events with DCI scores for ThreatTicker.

    Returns all disease outbreaks active in the past 365 days, with malaria
    events flagged and sorted first. Non-malaria events provide co-infection
    and crisis context for malaria-endemic countries.
    """
    rows = fetchall(
        """SELECT
               fo.event_id, fo.disease, fo.event_type,
               fo.country_iso3, dc.name AS country_name,
               fo.start_date, fo.cases_reported, fo.deaths_reported,
               fo.dci_score, fo.severity_score, fo.narrative,
               fo.source, fo.source_url
           FROM malaria.fact_outbreak fo
           LEFT JOIN malaria.dim_country dc ON dc.iso3 = fo.country_iso3
           WHERE (fo.status IS NULL OR fo.status != 'closed')
             AND fo.start_date >= NOW() - INTERVAL '365 days'
           ORDER BY fo.dci_score DESC NULLS LAST, fo.start_date DESC
           LIMIT 100"""
    )

    threats = [
        {
            "event_id":      r["event_id"],
            "disease":       r["disease"],
            "event_type":    r["event_type"],
            "iso3":          r["country_iso3"],
            "country":       r["country_name"] or r["country_iso3"],
            "start_date":    str(r["start_date"]) if r["start_date"] else None,
            "cases":         r["cases_reported"],
            "deaths":        r["deaths_reported"],
            "dci_score":     round(float(r["dci_score"]), 3) if r["dci_score"] else None,
            "dci_level":     dci_level(r["dci_score"]),
            "severity":      round(float(r["severity_score"]), 2) if r["severity_score"] else None,
            "narrative":     (r["narrative"] or "")[:300],
            "source":        r["source"],
            "source_url":    r["source_url"],
            "is_malaria":    _is_malaria_event(r["disease"]),
        }
        for r in rows
    ]
    # Sort: malaria events first, then by DCI score descending
    threats.sort(key=lambda t: (0 if t["is_malaria"] else 1, -(t["dci_score"] or 0)))
    return threats


def build_global_timeseries() -> list[dict]:
    """World malaria cases/deaths 2000–present for trend chart."""
    # Deduplicate: one source per (iso3, year, metric) using source priority
    rows = fetchall(
        f"""SELECT year, metric, SUM(value) AS total
            FROM (
                SELECT DISTINCT ON (iso3, year, metric) iso3, year, metric, value
                FROM malaria.fact_burden
                WHERE metric IN ('cases_estimated', 'deaths_estimated')
                  AND source_code IN ('wmr_2025','wmr_2024','who_gho')
                  AND year >= 2000
                ORDER BY iso3, year, metric, {_SOURCE_PRIORITY}
            ) deduped
            GROUP BY year, metric
            ORDER BY year, metric"""
    )

    # Pivot to [{year, cases, deaths}, ...]
    by_year: dict[int, dict] = {}
    for r in rows:
        yr = r["year"]
        if yr not in by_year:
            by_year[yr] = {"year": yr, "cases": None, "deaths": None}
        if r["metric"] == "cases_estimated":
            by_year[yr]["cases"] = round(float(r["total"] or 0))
        else:
            by_year[yr]["deaths"] = round(float(r["total"] or 0))

    return sorted(by_year.values(), key=lambda x: x["year"])


def run(dry_run: bool = False) -> None:
    log = PipelineLogger("build_command_data", dry_run=dry_run)

    # ── Build all JSON payloads ────────────────────────────────────────────
    with log.step("Build global summary"):
        summary = build_global_summary()
        log.info(f"  Cases: {summary['cases_estimated']:,}  Deaths: {summary['deaths_estimated']:,}")
        log.info(f"  DCI signal: {summary['dci_signal']}")

    with log.step("Build country data"):
        countries = build_countries()
        log.info(f"  {len(countries)} countries with burden data")

    with log.step("Build active threats"):
        threats = build_active_threats()
        log.info(f"  {len(threats)} active outbreak events")

    with log.step("Build global timeseries"):
        timeseries = build_global_timeseries()
        log.info(f"  {len(timeseries)} year-points")

    meta = {"generated_at": datetime.now(timezone.utc).isoformat(), "data_year": LATEST_YEAR}

    if not dry_run:
        with log.step("Upload to S3 serving layer"):
            put_json(serving_key("command", "global-summary.json"),    {**meta, **summary})
            put_json(serving_key("command", "countries.json"),         {**meta, "countries": countries})
            put_json(serving_key("command", "active-threats.json"),    {**meta, "threats": threats})
            put_json(serving_key("command", "global-timeseries.json"), {**meta, "timeseries": timeseries})
            log.info(f"  4 files written to s3://{BUCKET}/serving/v1/command/")
    else:
        log.info("[DRY RUN] Would write 4 serving JSON files")
        log.info(f"  Summary keys: {list(summary.keys())}")
        log.info(f"  Countries: {len(countries)}, Threats: {len(threats)}, TS points: {len(timeseries)}")

    log.finish(records=len(countries))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
