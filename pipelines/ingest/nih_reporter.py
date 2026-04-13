"""
L0 — NIH Reporter ingest
Fetches malaria R&D grants from the NIH Reporter API, extracts institution
state, and writes date-partitioned JSON to S3.

Usage:
    python -m pipelines.ingest.nih_reporter [--dry-run] [--date YYYY-MM-DD]

Env vars:
    MALARIA_INTEL_BUCKET  (default: cdah-malaria-intel-dev)
    NIH_REPORTER_API      (default: https://api.reporter.nih.gov/v2)
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

API_BASE = "https://api.reporter.nih.gov/v2"
SEARCH_TERMS = ["malaria", "plasmodium", "antimalarial", "artemisinin", "bed net", "insecticide treated net"]
FISCAL_YEARS = list(range(2015, 2026))


def fetch_grants(term: str, fiscal_years: list[int], offset: int = 0) -> dict:
    payload = {
        "criteria": {
            "advanced_text_search": {
                "operator": "and",
                "search_field": "all",
                "search_text": term,
            },
            "fiscal_years": fiscal_years,
        },
        "offset": offset,
        "limit": 500,
        "fields": [
            "project_num", "project_title", "fiscal_year",
            "award_amount", "organization", "principal_investigators",
            "project_start_date", "project_end_date", "abstract_text",
        ],
    }
    resp = requests.post(f"{API_BASE}/projects/search", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("nih_reporter", dry_run=dry_run)
    all_grants: list[dict] = []

    with log.step("Fetch NIH Reporter grants"):
        for term in SEARCH_TERMS:
            log.info(f"  Searching: '{term}'")
            offset = 0
            while True:
                try:
                    result = fetch_grants(term, FISCAL_YEARS, offset)
                except Exception as e:
                    log.warn(f"  Failed for term '{term}' offset {offset}: {e}")
                    break

                hits = result.get("results", [])
                all_grants.extend(hits)
                total = result.get("meta", {}).get("total", 0)
                log.info(f"  term={term!r} offset={offset} fetched={len(hits)} total={total}")

                if offset + len(hits) >= total:
                    break
                offset += 500

    # Deduplicate by project_num
    seen: set[str] = set()
    unique_grants = []
    for g in all_grants:
        pn = g.get("project_num", "")
        if pn and pn not in seen:
            seen.add(pn)
            unique_grants.append(g)

    log.info(f"Total unique grants: {len(unique_grants)}")

    # Enrich with state from organization
    for g in unique_grants:
        org = g.get("organization", {}) or {}
        g["_state"] = org.get("org_state", "")
        g["_org_name"] = org.get("org_name", "")
        g["_city"] = org.get("org_city", "")

    payload = {
        "_meta": {
            "source": "NIH Reporter API v2",
            "source_url": f"{API_BASE}/projects/search",
            "search_terms": SEARCH_TERMS,
            "fiscal_years": FISCAL_YEARS,
            "record_count": len(unique_grants),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "grants": unique_grants,
    }

    key = raw_key("nih-reporter", "grants.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")
    else:
        log.info(f"[DRY RUN] Would write {len(unique_grants)} grants to s3://{BUCKET}/{key}")

    log.finish(records=len(unique_grants))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None, help="Partition date YYYY-MM-DD")
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
