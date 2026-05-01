"""
L0 — Global Fund intervention-level expenditure ingest.

Source: Global Fund Data Service OData v4.2
URL:    https://fetch.theglobalfund.org/v4.2/odata/allFinancialIndicators

Fetches malaria programme expenditure broken down by intervention category
(bed nets, IRS, case management, SMC, etc.) per country per year.

Why this differs from global_fund_full.py:
  global_fund_full.py loads grant-level DISBURSEMENTS (what GF transferred to
  Principal Recipients at the component level). This pipeline loads EXPENDITURES
  at the intervention level — how those funds were actually spent, broken down
  by vector control / case management / prevention sub-categories.
  Intervention data available from 2017 grant cycle onward only.

Output:
  S3: raw/global-fund-interventions/dt=YYYY-MM-DD/gf-interventions.json
  DB: malaria.fact_funding
    source_code  = 'global_fund_v4'
    channel      = 'global_fund'
    amount_type  = 'spent'
    program      = intervention name (e.g. 'ITN - Mass campaign')

Usage:
    python -m pipelines.ingest.global_fund_interventions [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE   = "global_fund_v4"
GF_ODATA_BASE = "https://fetch.theglobalfund.org/v4.2/odata"
INDICATOR_NAME = "Expenditure: Module-Intervention - Reference Rate"

# Intervention parent modules that are malaria-relevant
MALARIA_MODULES = {
    "vector control",
    "case management",
    "specific prevention interventions (spi)",
    "malaria",
    "health management information systems and m&e",
    "human resources for health, including community health workers",
}

# Short labels for program column (max meaningful truncation)
_PROGRAM_ABBREV = {
    "Long-lasting insecticidal nets (LLIN) - Mass campaign - Universal":              "LLIN - mass campaign universal",
    "Long-lasting insecticidal nets (LLIN) - Mass campaign":                          "LLIN - mass campaign",
    "Long-lasting insecticidal nets (LLIN) - Continuous distribution - ANC":          "LLIN - continuous ANC",
    "Long-lasting insecticidal nets (LLIN) - Continuous distribution - EPI":          "LLIN - continuous EPI",
    "Long-lasting insecticidal nets (LLIN) - Continuous distribution - Community":    "LLIN - continuous community",
    "Insecticide treated nets (ITNs) - Mass campaign: universal":                     "ITN - mass campaign universal",
    "Insecticide treated nets (ITNs) - Continuous distribution: ANC":                 "ITN - continuous ANC",
    "Insecticide treated nets (ITNs) - Continuous distribution: EPI":                 "ITN - continuous EPI",
    "Indoor residual spraying (IRS)":                                                 "IRS",
    "Seasonal malaria chemoprevention":                                               "SMC",
    "Perennial malaria chemoprevention (PMC)":                                        "PMC",
    "Post discharge malaria chemoprevention (PDMC)":                                  "PDMC",
    "Severe malaria":                                                                 "Case mgmt - severe malaria",
    "Facility-based treatment":                                                       "Case mgmt - facility treatment",
    "Malaria":                                                                        "malaria_general",
}


def _abbrev(name: str) -> str:
    """Shorten intervention name to fit in program column."""
    return _PROGRAM_ABBREV.get(name, name[:100])


def fetch_interventions(page_size: int = 5000) -> list[dict]:
    """
    Fetch GF expenditure at intervention level for all countries, all pages.

    Uses OData $apply with groupby to aggregate actualAmount by
    (country, year, intervention, module). Paginates with $skip until
    the API returns fewer records than page_size.
    """
    apply_clause = (
        f"filter("
        f"indicatorName in ('{INDICATOR_NAME}') "
        f"and isLatestReported eq true"
        f")/"
        f"groupby("
        f"(implementationPeriod/periodFrom,"
        f"activityArea/name,"
        f"activityArea/parent/name,"
        f"implementationPeriod/grant/geography/code,"
        f"implementationPeriod/grant/geography/name),"
        f"aggregate(actualAmount with sum as actual)"
        f")"
    )

    url = f"{GF_ODATA_BASE}/allFinancialIndicators"
    all_records: list[dict] = []
    skip = 0

    while True:
        params = {
            "$apply":   apply_clause,
            "$orderby": "actual desc",
            "$top":     page_size,
            "$skip":    skip,
        }
        try:
            resp = requests.get(url, params=params, timeout=120)
            resp.raise_for_status()
            page = resp.json().get("value", [])
        except Exception:
            break

        all_records.extend(page)
        if len(page) < page_size:
            break   # last page
        skip += page_size

    return all_records


def parse_records(raw_records: list[dict]) -> list[dict]:
    """
    Extract flat rows from nested OData groupby response.
    Filter to malaria-relevant intervention modules only.
    """
    rows = []
    for r in raw_records:
        ip   = r.get("implementationPeriod") or {}
        grant = ip.get("grant") or {}
        geo  = grant.get("geography") or {}
        area = r.get("activityArea") or {}
        parent = area.get("parent") or {}

        iso3     = str(geo.get("code") or "").strip().upper()
        year_raw = ip.get("periodFrom")
        interv   = str(area.get("name") or "").strip()
        module   = str(parent.get("name") or "").strip()
        amount   = r.get("actual")

        if len(iso3) != 3:
            continue
        try:
            year = int(str(year_raw)[:4]) if year_raw else None
        except (ValueError, TypeError):
            year = None
        if not year or year < 2015 or year > 2030:
            continue
        try:
            amount_f = float(amount or 0)
        except (ValueError, TypeError):
            amount_f = 0.0
        if amount_f <= 0:
            continue

        # Filter to malaria-relevant modules
        if module.lower() not in MALARIA_MODULES and "malaria" not in module.lower():
            continue

        rows.append({
            "iso3":         iso3,
            "year":         year,
            "intervention": interv,
            "module":       module,
            "amount_usd":   amount_f,
        })
    return rows


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("global_fund_interventions", dry_run=dry_run)

    with log.step("Fetch GF intervention expenditures (OData v4.2)"):
        raw_records = fetch_interventions()
        log.info(f"  Raw records from API: {len(raw_records)}")

    if not raw_records:
        log.warn("  No data returned — API may be unavailable")
        log.finish(records=0)
        return

    with log.step("Parse and filter to malaria interventions"):
        rows = parse_records(raw_records)
        log.info(f"  Malaria intervention rows: {len(rows)}")

        # Log top interventions by total spend
        from collections import defaultdict
        interv_totals: dict[str, float] = defaultdict(float)
        for r in rows:
            interv_totals[r["intervention"]] += r["amount_usd"]
        top5 = sorted(interv_totals.items(), key=lambda x: -x[1])[:5]
        for interv, total in top5:
            log.info(f"  Top: {interv[:60]} — ${total:,.0f}")

        countries = len({r["iso3"] for r in rows})
        years     = sorted({r["year"] for r in rows})
        log.info(f"  Countries: {countries}, Years: {min(years) if years else '?'}-{max(years) if years else '?'}")

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "indicator":    INDICATOR_NAME,
            "record_count": len(rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": rows,
    }
    key = raw_key("global-fund-interventions", "gf-interventions.json", date=date)

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
                         amount_usd, amount_type, program, raw_s3_key)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                # Note: fact_funding doesn't have raw_s3_key in schema — use grant_id col instead
                # Storing intervention module in implementing_partner for queryability
                SQL = """
                    INSERT INTO malaria.fact_funding
                        (iso3, year, source_code, channel, disease,
                         amount_usd, amount_type, program, implementing_partner)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], SOURCE_CODE, "global_fund", "malaria",
                     r["amount_usd"], "spent",
                     _abbrev(r["intervention"]),   # program = intervention name
                     r["module"][:100])            # implementing_partner = module/category
                    for r in rows
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert failed: {e}")
    else:
        log.info(f"[DRY RUN] {len(rows)} intervention rows ready")
        for r in rows[:3]:
            log.info(f"  Sample: {r['iso3']} {r['year']} | {r['intervention'][:50]} | ${r['amount_usd']:,.0f}")

    log.finish(records=len(rows), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Global Fund intervention-level expenditures")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
