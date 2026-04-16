"""
L0 — CDC MMWR Malaria Surveillance ingest.
Downloads annual malaria surveillance reports from CDC.
Uses Bedrock Haiku to extract structured summary statistics
when the structured CSV is unavailable.

Reports cover US-diagnosed malaria cases by country of acquisition.

Usage:
    python -m pipelines.ingest.cdc_mmwr_malaria [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

# CDC MMWR Malaria Surveillance URLs
# Reports are published annually with ~1 year lag
CDC_MMWR_URLS = [
    # Structured data (preferred)
    "https://www.cdc.gov/malaria/php/surveillance-report/index.html",
    # Surveillance summary PDFs / HTML tables
    "https://www.cdc.gov/mmwr/volumes/73/ss/ss7303a1.htm",  # 2024 report (2022 data)
    "https://www.cdc.gov/mmwr/volumes/72/ss/ss7202a1.htm",  # 2023 report (2021 data)
    "https://www.cdc.gov/mmwr/volumes/71/ss/ss7102a1.htm",  # 2022 report (2020 data)
]

# CDC data API (if available)
CDC_OPEN_DATA = "https://data.cdc.gov/api/views"
MMWR_DATASET_ID = "4a9r-qpxj"  # Malaria Surveillance Dataset

SOURCE_CODE = "cdc_mmwr"


def fetch_cdc_opendata() -> list[dict]:
    """Try CDC Open Data Portal for structured malaria data."""
    try:
        url = f"https://data.cdc.gov/resource/{MMWR_DATASET_ID}.json"
        params = {"$limit": 50000, "$where": "disease='Malaria'"}
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def fetch_mmwr_html(url: str) -> str:
    """Fetch MMWR report HTML."""
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "malaria-intel-pipeline/1.0"})
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def extract_mmwr_data_with_bedrock(html: str, report_year: int) -> list[dict]:
    """Use Bedrock Haiku to extract table data from MMWR HTML."""
    from pipelines.utils.bedrock import invoke, HAIKU_MODEL, extract_json

    # Trim HTML to relevant section (tables)
    import re
    # Extract text from table elements
    table_text = re.sub(r'<[^>]+>', ' ', html)
    table_text = re.sub(r'\s+', ' ', table_text)[:4000]

    prompt = f"""You are extracting malaria surveillance data from a CDC MMWR report for year {report_year}.

Extract the following from this text:
1. Total US malaria cases reported
2. Total deaths
3. Top 5 countries of acquisition with case counts
4. Cases by region (Africa, Asia, Americas, Other)

Return ONLY valid JSON:
{{
  "report_year": {report_year},
  "total_cases": integer or null,
  "total_deaths": integer or null,
  "countries_of_acquisition": [{{"country": "name", "iso3": "XXX", "cases": integer}}],
  "by_region": {{"africa": integer, "asia": integer, "americas": integer, "other": integer}}
}}

CDC MMWR text:
{table_text}"""

    try:
        response = invoke(HAIKU_MODEL, prompt, max_tokens=512)
        return [extract_json(response)] if extract_json(response) else []
    except Exception:
        return []


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("cdc_mmwr_malaria", dry_run=dry_run)
    all_records: list[dict] = []

    # ── Try CDC Open Data Portal ───────────────────────────────────────────
    with log.step("Fetch CDC Open Data malaria dataset"):
        records = fetch_cdc_opendata()
        if records:
            log.info(f"  {len(records)} records from Open Data Portal")
            all_records.extend(records)

    # ── Scrape MMWR reports with Bedrock ───────────────────────────────────
    if not all_records:
        with log.step("Scrape MMWR reports + Bedrock extraction"):
            for i, url in enumerate(CDC_MMWR_URLS[1:]):  # Skip index page
                report_year = 2024 - i
                log.info(f"  Fetching {url}")
                html = fetch_mmwr_html(url)
                if not html:
                    log.warn(f"  Could not fetch {url}")
                    continue

                if not dry_run:
                    extracted = extract_mmwr_data_with_bedrock(html, report_year)
                    if extracted:
                        log.info(f"  Extracted: {extracted[0].get('total_cases')} cases for {report_year}")
                        all_records.extend([
                            {
                                "source":       SOURCE_CODE,
                                "report_year":  report_year,
                                "raw_url":      url,
                                **rec,
                            }
                            for rec in extracted if rec
                        ])
                else:
                    log.info(f"  [DRY RUN] Would extract from {url}")

    log.info(f"Total MMWR records: {len(all_records)}")

    # ── S3 raw ─────────────────────────────────────────────────────────────
    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "record_count": len(all_records),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "records": all_records,
    }
    key = raw_key("cdc-mmwr", "malaria-surveillance.json", date=date)
    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        # Structured records → fact_burden (US cases reported)
        with log.step("Upsert → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many

                burden_rows = []
                for rec in all_records:
                    if not rec.get("report_year"):
                        continue
                    # US total cases
                    if rec.get("total_cases") is not None:
                        burden_rows.append((
                            "USA", "malaria", int(rec["report_year"]) - 1,
                            SOURCE_CODE, "cases_reported",
                            float(rec["total_cases"]), None, None, False,
                        ))
                    if rec.get("total_deaths") is not None:
                        burden_rows.append((
                            "USA", "malaria", int(rec["report_year"]) - 1,
                            SOURCE_CODE, "deaths_reported",
                            float(rec["total_deaths"]), None, None, False,
                        ))

                if burden_rows:
                    SQL = """
                        INSERT INTO malaria.fact_burden
                            (iso3, disease_code, year, source_code, metric, value, value_low, value_high, is_modeled)
                        VALUES %s
                        ON CONFLICT (iso3, disease_code, year, source_code, metric, age_group, sex)
                        DO UPDATE SET value = EXCLUDED.value, ingested_at = NOW()
                    """
                    inserted = upsert_many(SQL, burden_rows)
                    log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert skipped: {e}")
    else:
        log.info(f"[DRY RUN] Would write {len(all_records)} records")

    log.finish(records=len(all_records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
