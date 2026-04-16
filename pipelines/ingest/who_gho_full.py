"""
L0 — WHO GHO full global malaria burden ingest.
PRIMARY: Reads pre-fetched indicator JSONs from foundation bucket:
  imacs-mm-foundation-data-prod/raw/malaria-intelligence/who_gho/who_gho_{CODE}.json

FALLBACK: Live WHO GHO OData API if foundation file is missing.

Writes to S3 raw layer (cdah-malaria-intel-dev) and PostgreSQL fact_burden / fact_intervention.

Usage:
    python -m pipelines.ingest.who_gho_full [--dry-run] [--live] [--date YYYY-MM-DD]
"""

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"
FOUNDATION_PREFIX = "raw/malaria-intelligence/who_gho"
GHO_API = "https://ghoapi.azureedge.net/api"

# Foundation files map GHO code → filename stem
# Format: {"value": [{"SpatialDim": iso3, "TimeDim": year, "NumericValue": float, "Low", "High"}]}
FOUNDATION_FILES = {
    "MALARIA_EST_INCIDENCE":  "who_gho_MALARIA_EST_INCIDENCE.json",
    "MALARIA_EST_DEATHS":     "who_gho_MALARIA_EST_DEATHS.json",
    "MALARIA_CONF_CASES":     "who_gho_MALARIA_CONF_CASES.json",
    "MALARIA_EST_MORTALITY":  "who_gho_MALARIA_EST_MORTALITY.json",
    "MALARIA_PV_INDIG":       "who_gho_MALARIA_PV_INDIG.json",
    "MALARIA_RDT_POS":        "who_gho_MALARIA_RDT_POS.json",
    "MALARIA_SUSPECTS":       "who_gho_MALARIA_SUSPECTS.json",
}

# Additional indicators only available via live API
LIVE_ONLY_INDICATORS = {
    "MALARIA_CASES":          "cases_reported",
    "MALARIA_DEATHS":         "deaths_reported",
    "MALARIA_ITN_USE":        "itn_use_pct",
    "MALARIA_IRS_COVERAGE":   "irs_coverage_pct",
    "MALARIA_ACT_TREATMENT":  "act_coverage_pct",
    "MALARIA_IPTP3_COVERAGE": "iptp3_coverage_pct",
    "MALARIA_LLIN_DIST":      "llin_distributed",
}

# Foundation file → metric name for fact_burden / fact_intervention
FOUNDATION_METRIC_MAP = {
    "MALARIA_EST_INCIDENCE": ("incidence_per_1000",   True,  "burden"),
    "MALARIA_EST_DEATHS":    ("deaths_estimated",      True,  "burden"),
    "MALARIA_CONF_CASES":    ("cases_confirmed",       False, "burden"),
    "MALARIA_EST_MORTALITY": ("mortality_per_100k",    True,  "burden"),
    "MALARIA_PV_INDIG":      ("pv_indigenous_cases",   False, "burden"),
    "MALARIA_RDT_POS":       ("rdt_positivity_pct",    False, "intervention"),
    "MALARIA_SUSPECTS":      ("cases_suspected",       False, "burden"),
}

SOURCE_CODE = "who_gho"
DISEASE_CODE = "malaria"

_s3 = boto3.client("s3", region_name="us-east-1")


def read_foundation_gho(code: str, filename: str) -> list[dict]:
    """Read WHO GHO JSON from foundation bucket."""
    key = f"{FOUNDATION_PREFIX}/{filename}"
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
        body = resp["Body"].read()
        data = json.loads(body)
        rows = data.get("value", data) if isinstance(data, dict) else data
        return rows
    except Exception as e:
        return []


def fetch_live_indicator(code: str) -> list[dict]:
    """Fetch from WHO GHO OData API (fallback / supplement)."""
    params = {
        "$filter": "SpatialDimType eq 'COUNTRY' and TimeDimType eq 'YEAR'",
        "$select": "SpatialDim,TimeDim,NumericValue,Low,High",
        "$top": 10000,
    }
    try:
        resp = requests.get(f"{GHO_API}/{code}", params=params, timeout=90)
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception:
        return []


def run(dry_run: bool = False, live: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("who_gho_full", dry_run=dry_run)
    all_rows: list[dict] = []

    # ── Foundation bucket (primary) ────────────────────────────────────────
    with log.step("Read WHO GHO from foundation bucket"):
        for code, filename in FOUNDATION_FILES.items():
            metric, is_modeled, table = FOUNDATION_METRIC_MAP[code]
            rows = read_foundation_gho(code, filename)
            if rows:
                log.info(f"  {code}: {len(rows)} rows from foundation")
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
                            "is_modeled": is_modeled,
                            "table":      table,
                            "region":     r.get("ParentLocationCode", ""),
                        })
            else:
                log.warn(f"  {code}: not in foundation, trying live API")
                rows = fetch_live_indicator(code)
                log.info(f"  {code}: {len(rows)} rows from API")
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
                            "is_modeled": is_modeled,
                            "table":      table,
                            "region":     r.get("ParentLocationCode", ""),
                        })

    # ── Live API supplement (intervention indicators not in foundation) ────
    with log.step("Fetch intervention indicators via live API"):
        for code, metric in LIVE_ONLY_INDICATORS.items():
            rows = fetch_live_indicator(code)
            log.info(f"  {code}: {len(rows)} rows")
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
                        "value_low":  None,
                        "value_high": None,
                        "is_modeled": False,
                        "table":      "intervention",
                        "region":     "",
                    })

    log.info(f"Total rows: {len(all_rows)}")

    # ── S3 raw ─────────────────────────────────────────────────────────────
    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "record_count": len(all_rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "foundation":   list(FOUNDATION_FILES.keys()),
        },
        "rows": all_rows,
    }
    key = raw_key("who-gho-full", "burden.json", date=date)
    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])

        with log.step("Upsert → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                burden_rows = [r for r in all_rows if r["table"] == "burden"]
                int_rows    = [r for r in all_rows if r["table"] == "intervention"]

                if burden_rows:
                    SQL_B = """
                        INSERT INTO malaria.fact_burden
                            (iso3, disease_code, year, source_code, metric, value, value_low, value_high, is_modeled)
                        VALUES %s
                        ON CONFLICT (iso3, disease_code, year, source_code, metric, age_group, sex)
                        DO UPDATE SET value=EXCLUDED.value, value_low=EXCLUDED.value_low,
                                      value_high=EXCLUDED.value_high, ingested_at=NOW()
                    """
                    b_tuples = [
                        (r["iso3"], DISEASE_CODE, r["year"], SOURCE_CODE,
                         r["metric"], r["value"], r["value_low"], r["value_high"], r["is_modeled"])
                        for r in burden_rows
                    ]
                    b_tuples, b_skipped = filter_valid_iso3(b_tuples, iso3_col=0)
                    if b_skipped:
                        log.info(f"  Skipped {b_skipped} burden rows (ISO3 not in dim_country)")
                    inserted = upsert_many(SQL_B, b_tuples)
                    log.info(f"  Upserted {inserted} burden rows")

                if int_rows:
                    SQL_I = """
                        INSERT INTO malaria.fact_intervention
                            (iso3, year, source_code, indicator, value, unit)
                        VALUES %s
                        ON CONFLICT (iso3, year, source_code, indicator)
                        DO UPDATE SET value=EXCLUDED.value, ingested_at=NOW()
                    """
                    i_tuples = [
                        (r["iso3"], r["year"], SOURCE_CODE, r["metric"], r["value"],
                         "pct" if r["metric"].endswith("_pct") else "count")
                        for r in int_rows
                    ]
                    i_tuples, i_skipped = filter_valid_iso3(i_tuples, iso3_col=0)
                    if i_skipped:
                        log.info(f"  Skipped {i_skipped} intervention rows (ISO3 not in dim_country)")
                    inserted = upsert_many(SQL_I, i_tuples)
                    log.info(f"  Upserted {inserted} intervention rows")
            except Exception as e:
                log.warn(f"  DB upsert skipped: {e}")
    else:
        log.info(f"[DRY RUN] {len(all_rows)} rows → s3://{BUCKET}/{key}")

    log.finish(records=len(all_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true", help="Force live API even if foundation exists")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, live=args.live, date=args.date)
