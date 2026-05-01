"""
L0 — WHO Global Health Expenditure Database (GHED) ingest.

Sources:
  1. MALARIA_NMCP_CALCULATIONS  — Domestic malaria programme spend (raw USD, ~100 countries, 2015-2023)
     WHO GMP / National Malaria Control Programmes via WHO GHO OData API.
  2. GHED_GGHE-D_pc_US_SHA2011  — Domestic general govt health expenditure per capita USD
     (197 countries, 2000-2023 — proxy for health system investment trajectory)
  3. GHED_OOP_pc_US_SHA2011     — Out-of-pocket health expenditure per capita USD
     (financial-risk / graduation-crisis indicator)

Why this matters:
  The graduation-crisis narrative requires showing the gap between donor funding and what
  endemic countries spend themselves on malaria. This pipeline provides that domestic side.

Output:
  S3: raw/who-ghed/dt=YYYY-MM-DD/ghed-expenditure.json
  DB: malaria.fact_funding
    channel = 'government'       for GGHE-D and NMCP (domestic government spend)
    channel = 'out_of_pocket'    for OOP
    amount_type = 'total'        for MALARIA_NMCP (raw USD)
    amount_type = 'per_capita'   for GHED per-capita indicators

Usage:
    python -m pipelines.ingest.who_ghed [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE  = "who_ghed"
GHO_BASE     = "https://ghoapi.azureedge.net/api"

# Indicators to fetch from WHO GHO OData API
INDICATORS = [
    {
        "code":         "MALARIA_NMCP_CALCULATIONS",
        "label":        "Domestic malaria programme expenditure (NMCP)",
        "channel":      "government",
        "disease":      "malaria",
        "amount_type":  "total",      # raw USD (confirmed: NGA ~$2-21M range)
        "program":      "nmcp_domestic",
    },
    {
        "code":         "GHED_GGHE-D_pc_US_SHA2011",
        "label":        "Domestic general govt health expenditure per capita (USD)",
        "channel":      "government",
        "disease":      "all",
        "amount_type":  "per_capita",  # USD per capita
        "program":      "gghe_d",
    },
    {
        "code":         "GHED_OOP_pc_US_SHA2011",
        "label":        "Out-of-pocket health expenditure per capita (USD)",
        "channel":      "out_of_pocket",
        "disease":      "all",
        "amount_type":  "per_capita",
        "program":      "oop",
    },
]


def fetch_gho_indicator(code: str) -> list[dict]:
    """
    Fetch all records for a WHO GHO OData indicator.
    Returns raw API response value list.
    No auth required. Uses bare URL (no $select/$top — some indicators return 400 with those).
    """
    url = f"{GHO_BASE}/{code}"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception as e:
        return []


def parse_indicator_rows(records: list[dict], meta: dict) -> list[dict]:
    """Convert raw GHO OData records to fact_funding-ready rows."""
    rows = []
    for r in records:
        iso3 = str(r.get("SpatialDim") or "").strip()
        if len(iso3) != 3:
            continue
        try:
            year = int(r.get("TimeDim") or 0)
        except (ValueError, TypeError):
            continue
        if year < 2000 or year > 2030:
            continue
        try:
            value = float(r.get("NumericValue") or 0)
        except (ValueError, TypeError):
            continue
        if value <= 0:
            continue
        rows.append({
            "iso3":         iso3,
            "year":         year,
            "source_code":  SOURCE_CODE,
            "channel":      meta["channel"],
            "disease":      meta["disease"],
            "amount_usd":   value,
            "amount_type":  meta["amount_type"],
            "program":      meta["program"],
        })
    return rows


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("who_ghed", dry_run=dry_run)

    all_rows: list[dict] = []

    for ind in INDICATORS:
        with log.step(f"Fetch {ind['code']}"):
            records = fetch_gho_indicator(ind["code"])
            log.info(f"  Raw records: {len(records)}")
            if not records:
                log.warn(f"  No data returned for {ind['code']}")
                continue
            rows = parse_indicator_rows(records, ind)
            log.info(f"  Parsed: {len(rows)} valid rows ({ind['label']})")
            all_rows.extend(rows)

    log.info(f"Total GHED rows: {len(all_rows)}")

    # Summarise by indicator
    from collections import Counter
    by_program = Counter(r["program"] for r in all_rows)
    for prog, cnt in by_program.items():
        years = sorted({r["year"] for r in all_rows if r["program"] == prog})
        countries = len({r["iso3"] for r in all_rows if r["program"] == prog})
        log.info(f"  {prog}: {cnt} rows, {countries} countries, {min(years) if years else '?'}-{max(years) if years else '?'}")

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "indicators":   [i["code"] for i in INDICATORS],
            "record_count": len(all_rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": all_rows,
    }
    key = raw_key("who-ghed", "ghed-expenditure.json", date=date)

    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_funding"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_funding
                        (iso3, year, source_code, channel, disease,
                         amount_usd, amount_type, program)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], r["source_code"], r["channel"],
                     r["disease"], r["amount_usd"], r["amount_type"], r["program"])
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
        log.info(f"[DRY RUN] {len(all_rows)} rows ready")
        for r in all_rows[:3]:
            log.info(f"  Sample: {r}")

    log.finish(records=len(all_rows), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest WHO GHED domestic health expenditure data")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
