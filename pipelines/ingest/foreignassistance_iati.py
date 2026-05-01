"""
L0 — ForeignAssistance.gov IATI multi-donor malaria ingest.

Source: ForeignAssistance.gov bulk IATI transactions CSV (EADS S3 bucket)
URL:    https://eads-data.s3.us-east-1.amazonaws.com/explorer/landscape_transactions_data.csv

Streams the 282MB IATI transactions CSV, filters for malaria-specific
DAC purpose codes (12262 = Malaria control, 12250 = Infectious disease control),
and upserts non-zero disbursements to malaria.fact_funding.

Critical exclusion: org_id == "47045" (Global Fund) rows are skipped — we
already have that data at better granularity from global_fund_v4.

Donors ingested (sample, from 2024 run):
  UNICEF $4.1B, World Bank $4.1B, WHO $2.2B, Gates Foundation $1.6B,
  UK FCDO $636M, Canada $394M, AFD (France) $371M, German BMZ $284M,
  U.S. Government $246M

Output:
  S3: raw/foreignassistance-iati/dt=YYYY-MM-DD/fa-malaria-disbursements.json
  DB: malaria.fact_funding
    source_code  = 'foreignassistance_iati'
    channel      = normalised from organization_name (see _normalise_channel)
    amount_type  = 'disbursed'
    disease      = 'malaria'

Usage:
    python -m pipelines.ingest.foreignassistance_iati [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import csv
import io
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE  = "foreignassistance_iati"
CSV_URL      = "https://eads-data.s3.us-east-1.amazonaws.com/explorer/landscape_transactions_data.csv"

# DAC purpose codes for malaria
MALARIA_PURPOSES = {"12262", "12250"}

# Global Fund org_id — exclude to prevent double-counting with global_fund_v4
GLOBAL_FUND_ORG_ID = "47045"


def _normalise_channel(org_name: str) -> str:
    """Map organization_name to a standardised channel slug."""
    n = org_name.lower()
    if "u.s." in n or "us government" in n or "united states" in n:
        return "pmi_usaid"
    if "world bank" in n:
        return "world_bank"
    if "united kingdom" in n or "fcdo" in n or "dfid" in n:
        return "uk_fcdo"
    if "germany" in n or "bmz" in n or "bundesministerium" in n or "giz" in n or "kfw" in n:
        return "germany_bmz"
    if "france" in n or "afd" in n or "agence française" in n or "agence francaise" in n:
        return "france_afd"
    if "australia" in n or "dfat" in n:
        return "australia_dfat"
    if "canada" in n or "dfatd" in n or "global affairs canada" in n:
        return "canada_gac"
    if "unicef" in n or "united nations children" in n:
        return "unicef"
    if "world health organization" in n or "who" == n.strip():
        return "who"
    if "gates" in n or "bmgf" in n:
        return "gates_foundation"
    if "netherlands" in n:
        return "netherlands"
    if "switzerland" in n or "swiss" in n or "sdc" in n:
        return "switzerland_sdc"
    if "japan" in n or "jica" in n:
        return "japan_jica"
    if "sweden" in n or "sida" in n:
        return "sweden_sida"
    if "norway" in n or "norad" in n:
        return "norway_norad"
    # Fallback: slug from org name (max 50 chars, alphanumeric + underscore)
    slug = org_name[:50].lower().replace(" ", "_")
    slug = "".join(c for c in slug if c.isalnum() or c == "_")
    return slug or "unknown"


def stream_and_filter(log) -> list[dict]:
    """
    Download the 282MB IATI transactions CSV to /tmp, then filter for
    malaria disbursements and return clean rows.
    """
    import tempfile, os

    rows = []
    skipped_gf = 0
    skipped_zero = 0
    skipped_type = 0
    skipped_iso3 = 0
    total = 0

    # Download to a temp file (avoids socket-close issues on large streams)
    tmp_path = Path(tempfile.gettempdir()) / "fa_iati_transactions.csv"
    log.info(f"  Downloading {CSV_URL} → {tmp_path}")
    resp = requests.get(CSV_URL, stream=True, timeout=600)
    resp.raise_for_status()
    downloaded = 0
    with open(tmp_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            fh.write(chunk)
            downloaded += len(chunk)
    log.info(f"  Downloaded {downloaded / 1e6:.1f} MB")

    reader = csv.DictReader(open(tmp_path, encoding="utf-8", errors="replace"))

    for row in reader:
        total += 1
        if total % 250000 == 0:
            log.info(f"  ... scanned {total:,} rows, {len(rows):,} matched so far")

        # Purpose filter
        if row.get("purpose") not in MALARIA_PURPOSES:
            continue

        # Transaction type filter
        if row.get("transaction_type") != "Disbursement":
            skipped_type += 1
            continue

        # Exclude Global Fund
        if str(row.get("org_id", "")).strip() == GLOBAL_FUND_ORG_ID:
            skipped_gf += 1
            continue

        # Amount filter
        try:
            amount = float(row.get("transaction_amount") or 0)
        except (ValueError, TypeError):
            amount = 0.0
        if amount <= 0:
            skipped_zero += 1
            continue

        # ISO3 validation (basic)
        iso3 = str(row.get("country") or "").strip().upper()
        if len(iso3) != 3:
            skipped_iso3 += 1
            continue

        try:
            year = int(row.get("transaction_year") or 0)
        except (ValueError, TypeError):
            continue
        if year < 2000 or year > 2030:
            continue

        org_name = str(row.get("organization_name") or "").strip()
        purpose_name = str(row.get("purpose_name") or "").strip()

        rows.append({
            "iso3":                 iso3,
            "year":                 year,
            "source_code":          SOURCE_CODE,
            "channel":              _normalise_channel(org_name),
            "disease":              "malaria",
            "amount_usd":           amount,
            "amount_type":          "disbursed",
            "program":              purpose_name[:100] if purpose_name else None,
            "implementing_partner": org_name[:100] if org_name else None,
        })

    log.info(f"  Total rows scanned: {total:,}")
    log.info(f"  Matched (malaria disbursements, amount>0): {len(rows):,}")
    log.info(f"  Skipped (non-Disbursement): {skipped_type:,}")
    log.info(f"  Skipped (Global Fund): {skipped_gf:,}")
    log.info(f"  Skipped (zero amount): {skipped_zero:,}")
    return rows


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger(SOURCE_CODE, dry_run=dry_run)

    # ── Seed dim_source ────────────────────────────────────────────────── #
    if not dry_run:
        with log.step("Seed dim_source"):
            try:
                from pipelines.utils.db import execute
                execute("""
                    INSERT INTO malaria.dim_source
                        (code, name, url, data_type, refresh_cadence)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (code) DO NOTHING
                """, (
                    SOURCE_CODE,
                    "ForeignAssistance.gov IATI Multi-Donor Data",
                    "https://foreignassistance.gov/data",
                    "download",
                    "annual",
                ))
                log.info("  dim_source row ensured")
            except Exception as e:
                log.warn(f"  dim_source seed failed: {e}")

    # ── Fetch & filter ────────────────────────────────────────────────── #
    with log.step("Stream & filter IATI transactions CSV"):
        try:
            rows = stream_and_filter(log)
        except Exception as e:
            log.warn(f"  CSV fetch failed: {e}")
            log.finish(records=0)
            return

    if not rows:
        log.warn("  No rows matched — check CSV URL or purpose codes")
        log.finish(records=0)
        return

    # ── Summary ──────────────────────────────────────────────────────── #
    with log.step("Summarise"):
        by_channel = Counter(r["channel"] for r in rows)
        by_year = defaultdict(float)
        for r in rows:
            by_year[r["year"]] += r["amount_usd"]

        log.info(f"  Countries: {len({r['iso3'] for r in rows})}")
        log.info(f"  Years: {min(by_year)}-{max(by_year)}")
        log.info(f"  Total USD: ${sum(r['amount_usd'] for r in rows)/1e9:.2f}B")
        log.info("  Top channels by row count:")
        for ch, n in sorted(by_channel.items(), key=lambda x: -x[1])[:10]:
            total_usd = sum(r["amount_usd"] for r in rows if r["channel"] == ch)
            log.info(f"    {ch:30} {n:5d} rows  ${total_usd/1e6:.0f}M")

    # ── S3 upload ─────────────────────────────────────────────────────── #
    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "csv_url":      CSV_URL,
            "purposes":     sorted(MALARIA_PURPOSES),
            "record_count": len(rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": rows,
    }
    key = raw_key("foreignassistance-iati", "fa-malaria-disbursements.json", date=date)

    if not dry_run:
        with log.step("Upload filtered rows to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        # ── DB upsert ────────────────────────────────────────────────── #
        with log.step("Upsert → PostgreSQL fact_funding"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_funding
                        (iso3, year, source_code, channel, disease,
                         amount_usd, amount_type, program, implementing_partner)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], r["source_code"], r["channel"],
                     r["disease"], r["amount_usd"], r["amount_type"],
                     r["program"], r["implementing_partner"])
                    for r in rows
                ]
                db_rows, skipped_iso3 = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped_iso3:
                    log.info(f"  Skipped {skipped_iso3} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert failed: {e}")
    else:
        log.info(f"[DRY RUN] {len(rows)} rows ready (not written)")
        for r in rows[:5]:
            log.info(
                f"  {r['iso3']} {r['year']} | {r['channel']:25} | "
                f"${r['amount_usd']:>12,.0f} | {(r['program'] or '')}"
            )

    log.finish(records=len(rows), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest ForeignAssistance.gov IATI malaria disbursements"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
