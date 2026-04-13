"""
L0 — WHO / RBM burden data ingest
Fetches country-level malaria burden indicators from WHO Global Health Observatory API.

Usage:
    python -m pipelines.ingest.who_rbm [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

GHO_API = "https://ghoapi.azureedge.net/api"

# WHO GHO indicator codes for malaria
INDICATORS = {
    "MALARIA_CASES":       "Malaria cases reported",
    "MALARIA_DEATHS":      "Malaria estimated deaths",
    "MALARIA_INCIDENCE":   "Malaria incidence (per 1000 population at risk)",
    "MALARIA_ITN_USE":     "Children sleeping under insecticide-treated mosquito nets",
    "MALARIA_IRS_COVERAGE": "Children (under 5) sleeping under ITNs",
}

PMI_COUNTRIES = [
    "MOZ","TZA","NGA","ETH","UGA","KEN","GHA","MDG","MWI","ZMB",
    "COD","MLI","SEN","CMR","BFA","GIN","ZWE","RWA","TGO","BEN",
    "SDN","AGO","LSO","SWZ","MMR","PNG","HTI",
]


def fetch_indicator(code: str) -> list[dict]:
    params = {
        "$filter": "SpatialDimType eq 'COUNTRY' and TimeDimType eq 'YEAR'",
        "$select": "SpatialDim,TimeDim,NumericValue,Low,High",
        "$top": 10000,
    }
    resp = requests.get(f"{GHO_API}/{code}", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json().get("value", [])


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("who_rbm", dry_run=dry_run)
    country_data: dict[str, dict] = {iso3: {"iso3": iso3, "indicators": {}} for iso3 in PMI_COUNTRIES}

    with log.step("Fetch WHO GHO indicators"):
        for code, label in INDICATORS.items():
            log.info(f"  Fetching {code}: {label}")
            try:
                rows = fetch_indicator(code)
                log.info(f"    → {len(rows)} records")
                for row in rows:
                    iso3 = row.get("SpatialDim", "")
                    year = row.get("TimeDim")
                    value = row.get("NumericValue")
                    if iso3 in country_data and year and value is not None:
                        if code not in country_data[iso3]["indicators"]:
                            country_data[iso3]["indicators"][code] = {}
                        country_data[iso3]["indicators"][code][str(year)] = {
                            "value": value,
                            "low": row.get("Low"),
                            "high": row.get("High"),
                        }
            except Exception as e:
                log.warn(f"    Failed: {e}")

    records = list(country_data.values())

    payload = {
        "_meta": {
            "source": "WHO Global Health Observatory API",
            "indicators": INDICATORS,
            "countries": PMI_COUNTRIES,
            "record_count": len(records),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "countries": records,
    }

    key = raw_key("who-rbm", "country-burden.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")
    else:
        log.info(f"[DRY RUN] Would write {len(records)} country records to s3://{BUCKET}/{key}")

    log.finish(records=len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
