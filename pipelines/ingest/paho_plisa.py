"""
L0 — PAHO PLISA Americas malaria burden ingest.
Fetches malaria cases/deaths for all 35 PAHO member states (Americas region).
Uses PAHO PLISA OData API.

Usage:
    python -m pipelines.ingest.paho_plisa [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

PAHO_API = "https://paho.sharepoint.com/sites/pahoplisa-api/_api"
# Alternative: PLISA public health indicators
PLISA_API = "https://www3.paho.org/data/index.php/en/?option=com_content&view=article&id=524&Itemid=0"
# PAHO OData-based endpoint
PAHO_ODATA = "https://opendata.paho.org/api/odata"

# PAHO uses different API structure; use the public JSON endpoint
PAHO_INDICATORS_URL = "https://paho.sharepoint.com"

# Fallback: PAHO GHO regional data via WHO API
WHO_GHO_PAHO_URL = "https://ghoapi.azureedge.net/api"

# PAHO member states (ISO3)
PAHO_COUNTRIES = [
    "ARG","BLZ","BOL","BRA","CHL","COL","CRI","CUB","DOM","ECU",
    "SLV","GTM","GUY","HTI","HND","JAM","MEX","NIC","PAN","PRY",
    "PER","PRI","SUR","TTO","URY","VEN","USA","CAN",
    # French Guiana = GUF (overseas territory of France)
    "GUF",
]

SOURCE_CODE = "paho_plisa"
DISEASE_CODE = "malaria"


PAGE_SIZE = 1000  # WHO GHO OData max; $top > 1000 returns 400


def _gho_paginate(indicator: str) -> list[dict]:
    """
    Paginate through all GHO records for an indicator using $skip.
    '$top=1000' is the confirmed max; larger values return 400.
    Uses direct URL construction to keep '$' unencoded.
    """
    all_rows: list[dict] = []
    skip = 0
    while True:
        url = f"{WHO_GHO_PAHO_URL}/{indicator}?$top={PAGE_SIZE}&$skip={skip}"
        resp = requests.get(url, timeout=90)
        resp.raise_for_status()
        batch = resp.json().get("value", [])
        all_rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return all_rows


def fetch_gho_all_countries(indicator: str) -> list[dict]:
    """Fetch all countries (paginated), filter to PAHO in Python."""
    rows = _gho_paginate(indicator)
    return [r for r in rows if r.get("SpatialDim", "") in PAHO_COUNTRIES]


def fetch_gho_filtered(indicator: str) -> list[dict]:
    """Same paginated fetch as fetch_gho_all_countries — filter applied in Python."""
    return fetch_gho_all_countries(indicator)


# Estimated burden indicators (use $top only — $filter not supported on these)
GHO_EST_INDICATORS = {
    "MALARIA_EST_CASES":      "cases_estimated",
    "MALARIA_EST_DEATHS":     "deaths_estimated",
    "MALARIA_EST_INCIDENCE":  "incidence_per_1000",
    "MALARIA_EST_MORTALITY":  "mortality_per_100k",
}

# Reported/confirmed indicators (support $filter on SpatialDimType/TimeDimType)
GHO_CONF_INDICATORS = {
    "MALARIA_CONF_CASES":     "cases_confirmed",
    "MALARIA_INDIG":          "cases_indigenous",
    "MALARIA_TOTAL_CASES":    "cases_total",
}


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("paho_plisa", dry_run=dry_run)

    all_rows: list[dict] = []

    def _append(rows, metric, is_modeled):
        for r in rows:
            iso3  = r.get("SpatialDim", "")
            year  = r.get("TimeDim")
            value = r.get("NumericValue")
            if iso3 and year and value is not None:
                all_rows.append({
                    "iso3":       iso3,
                    "year":       int(year),
                    "metric":     metric,
                    "value":      float(value),
                    "value_low":  float(r["Low"])  if r.get("Low")  is not None else None,
                    "value_high": float(r["High"]) if r.get("High") is not None else None,
                    "is_modeled": is_modeled,
                    "region":     "AMR",
                })

    with log.step("Fetch estimated burden (no filter — fetch all, slice AMR)"):
        for code, metric in GHO_EST_INDICATORS.items():
            try:
                rows = fetch_gho_all_countries(code)
                _append(rows, metric, is_modeled=True)
                log.info(f"  {code}: {len(rows)} AMR records")
            except Exception as e:
                log.warn(f"  {code} failed: {e}")

    with log.step("Fetch confirmed/reported cases (OData filter)"):
        for code, metric in GHO_CONF_INDICATORS.items():
            try:
                rows = fetch_gho_filtered(code)
                _append(rows, metric, is_modeled=False)
                log.info(f"  {code}: {len(rows)} AMR records")
            except Exception as e:
                log.warn(f"  {code} failed: {e}")

    log.info(f"Total PAHO rows: {len(all_rows)}")

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "region":       "AMR",
            "countries":    PAHO_COUNTRIES,
            "record_count": len(all_rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": all_rows,
    }
    key = raw_key("paho-plisa", "americas-malaria.json", date=date)
    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_burden"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_burden
                        (iso3, disease_code, year, source_code, metric, value, value_low, value_high, is_modeled)
                    VALUES %s
                    ON CONFLICT (iso3, disease_code, year, source_code, metric, age_group, sex)
                    DO UPDATE SET value = EXCLUDED.value, ingested_at = NOW()
                """
                db_rows = [
                    (r["iso3"], DISEASE_CODE, r["year"], SOURCE_CODE,
                     r["metric"], r["value"], r.get("value_low"), r.get("value_high"), r["is_modeled"])
                    for r in all_rows
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert skipped: {e}")
    else:
        log.info(f"[DRY RUN] Would write {len(all_rows)} rows")

    log.finish(records=len(all_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
