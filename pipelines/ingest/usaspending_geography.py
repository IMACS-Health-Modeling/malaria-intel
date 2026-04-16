"""
L0 — USAspending Geography ingest
Uses the /spending_by_geography/ endpoint (fixes the broken recipient_state field
in spending_by_award). Returns malaria-related federal awards aggregated by
recipient US state.

Usage:
    python -m pipelines.ingest.usaspending_geography [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

API_BASE = "https://api.usaspending.gov/api/v2"
KEYWORDS = ["malaria", "PMI", "antimalarial", "plasmodium falciparum", "insecticide treated net"]
FISCAL_YEARS = list(range(2015, 2025))


def fetch_by_geography(keyword: str, fiscal_year: int) -> list[dict]:
    """Fetch spending aggregated by recipient state for a keyword + FY (all award types combined)."""
    payload = {
        "filters": {
            "keywords": [keyword],
            "time_period": [{"start_date": f"{fiscal_year-1}-10-01", "end_date": f"{fiscal_year}-09-30"}],
            "award_type_codes": ["02", "03", "04", "05", "A", "B", "C", "D"],
        },
        "scope": "recipient_location",
        "geo_layer": "state",
    }
    resp = requests.post(f"{API_BASE}/search/spending_by_geography/", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json().get("results", [])


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("usaspending_geography", dry_run=dry_run)

    # Aggregate: state_code -> total_usd
    state_totals: dict[str, float] = {}
    state_names: dict[str, str] = {}

    with log.step("Fetch USAspending geography data"):
        for keyword in KEYWORDS:
            for fy in FISCAL_YEARS:
                try:
                    results = fetch_by_geography(keyword, fy)
                    for r in results:
                        code = r.get("shape_code", "")
                        amt = r.get("aggregated_amount", 0) or 0
                        if code:
                            state_totals[code] = state_totals.get(code, 0) + amt
                            if r.get("display_name"):
                                state_names[code] = r["display_name"]
                    log.info(f"  kw={keyword!r} fy={fy} → {len(results)} states")
                except Exception as e:
                    log.warn(f"  Failed kw={keyword!r} fy={fy}: {e}")

    records = [
        {"state_code": code, "state_name": state_names.get(code, code), "total_usd": round(total)}
        for code, total in sorted(state_totals.items(), key=lambda x: -x[1])
    ]

    payload = {
        "_meta": {
            "source": "USAspending.gov /spending_by_geography/",
            "keywords": KEYWORDS,
            "fiscal_years": FISCAL_YEARS,
            "record_count": len(records),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "states": records,
    }

    key = raw_key("usaspending", "geography.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")
    else:
        log.info(f"[DRY RUN] Would write {len(records)} state records to s3://{BUCKET}/{key}")

    log.finish(records=len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
