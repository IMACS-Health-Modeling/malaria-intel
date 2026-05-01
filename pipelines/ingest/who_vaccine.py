"""
L0 — WHO malaria vaccine coverage & pipeline ingest.

Sources:
  1. WHO WIISE / WHO-UNICEF Estimates of National Immunization Coverage (WUENIC)
     API: https://immunizationdata.who.int/api/v1/coverage
     Indicators: MALARIA_RTSS (RTS,S/Mosquirix), MALARIA_R21 (R21/Matrix-M)

  2. WHO GHO malaria vaccine indicators (broader coverage estimates)
     API: https://ghoapi.azureedge.net/api

  3. WHO/PATH malaria vaccine rollout tracker (static reference data)
     Pilot countries (Ghana, Kenya, Malawi — 2019-2023) + scale-up (2024+)

Output:
  S3: raw/who-vaccine/dt=YYYY-MM-DD/vaccine-coverage.json
  DB: malaria.fact_vaccine_coverage

Usage:
    python -m pipelines.ingest.who_vaccine [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE = "who_wiise"
WHO_GHO_BASE = "https://ghoapi.azureedge.net/api"

# WHO GHO indicators for malaria vaccine-adjacent coverage metrics.
# NOTE: No dedicated RTS,S/R21 coverage indicator exists in GHO yet (data only in WIISE/WUENIC).
# MALARIA_IPTP3_COVERAGE = IPTp3 (preventive treatment in pregnancy) — not in WMR annexes.
GHO_VACCINE_INDICATORS = {
    "MALARIA_IPTP3_COVERAGE": {"vaccine_code": "iptp3", "metric": "coverage_pct"},
    "MALARIA_ITN_COVERAGE":   {"vaccine_code": "itn",   "metric": "coverage_pct"},
}

# WUENIC / WHO WIISE API — try these indicator codes
WIISE_VACCINE_INDICATORS = [
    "MALARIA_VAC1",   # 1st dose coverage
    "MALARIA_VAC3",   # 3rd dose coverage (full schedule)
    "RTSS1",          # RTS,S dose 1
    "RTSS3",          # RTS,S dose 3
]

# Static rollout reference: pilot programme + early scale-up countries
# Sources: WHO press releases, Gavi board decisions
ROLLOUT_REFERENCE = [
    # Pilot countries — Malaria Vaccine Implementation Programme (MVIP) 2019-2023
    {"iso3": "GHA", "country": "Ghana",   "intro_year": 2019, "phase": "piloting",  "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    {"iso3": "KEN", "country": "Kenya",   "intro_year": 2019, "phase": "piloting",  "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    {"iso3": "MWI", "country": "Malawi",  "intro_year": 2019, "phase": "piloting",  "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    # WHO prequalification 2021, scale-up approved Oct 2021
    {"iso3": "GHA", "country": "Ghana",   "intro_year": 2022, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    {"iso3": "KEN", "country": "Kenya",   "intro_year": 2022, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    {"iso3": "MWI", "country": "Malawi",  "intro_year": 2022, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk",             "product_name": "Mosquirix"},
    # Gavi-supported rollout 2023-2024
    {"iso3": "BFA", "country": "Burkina Faso",  "intro_year": 2023, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    {"iso3": "CMR", "country": "Cameroon",      "intro_year": 2023, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    {"iso3": "BEN", "country": "Benin",         "intro_year": 2023, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    {"iso3": "SLE", "country": "Sierra Leone",  "intro_year": 2023, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    {"iso3": "LBR", "country": "Liberia",       "intro_year": 2023, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    {"iso3": "NGA", "country": "Nigeria",       "intro_year": 2024, "phase": "scaled_up", "vaccine_code": "rtss", "manufacturer": "gsk", "product_name": "Mosquirix"},
    # R21/Matrix-M (Serum Institute / Jenner Institute) — WHO prequalified Dec 2023
    {"iso3": "GHA", "country": "Ghana",         "intro_year": 2024, "phase": "scaled_up", "vaccine_code": "r21",  "manufacturer": "serum_institute", "product_name": "R21/Matrix-M"},
    {"iso3": "NGA", "country": "Nigeria",       "intro_year": 2024, "phase": "scaled_up", "vaccine_code": "r21",  "manufacturer": "serum_institute", "product_name": "R21/Matrix-M"},
    {"iso3": "CMR", "country": "Cameroon",      "intro_year": 2024, "phase": "scaled_up", "vaccine_code": "r21",  "manufacturer": "serum_institute", "product_name": "R21/Matrix-M"},
]


def fetch_gho_vaccine(indicator: str, meta: dict) -> list[dict]:
    """Fetch one WHO GHO vaccine indicator."""
    url = f"{WHO_GHO_BASE}/{indicator}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    rows = []
    for r in resp.json().get("value", []):
        iso3 = r.get("SpatialDim", "")
        if len(iso3) != 3:
            continue
        try:
            year = int(r.get("TimeDim") or 0)
            value = float(r.get("NumericValue") or 0)
        except (ValueError, TypeError):
            continue

        row: dict = {
            "iso3":         iso3,
            "year":         year,
            "vaccine_code": meta["vaccine_code"],
            "source_code":  SOURCE_CODE,
        }
        if meta["metric"] == "coverage_pct":
            row["coverage_pct"] = value
        elif meta["metric"] == "doses_admin":
            row["doses_admin"] = int(value)
        rows.append(row)
    return rows


def fetch_wiise_coverage() -> list[dict]:
    """
    Try WHO WIISE API for malaria vaccine coverage estimates.
    Falls back gracefully if endpoint unavailable.
    """
    rows = []
    base = "https://immunizationdata.who.int/api/v1/coverage"
    for indicator in WIISE_VACCINE_INDICATORS:
        try:
            resp = requests.get(
                base,
                params={"indicator": indicator, "group": "countries", "year": "2019:2025"},
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            for r in resp.json().get("data") or resp.json():
                iso3 = str(r.get("iso3") or r.get("ISO3") or "").upper()
                if len(iso3) != 3:
                    continue
                try:
                    year = int(r.get("year") or r.get("Year") or 0)
                    cov  = float(r.get("coverage") or r.get("value") or 0)
                except (ValueError, TypeError):
                    continue
                rows.append({
                    "iso3":         iso3,
                    "year":         year,
                    "vaccine_code": "rtss" if "RTSS" in indicator else "malaria",
                    "coverage_pct": cov,
                    "source_code":  SOURCE_CODE,
                })
        except Exception:
            continue
    return rows


def build_rollout_rows() -> list[dict]:
    """Convert static rollout reference table to DB-ready rows."""
    rows = []
    for r in ROLLOUT_REFERENCE:
        rows.append({
            "iso3":                 r["iso3"],
            "year":                 r["intro_year"],
            "source_code":          "who_vaccine_pipeline",
            "vaccine_code":         r["vaccine_code"],
            "coverage_pct":         None,   # no coverage data for pipeline entries
            "doses_admin":          None,
            "target_population":    None,
            "doses_per_schedule":   4 if r["vaccine_code"] == "rtss" else 3,
            "schedule_description": "3 doses + booster at 15-18m" if r["vaccine_code"] == "rtss" else "3 doses (0,1,2m)",
            "rollout_phase":        r["phase"],
            "intro_year":           r["intro_year"],
            "pilot_country":        r["phase"] == "piloting",
            "manufacturer":         r["manufacturer"],
            "product_name":         r["product_name"],
        })
    return rows


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("who_vaccine", dry_run=dry_run)

    coverage_rows: list[dict] = []

    # 1. WHO GHO vaccine indicators
    with log.step("Fetch WHO GHO vaccine indicators"):
        for indicator, meta in GHO_VACCINE_INDICATORS.items():
            try:
                rows = fetch_gho_vaccine(indicator, meta)
                coverage_rows.extend(rows)
                log.info(f"  {indicator}: {len(rows)} rows")
            except Exception as e:
                log.warn(f"  {indicator} failed: {e}")

    # 2. WHO WIISE
    with log.step("Fetch WHO WIISE coverage"):
        try:
            wiise_rows = fetch_wiise_coverage()
            coverage_rows.extend(wiise_rows)
            log.info(f"  WIISE: {len(wiise_rows)} rows")
        except Exception as e:
            log.warn(f"  WIISE failed: {e}")

    # 3. Static rollout reference
    rollout_rows = build_rollout_rows()
    log.info(f"  Rollout reference: {len(rollout_rows)} rows")

    all_rows = coverage_rows + rollout_rows
    log.info(f"Total vaccine rows: {len(all_rows)}")

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "record_count": len(all_rows),
            "coverage_rows": len(coverage_rows),
            "rollout_rows":  len(rollout_rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": all_rows,
    }
    key = raw_key("who-vaccine", "vaccine-coverage.json", date=date)

    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_vaccine_coverage"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_vaccine_coverage
                        (iso3, year, source_code, vaccine_code, coverage_pct,
                         doses_admin, target_population, doses_per_schedule,
                         schedule_description, rollout_phase, intro_year,
                         pilot_country, manufacturer, product_name, raw_s3_key)
                    VALUES %s
                    ON CONFLICT (iso3, year, source_code, vaccine_code)
                    DO UPDATE SET
                        coverage_pct = COALESCE(EXCLUDED.coverage_pct, fact_vaccine_coverage.coverage_pct),
                        doses_admin  = COALESCE(EXCLUDED.doses_admin,  fact_vaccine_coverage.doses_admin),
                        rollout_phase = COALESCE(EXCLUDED.rollout_phase, fact_vaccine_coverage.rollout_phase),
                        ingested_at  = NOW()
                """
                db_rows = [
                    (
                        r.get("iso3"), r.get("year"), r.get("source_code", SOURCE_CODE),
                        r.get("vaccine_code"), r.get("coverage_pct"), r.get("doses_admin"),
                        r.get("target_population"), r.get("doses_per_schedule"),
                        r.get("schedule_description"), r.get("rollout_phase"),
                        r.get("intro_year"), r.get("pilot_country", False),
                        r.get("manufacturer"), r.get("product_name"), key,
                    )
                    for r in all_rows
                    if r.get("iso3") and r.get("year")
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert failed: {e}")
    else:
        log.info(f"[DRY RUN] {len(all_rows)} rows ready ({len(rollout_rows)} rollout reference rows guaranteed)")

    log.finish(records=len(all_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
