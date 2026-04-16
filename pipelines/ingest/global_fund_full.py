"""
L0 — Global Fund grants + financial indicators ingest.
PRIMARY: Reads from foundation bucket (two locations — prefer health/ for full financials):

  GRANTS:
    raw/malaria-intelligence/global_fund_v4/gf_grants.json          (376KB, all components)
    raw/health/global-fund/grants/Grants.json.gz

  FINANCIALS (multi-part, gzipped):
    raw/health/global-fund/finance/AllFinancialIndicators.json.gz    (compressed summary)
    raw/health/global-fund/finance/AllFinancialIndicators_part001.json.gz  (full, ~120MB total)
    ... part002–part006

  PROGRAMMATIC:
    raw/health/global-fund/programs/AllProgrammaticIndicators.json.gz

FALLBACK: Live GF Data Service API v4 for any gaps.

Usage:
    python -m pipelines.ingest.global_fund_full [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"
GF_API = "https://data-service.theglobalfund.org/api/odata/v4"
SOURCE_CODE = "global_fund_v4"
DISEASE_CODE = "malaria"

GF_MALARIA_KEYWORDS = {"malaria", "m"}

_s3 = boto3.client("s3", region_name="us-east-1")


def read_gz_json(s3_key: str) -> list | dict | None:
    """Read gzipped JSON from foundation bucket."""
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=s3_key)
        body = resp["Body"].read()
        if s3_key.endswith(".gz"):
            body = gzip.decompress(body)
        return json.loads(body)
    except Exception:
        return None


def is_malaria_grant(grant: dict) -> bool:
    component = (grant.get("componentName") or grant.get("component") or "").lower()
    disease   = (grant.get("diseaseCode") or grant.get("disease") or "").lower()
    activity  = (grant.get("activityAreaName") or "").lower()
    return (
        "malaria" in component or
        disease in GF_MALARIA_KEYWORDS or
        "malaria" in activity
    )


def load_grants() -> list[dict]:
    """Load grants, preferring malaria-intelligence path then health/ path."""
    # Try malaria-intelligence path first (already filtered snapshot)
    data = read_gz_json("raw/malaria-intelligence/global_fund_v4/gf_grants.json")
    if data:
        grants = data if isinstance(data, list) else data.get("value", [])
        malaria = [g for g in grants if is_malaria_grant(g)]
        if malaria:
            return malaria
        # If not pre-filtered, return all (will filter below)
        if grants:
            return [g for g in grants if is_malaria_grant(g)] or grants[:500]

    # Try health/ path (compressed)
    data = read_gz_json("raw/health/global-fund/grants/Grants.json.gz")
    if data:
        grants = data if isinstance(data, list) else data.get("value", [])
        return [g for g in grants if is_malaria_grant(g)]

    return []


def load_financials() -> list[dict]:
    """
    Load AllFinancialIndicators. Try summary first (smaller), then multi-part.
    Returns list of financial indicator records.
    """
    # Try single compressed summary
    data = read_gz_json("raw/health/global-fund/finance/AllFinancialIndicators.json.gz")
    if data:
        records = data if isinstance(data, list) else data.get("value", [])
        if records:
            return records

    # Load multi-part files
    all_records: list[dict] = []
    for part in range(1, 7):
        key = f"raw/health/global-fund/finance/AllFinancialIndicators_part{part:03d}.json.gz"
        data = read_gz_json(key)
        if data is None:
            break
        records = data if isinstance(data, list) else data.get("value", [])
        all_records.extend(records)

    return all_records


def fetch_gf_grants_api() -> list[dict]:
    """Live API fallback for malaria grants."""
    try:
        resp = requests.get(
            f"{GF_API}/Grants",
            params={"$filter": "componentName eq 'Malaria'", "$top": 1000},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception:
        return []


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("global_fund_full", dry_run=dry_run)

    # ── Grants ─────────────────────────────────────────────────────────────
    with log.step("Load GF grants from foundation bucket"):
        grants = load_grants()
        log.info(f"  Foundation grants: {len(grants)}")

    if not grants:
        with log.step("Fetch grants from live API"):
            grants = fetch_gf_grants_api()
            log.info(f"  API grants: {len(grants)}")

    # ── Financials ─────────────────────────────────────────────────────────
    with log.step("Load GF AllFinancialIndicators from foundation bucket"):
        financials = load_financials()
        log.info(f"  Financial records: {len(financials)}")

    # ── Programmatic indicators ────────────────────────────────────────────
    with log.step("Load GF programmatic indicators"):
        prog_data = read_gz_json("raw/health/global-fund/programs/AllProgrammaticIndicators.json.gz")
        programmatic = []
        if prog_data:
            programmatic = prog_data if isinstance(prog_data, list) else prog_data.get("value", [])
            log.info(f"  Programmatic records: {len(programmatic)}")

    log.info(f"Totals — grants: {len(grants)}, financials: {len(financials)}, programmatic: {len(programmatic)}")

    # ── S3 raw ─────────────────────────────────────────────────────────────
    payload = {
        "_meta": {
            "source": SOURCE_CODE,
            "grants_count": len(grants),
            "financials_count": len(financials),
            "programmatic_count": len(programmatic),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "grants":       grants,
        "financials":   financials[:5000],   # cap payload size for S3
        "programmatic": programmatic[:5000],
    }
    key = raw_key("global-fund", "grants-financials.json", date=date)

    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert GF funding → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3

                # Build activityAreaId → (iso3, grant_code) lookup from grants
                # Grant code format: "{ISO3}-M-{id}" — first 3 chars are country code
                activity_to_iso3: dict[str, str] = {}
                for g in grants:
                    code = (g.get("code") or "").strip()
                    if code and "-" in code:
                        iso3_guess = code.split("-")[0].upper()
                        if len(iso3_guess) == 3:
                            act_id = g.get("activityAreaId") or g.get("id") or ""
                            if act_id:
                                activity_to_iso3[act_id] = iso3_guess

                # Grants → fact_funding (board-approved amounts)
                grant_rows = []
                for g in grants:
                    code = (g.get("code") or "").strip()
                    iso3 = code.split("-")[0].upper() if code and "-" in code else ""
                    if not iso3 or len(iso3) != 3:
                        continue
                    period = g.get("periodStartDate") or g.get("periodStart") or g.get("startDate") or ""
                    year = int(period[:4]) if period and len(period) >= 4 else None
                    if not year:
                        continue
                    amount = (g.get("totalBoardApprovedAmount_ReferenceRate") or
                              g.get("totalSignedAmount_ReferenceRate") or
                              g.get("approved_budget"))
                    if amount is None:
                        continue
                    grant_id = g.get("code") or g.get("id") or ""
                    grant_rows.append((
                        iso3, year, SOURCE_CODE, "global_fund", DISEASE_CODE,
                        float(amount), "approved", "malaria_grant", str(grant_id), "",
                    ))

                # Financial indicators → fact_funding (disbursements)
                # Join financials to grants via activityAreaId to get ISO3
                fin_rows = []
                for fin in financials:
                    act_id = fin.get("activityAreaId") or ""
                    iso3 = activity_to_iso3.get(act_id, "")
                    if not iso3 or len(iso3) != 3:
                        continue
                    period = fin.get("periodFrom") or fin.get("periodStartDate") or ""
                    year = int(str(period)[:4]) if period and len(str(period)) >= 4 else None
                    if not year:
                        continue
                    amount = fin.get("actualAmount") or fin.get("plannedAmount")
                    if amount is None:
                        continue
                    fin_rows.append((
                        iso3, year, SOURCE_CODE, "global_fund", DISEASE_CODE,
                        float(amount), "disbursed",
                        fin.get("indicatorName", "")[:200], "", "",
                    ))

                SQL = """
                    INSERT INTO malaria.fact_funding
                        (iso3, year, source_code, channel, disease, amount_usd, amount_type,
                         program, grant_id, implementing_partner)
                    VALUES %s ON CONFLICT DO NOTHING
                """
                if grant_rows:
                    grant_rows, g_skip = filter_valid_iso3(grant_rows, iso3_col=0)
                    if g_skip:
                        log.info(f"  Skipped {g_skip} grant rows (ISO3 not in dim_country)")
                    inserted = upsert_many(SQL, grant_rows)
                    log.info(f"  Upserted {inserted} grant rows")
                if fin_rows:
                    fin_rows, f_skip = filter_valid_iso3(fin_rows, iso3_col=0)
                    if f_skip:
                        log.info(f"  Skipped {f_skip} financial rows (ISO3 not in dim_country)")
                    inserted = upsert_many(SQL, fin_rows)
                    log.info(f"  Upserted {inserted} financial rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] grants={len(grants)} financials={len(financials)}")

    log.finish(records=len(grants) + len(financials))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
