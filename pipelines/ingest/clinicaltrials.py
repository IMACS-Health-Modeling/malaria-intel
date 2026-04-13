"""
L0 — ClinicalTrials.gov ingest
Fetches malaria clinical trials with US sponsors/lead sponsors.
Uses the ClinicalTrials.gov API v2.

Usage:
    python -m pipelines.ingest.clinicaltrials [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

API_BASE = "https://clinicaltrials.gov/api/v2"


def fetch_trials(page_token: str | None = None) -> dict:
    params = {
        "query.cond": "malaria",
        "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED",
        "filter.geo": "distance(37.0902,-95.7129,3000mi)",  # US sponsor location heuristic
        "pageSize": 1000,
        "fields": "NCTId,BriefTitle,OverallStatus,LeadSponsorName,LeadSponsorClass,"
                  "LocationFacility,LocationCity,LocationState,LocationCountry,"
                  "StartDate,CompletionDate,EnrollmentCount,Phase",
    }
    if page_token:
        params["pageToken"] = page_token

    resp = requests.get(f"{API_BASE}/studies", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("clinicaltrials", dry_run=dry_run)
    all_trials: list[dict] = []

    with log.step("Fetch ClinicalTrials.gov malaria studies"):
        page_token = None
        page = 0
        while True:
            try:
                result = fetch_trials(page_token)
            except Exception as e:
                log.warn(f"  Page {page} failed: {e}")
                break

            studies = result.get("studies", [])
            all_trials.extend(studies)
            page_token = result.get("nextPageToken")
            log.info(f"  Page {page}: fetched {len(studies)} trials (total so far: {len(all_trials)})")
            page += 1

            if not page_token:
                break

    # Filter to US-sponsored: LeadSponsorClass includes INDUSTRY, NIH, FED, OTHER
    # and extract sponsor state from location data
    us_trials = []
    for t in all_trials:
        proto = t.get("protocolSection", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        locations = proto.get("contactsLocationsModule", {}).get("locations", [])

        # Check if any location is in the US
        us_locations = [l for l in locations if l.get("country") == "United States"]
        if not us_locations and sponsor.get("class") not in ("NIH", "FED", "INDUSTRY"):
            continue

        # Extract state from first US location
        sponsor_state = ""
        if us_locations:
            sponsor_state = us_locations[0].get("state", "")

        us_trials.append({
            "nct_id": proto.get("identificationModule", {}).get("nctId", ""),
            "title": proto.get("identificationModule", {}).get("briefTitle", ""),
            "status": proto.get("statusModule", {}).get("overallStatus", ""),
            "sponsor_name": sponsor.get("name", ""),
            "sponsor_class": sponsor.get("class", ""),
            "sponsor_state": sponsor_state,
            "phase": proto.get("designModule", {}).get("phases", []),
            "start_date": proto.get("statusModule", {}).get("startDateStruct", {}).get("date", ""),
            "completion_date": proto.get("statusModule", {}).get("completionDateStruct", {}).get("date", ""),
            "enrollment": proto.get("designModule", {}).get("enrollmentInfo", {}).get("count", 0),
        })

    log.info(f"US-sponsored malaria trials: {len(us_trials)} / {len(all_trials)} total")

    payload = {
        "_meta": {
            "source": "ClinicalTrials.gov API v2",
            "condition": "malaria",
            "record_count": len(us_trials),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "trials": us_trials,
    }

    key = raw_key("clinicaltrials", "malaria-trials.json", date=date)
    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
    else:
        log.info(f"[DRY RUN] Would write {len(us_trials)} trials to s3://{BUCKET}/{key}")

    log.finish(records=len(us_trials))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
