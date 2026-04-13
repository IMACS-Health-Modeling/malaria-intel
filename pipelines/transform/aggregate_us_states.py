"""
L1 — Aggregate US state-level malaria activity
Merges NIH Reporter grants + USAspending geography + ClinicalTrials data
into a single per-state summary written to processed/us-states/.

Usage:
    python -m pipelines.transform.aggregate_us_states [--dry-run]
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.s3 import get_json, put_json, processed_key, latest_raw, BUCKET
from pipelines.utils.logger import PipelineLogger
from pipelines.utils.validators import validate_us_ecosystem

# State name → code lookup (for matching NIH institution states)
STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
CODE_TO_NAME = {v: k for k, v in STATE_CODES.items()}


def run(dry_run: bool = False) -> None:
    log = PipelineLogger("aggregate_us_states", dry_run=dry_run)

    # Per-state accumulators
    nih_usd: dict[str, float] = defaultdict(float)
    usaspend_usd: dict[str, float] = defaultdict(float)
    trial_counts: dict[str, int] = defaultdict(int)

    with log.step("Load NIH Reporter raw data"):
        try:
            nih_raw = get_json(latest_raw("nih-reporter", "grants.json"))
            for grant in nih_raw.get("grants", []):
                state = grant.get("_state", "").upper().strip()
                amount = grant.get("award_amount") or 0
                if state and len(state) == 2:
                    nih_usd[state] += float(amount)
            log.info(f"  NIH grants loaded: {len(nih_raw.get('grants', []))}")
        except FileNotFoundError:
            log.warn("  NIH raw data not found — skipping")

    with log.step("Load USAspending geography raw data"):
        try:
            usa_raw = get_json(latest_raw("usaspending", "geography.json"))
            for row in usa_raw.get("states", []):
                code = row.get("state_code", "").upper().strip()
                if code:
                    usaspend_usd[code] += float(row.get("total_usd", 0))
            log.info(f"  USAspending states loaded: {len(usa_raw.get('states', []))}")
        except FileNotFoundError:
            log.warn("  USAspending raw data not found — skipping")

    with log.step("Load ClinicalTrials raw data"):
        try:
            ct_raw = get_json(latest_raw("clinicaltrials", "malaria-trials.json"))
            for trial in ct_raw.get("trials", []):
                state = trial.get("sponsor_state", "").strip()
                # Convert full name to code if needed
                if state and len(state) > 2:
                    state = STATE_CODES.get(state, "")
                if state and len(state) == 2:
                    trial_counts[state.upper()] += 1
            log.info(f"  ClinicalTrials loaded: {len(ct_raw.get('trials', []))}")
        except FileNotFoundError:
            log.warn("  ClinicalTrials raw data not found — skipping")

    # Build state records
    all_codes = set(nih_usd) | set(usaspend_usd) | set(trial_counts)
    states = []
    for code in sorted(all_codes):
        if code not in CODE_TO_NAME and code != "DC":
            continue
        states.append({
            "code": code,
            "name": CODE_TO_NAME.get(code, "Washington DC"),
            "nih_grants_usd": round(nih_usd.get(code, 0)),
            "usaspending_usd": round(usaspend_usd.get(code, 0)),
            "clinical_trials": trial_counts.get(code, 0),
            "org_count": 0,          # Populated by implementing_partners step
            "countries_reached": 0,  # Populated by implementing_partners step
            "top_orgs": [],
        })

    # Sort by total activity
    states.sort(key=lambda s: s["nih_grants_usd"] + s["usaspending_usd"], reverse=True)

    total_nih = sum(s["nih_grants_usd"] for s in states)
    total_orgs = sum(s.get("org_count", 0) for s in states)
    total_trials = sum(s["clinical_trials"] for s in states)

    output = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": ["nih-reporter", "usaspending-geography", "clinicaltrials"],
            "record_count": len(states),
            "pipeline_version": "1.0.0",
        },
        "total_nih_usd": total_nih,
        "total_orgs": total_orgs,
        "total_trials": total_trials,
        "states": states,
    }

    validate_us_ecosystem(output)

    key = processed_key("us-states", "by-state", "summary.json")
    if not dry_run:
        with log.step("Write to processed layer"):
            put_json(key, output)
        log.info(f"s3://{BUCKET}/{key}")
    else:
        log.info(f"[DRY RUN] Would write {len(states)} states to s3://{BUCKET}/{key}")

    log.finish(records=len(states))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
