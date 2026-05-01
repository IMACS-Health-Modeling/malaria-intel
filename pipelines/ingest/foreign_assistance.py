"""
L0 — Foreign assistance malaria funding ingest via USAspending.gov API.
ForeignAssistance.gov was taken offline (2025); data is now sourced from
USAspending.gov /spending_by_geography/ with place_of_performance scope.

Fetches malaria-related US foreign assistance spend aggregated by recipient
country and fiscal year, then upserts to fact_funding.

Usage:
    python -m pipelines.ingest.foreign_assistance [--dry-run] [--date YYYY-MM-DD]
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
KEYWORDS = ["malaria", "PMI", "antimalarial", "plasmodium", "insecticide treated net", "bed net"]
FISCAL_YEARS = list(range(2015, 2026))
SOURCE_CODE = "usaspending"

# USAspending country name → ISO3 (common mappings)
_COUNTRY_ISO3: dict[str, str] = {
    "nigeria": "NGA", "democratic republic of the congo": "COD", "ethiopia": "ETH",
    "uganda": "UGA", "mozambique": "MOZ", "tanzania": "TZA", "ghana": "GHA",
    "kenya": "KEN", "zambia": "ZMB", "malawi": "MWI", "mali": "MLI",
    "burkina faso": "BFA", "cameroon": "CMR", "guinea": "GIN", "madagascar": "MDG",
    "niger": "NER", "rwanda": "RWA", "senegal": "SEN", "sierra leone": "SLE",
    "togo": "TGO", "benin": "BEN", "angola": "AGO", "south sudan": "SSD",
    "somalia": "SOM", "cote d'ivoire": "CIV", "ivory coast": "CIV",
    "zimbabwe": "ZWE", "liberia": "LBR", "central african republic": "CAF",
    "chad": "TCD", "burundi": "BDI", "congo": "COG",
    "papua new guinea": "PNG", "indonesia": "IDN", "india": "IND",
    "myanmar": "MMR", "cambodia": "KHM", "laos": "LAO", "vietnam": "VNM",
    "pakistan": "PAK", "haiti": "HTI", "colombia": "COL", "peru": "PER",
    "sudan": "SDN", "eritrea": "ERI", "comoros": "COM", "gambia": "GMB",
    "equatorial guinea": "GNQ", "gabon": "GAB", "sao tome and principe": "STP",
    "djibouti": "DJI", "namibia": "NAM", "botswana": "BWA", "lesotho": "LSO",
    "eswatini": "SWZ", "swaziland": "SWZ",
}


def _to_iso3(name: str) -> str | None:
    return _COUNTRY_ISO3.get(name.lower().strip())


def fetch_country_spend(keyword: str, fiscal_year: int) -> list[dict]:
    """Fetch malaria spend by place-of-performance country for one keyword + FY."""
    payload = {
        "filters": {
            "keywords": [keyword],
            "time_period": [{"start_date": f"{fiscal_year-1}-10-01",
                             "end_date": f"{fiscal_year}-09-30"}],
            "award_type_codes": ["02", "03", "04", "05", "A", "B", "C", "D"],
        },
        "scope": "place_of_performance",
        "geo_layer": "country",
    }
    try:
        resp = requests.post(
            f"{API_BASE}/search/spending_by_geography/",
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("foreign_assistance", dry_run=dry_run)

    # (iso3, year) -> total_usd
    spend: dict[tuple[str, int], float] = {}
    country_names: dict[str, str] = {}

    with log.step("Fetch USAspending country-level malaria spend"):
        for keyword in KEYWORDS:
            for fy in FISCAL_YEARS:
                results = fetch_country_spend(keyword, fy)
                for r in results:
                    country = r.get("display_name", "")
                    iso3 = _to_iso3(country)
                    if not iso3:
                        continue
                    amt = float(r.get("aggregated_amount", 0) or 0)
                    if amt <= 0:
                        continue
                    key = (iso3, fy)
                    spend[key] = spend.get(key, 0.0) + amt
                    country_names[iso3] = country

        log.info(f"  {len(spend)} (iso3, year) pairs aggregated from USAspending")

    records = [
        {"iso3": iso3, "year": yr, "amount_usd": amt, "channel": "usaid_bilateral"}
        for (iso3, yr), amt in spend.items()
    ]

    payload = {
        "_meta": {
            "source": SOURCE_CODE,
            "keywords": KEYWORDS,
            "fiscal_years": FISCAL_YEARS,
            "record_count": len(records),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "records": records,
    }

    key = raw_key("foreign-assistance", "country-year.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_funding"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_funding
                        (iso3, year, source_code, channel, disease, amount_usd, amount_type)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], SOURCE_CODE, r["channel"],
                     "malaria", r["amount_usd"], "disbursed")
                    for r in records
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] {len(records)} country-year records")

    log.finish(records=len(records), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
