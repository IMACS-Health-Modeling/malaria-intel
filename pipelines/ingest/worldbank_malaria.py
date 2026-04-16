"""
L0 — World Bank malaria indicators ingest.
Reads pre-fetched World Bank JSON files from foundation bucket:
  raw/malaria-intelligence/worldbank/wb_SH_MLR_INCD_P3.json   — incidence per 1000 (1.1MB)
  raw/malaria-intelligence/worldbank/wb_SH_MLR_NETS_ZS.json   — ITN use % (79KB)
  raw/malaria-intelligence/worldbank/wb_SH_MLR_TRET_ZS.json   — treatment rate % (91KB)
  raw/malaria-intelligence/worldbank/wb_SH_STA_MALR.json      — malaria deaths (543KB)

WB format: [{countryiso3code, date, value, indicator: {id, value}}, ...]

Writes to fact_burden (incidence, deaths) and fact_intervention (ITN, treatment).

Usage:
    python -m pipelines.ingest.worldbank_malaria [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

WB_FILES = {
    "SH_MLR_INCD_P3": {
        "key":    "raw/malaria-intelligence/worldbank/wb_SH_MLR_INCD_P3.json",
        "metric": "incidence_per_1000",
        "table":  "burden",
        "is_modeled": True,
    },
    "SH_STA_MALR": {
        "key":    "raw/malaria-intelligence/worldbank/wb_SH_STA_MALR.json",
        "metric": "deaths_reported",
        "table":  "burden",
        "is_modeled": False,
    },
    "SH_MLR_NETS_ZS": {
        "key":    "raw/malaria-intelligence/worldbank/wb_SH_MLR_NETS_ZS.json",
        "metric": "itn_use_pct",
        "table":  "intervention",
        "is_modeled": False,
    },
    "SH_MLR_TRET_ZS": {
        "key":    "raw/malaria-intelligence/worldbank/wb_SH_MLR_TRET_ZS.json",
        "metric": "act_coverage_pct",
        "table":  "intervention",
        "is_modeled": False,
    },
}

SOURCE_CODE = "worldbank"
DISEASE_CODE = "malaria"
_s3 = boto3.client("s3", region_name="us-east-1")


def load_wb_json(key: str) -> list[dict]:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
        data = json.loads(resp["Body"].read())
        # WB format: either direct array or [metadata, data_array]
        if isinstance(data, list):
            if len(data) == 2 and isinstance(data[1], list):
                return data[1]  # [pagination_meta, rows]
            return data
        return data.get("value", data.get("data", []))
    except Exception:
        return []


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("worldbank_malaria", dry_run=dry_run)
    all_rows: list[dict] = []

    for indicator_code, spec in WB_FILES.items():
        with log.step(f"Load WB {indicator_code}"):
            records = load_wb_json(spec["key"])
            if not records:
                log.warn(f"  Not found or empty: {spec['key']}")
                continue
            log.info(f"  {len(records)} records")

            for r in records:
                iso3  = (r.get("countryiso3code") or r.get("country", {}).get("id", "")
                         if isinstance(r.get("country"), dict) else r.get("iso3", "")).upper()
                if not iso3 or len(iso3) != 3:
                    continue

                year_raw = r.get("date") or r.get("year") or ""
                try:
                    year = int(str(year_raw).strip())
                except (ValueError, TypeError):
                    continue

                value = r.get("value")
                if value is None:
                    continue
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    continue

                all_rows.append({
                    "iso3":       iso3,
                    "year":       year,
                    "metric":     spec["metric"],
                    "table":      spec["table"],
                    "value":      value,
                    "is_modeled": spec["is_modeled"],
                })

    log.info(f"Total WB rows: {len(all_rows)}")

    payload = {
        "_meta": {"source": SOURCE_CODE, "record_count": len(all_rows),
                  "fetched_at": datetime.now(timezone.utc).isoformat()},
        "rows": all_rows,
    }
    key = raw_key("worldbank-malaria", "wb-indicators.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3

                burden_rows = [r for r in all_rows if r["table"] == "burden"]
                int_rows    = [r for r in all_rows if r["table"] == "intervention"]

                if burden_rows:
                    SQL_B = """
                        INSERT INTO malaria.fact_burden
                            (iso3, disease_code, year, source_code, metric, value, is_modeled)
                        VALUES %s
                        ON CONFLICT (iso3, disease_code, year, source_code, metric, age_group, sex)
                        DO UPDATE SET value=EXCLUDED.value, ingested_at=NOW()
                    """
                    b_tuples = [
                        (r["iso3"], DISEASE_CODE, r["year"], SOURCE_CODE,
                         r["metric"], r["value"], r["is_modeled"])
                        for r in burden_rows
                    ]
                    b_tuples, b_skip = filter_valid_iso3(b_tuples, iso3_col=0)
                    if b_skip:
                        log.info(f"  Skipped {b_skip} burden rows (ISO3 not in dim_country)")
                    upsert_many(SQL_B, b_tuples)
                    log.info(f"  Upserted {len(b_tuples)} burden rows")

                if int_rows:
                    SQL_I = """
                        INSERT INTO malaria.fact_intervention
                            (iso3, year, source_code, indicator, value, unit)
                        VALUES %s
                        ON CONFLICT (iso3, year, source_code, indicator)
                        DO UPDATE SET value=EXCLUDED.value, ingested_at=NOW()
                    """
                    i_tuples = [
                        (r["iso3"], r["year"], SOURCE_CODE, r["metric"], r["value"], "pct")
                        for r in int_rows
                    ]
                    i_tuples, i_skip = filter_valid_iso3(i_tuples, iso3_col=0)
                    if i_skip:
                        log.info(f"  Skipped {i_skip} intervention rows (ISO3 not in dim_country)")
                    upsert_many(SQL_I, i_tuples)
                    log.info(f"  Upserted {len(i_tuples)} intervention rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] {len(all_rows)} rows")

    log.finish(records=len(all_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
