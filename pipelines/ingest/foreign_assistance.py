"""
L0 — ForeignAssistance.gov ingest
Fetches US bilateral foreign aid by country and sector.
Uses the correct USAID CKAN API endpoint (not data.usaid.gov which fails DNS).

Usage:
    python -m pipelines.ingest.foreign_assistance [--dry-run] [--date YYYY-MM-DD]

Note: The previous pipeline used data.usaid.gov which fails DNS resolution.
This version uses the correct endpoint: foreignassistance.gov data export.
"""

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

# Correct endpoint — USAID publishes full CSV downloads here
FA_CSV_URL = "https://foreignassistance.gov/data/ForeignAssistanceFunding.csv"
# Backup: sector-level download
FA_SECTOR_URL = "https://foreignassistance.gov/data/ForeignAssistanceFundingBySector.csv"

HEALTH_SECTORS = [
    "Health", "Population Policy/Programmes & Reproductive Health",
    "Basic Health Care", "Basic Health Infrastructure",
    "Infectious Disease Control", "Malaria Control",
    "COVID-19 Prevention, Detection, and Response",
]


def fetch_csv(url: str) -> list[dict]:
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    content = resp.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("foreign_assistance", dry_run=dry_run)
    records: list[dict] = []

    with log.step("Fetch ForeignAssistance.gov data"):
        try:
            rows = fetch_csv(FA_CSV_URL)
            log.info(f"  Downloaded {len(rows)} rows from primary URL")
        except Exception as e:
            log.warn(f"  Primary URL failed ({e}), trying sector URL")
            try:
                rows = fetch_csv(FA_SECTOR_URL)
                log.info(f"  Downloaded {len(rows)} rows from sector URL")
            except Exception as e2:
                log.error(f"  Both URLs failed: {e2}")
                rows = []

    with log.step("Filter to health/malaria sectors"):
        for row in rows:
            sector = row.get("Sector Name", row.get("sector_name", ""))
            country = row.get("Country Name", row.get("country_name", ""))
            year = row.get("Fiscal Year", row.get("fiscal_year", ""))
            amount = row.get("Constant Dollar Amount", row.get("disbursements_usd", 0))

            if not sector or not country:
                continue

            # Keep all health sectors
            if any(h.lower() in sector.lower() for h in HEALTH_SECTORS):
                try:
                    amt = float(str(amount).replace(",", "") or 0)
                except ValueError:
                    amt = 0

                records.append({
                    "country": country,
                    "sector": sector,
                    "fiscal_year": year,
                    "amount_usd": amt,
                    "raw_sector": sector,
                })

    log.info(f"Health sector records: {len(records)}")

    payload = {
        "_meta": {
            "source": "ForeignAssistance.gov",
            "url": FA_CSV_URL,
            "filter": "health sectors",
            "record_count": len(records),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "records": records,
    }

    key = raw_key("foreign-assistance", "country-sector.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")
    else:
        log.info(f"[DRY RUN] Would write {len(records)} records to s3://{BUCKET}/{key}")

    log.finish(records=len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
