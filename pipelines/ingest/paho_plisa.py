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


def fetch_paho_via_gho(indicator: str) -> list[dict]:
    """
    Fetch PAHO-region malaria data via WHO GHO, filtering to AMR region.
    More reliable than direct PAHO API.
    """
    params = {
        "$filter": f"SpatialDimType eq 'COUNTRY' and TimeDimType eq 'YEAR'",
        "$select": "SpatialDim,TimeDim,NumericValue,Low,High",
        "$top": 5000,
    }
    resp = requests.get(f"{WHO_GHO_PAHO_URL}/{indicator}", params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json().get("value", [])
    # Filter to PAHO countries
    return [r for r in rows if r.get("SpatialDim", "") in PAHO_COUNTRIES]


GHO_INDICATORS = {
    "MALARIA_EST_CASES":  "cases_estimated",
    "MALARIA_EST_DEATHS": "deaths_estimated",
    "MALARIA_INCIDENCE":  "incidence_per_1000",
    "MALARIA_CASES":      "cases_reported",
    "MALARIA_DEATHS":     "deaths_reported",
}


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("paho_plisa", dry_run=dry_run)

    all_rows: list[dict] = []

    with log.step("Fetch PAHO malaria data via WHO GHO (AMR filter)"):
        for code, metric in GHO_INDICATORS.items():
            log.info(f"  {code}")
            try:
                rows = fetch_paho_via_gho(code)
                for r in rows:
                    iso3 = r.get("SpatialDim", "")
                    year = r.get("TimeDim")
                    value = r.get("NumericValue")
                    if iso3 and year and value is not None:
                        all_rows.append({
                            "iso3":       iso3,
                            "year":       int(year),
                            "metric":     metric,
                            "value":      float(value),
                            "value_low":  float(r["Low"])  if r.get("Low")  is not None else None,
                            "value_high": float(r["High"]) if r.get("High") is not None else None,
                            "is_modeled": metric in ("cases_estimated", "deaths_estimated", "incidence_per_1000"),
                            "region":     "AMR",
                        })
                log.info(f"    → {len(rows)} AMR records")
            except Exception as e:
                log.warn(f"    {code} failed: {e}")

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
