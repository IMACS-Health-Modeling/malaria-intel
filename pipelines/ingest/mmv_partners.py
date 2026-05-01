"""
L0 — MMV US Active Partners ingest.

Source: MMV internal export — "Active partners in the United States 2025-26_for sharing.xlsx"
        (48 partners: Academia, CRO, NGO, Pharma, Government, Service Provider)

Output:
  S3: raw/mmv-partners/dt=YYYY-MM-DD/mmv-us-partners.json
  DB: malaria.dim_partner (upsert on name + active_year)

Usage:
    python -m pipelines.ingest.mmv_partners [--dry-run] [--date YYYY-MM-DD]
    python -m pipelines.ingest.mmv_partners --file /path/to/partners.xlsx
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import openpyxl
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

# Default file location (relative to repo root)
_DEFAULT_XLSX = Path(__file__).parent.parent.parent / "Active partners in the United States 2025-26_for sharing.xlsx"

ACTIVE_YEAR = 2026  # "2025-26" cycle → report year 2026

# Entity type normalisation
_ENTITY_MAP = {
    "academia":                              "academia",
    "contract research organization - cro":  "cro",
    "non governmental organization - ngo":   "ngo",
    "pharma":                                "pharma",
    "governmental agency or ministry":       "government",
    "service provider":                      "service_provider",
    # fallbacks
    "academic development organization - ado": "academia",
    "international organization":            "ngo",
    "other":                                 "other",
}

# US state name → 2-letter code (covers states that appear in the dataset)
_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
# Reverse map: "CA" → "CA" (pass-through for already-abbreviated values)
_STATE_CODES = {v: v for v in _STATE_ABBREV.values()}


def _normalize_entity(raw: str) -> str:
    return _ENTITY_MAP.get(raw.strip().lower(), "other")


def _parse_city_state(raw: str) -> tuple[str | None, str | None]:
    """
    Parse 'City, ST' or 'City, State' → (city, state_code).
    Handles multi-city entries like 'Danbury, CT and Durham, NC' → first pair.
    """
    if not raw:
        return None, None
    raw = raw.strip()
    # Take only the first location if multiple listed
    if " and " in raw:
        raw = raw.split(" and ")[0].strip()
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 2:
        return raw, None
    city = parts[0]
    state_raw = parts[-1].strip()
    # Already an abbreviation?
    code = _STATE_CODES.get(state_raw.upper())
    if code:
        return city, code
    # Full name?
    code = _STATE_ABBREV.get(state_raw)
    if code:
        return city, code
    # Try stripping trailing punctuation / spaces
    state_raw2 = state_raw.rstrip(".")
    code = _STATE_CODES.get(state_raw2.upper()) or _STATE_ABBREV.get(state_raw2)
    return city, code


def load_xlsx(path: Path) -> list[dict]:
    """Parse the partners Excel → list of clean dicts."""
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, entity_raw, city_state_raw, notes, country, region = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )
        # Skip blank rows and the filter-metadata footer row
        if not name or not isinstance(name, str) or name.startswith("Applied filters"):
            continue
        city, state_code = _parse_city_state(city_state_raw or "")
        rows.append({
            "name":            name.strip(),
            "entity_type":     _normalize_entity(entity_raw or ""),
            "entity_type_raw": (entity_raw or "").strip(),
            "city":            city,
            "state_code":      state_code,
            "country_iso3":    "USA",
            "notes":           (notes or "").strip() or None,
            "active_year":     ACTIVE_YEAR,
        })
    return rows


def run(dry_run: bool = False, date: str | None = None, xlsx_path: Path | None = None) -> None:
    log = PipelineLogger("mmv_partners", dry_run=dry_run)
    xlsx = xlsx_path or _DEFAULT_XLSX

    with log.step("Load partners Excel"):
        if not xlsx.exists():
            log.warn(f"  File not found: {xlsx}")
            log.finish(records=0)
            return
        rows = load_xlsx(xlsx)
        log.info(f"  Loaded {len(rows)} partner rows from {xlsx.name}")

        # Summary by entity type
        from collections import Counter
        counts = Counter(r["entity_type"] for r in rows)
        for etype, n in sorted(counts.items(), key=lambda x: -x[1]):
            log.info(f"    {etype}: {n}")

        states = sorted({r["state_code"] for r in rows if r["state_code"]})
        log.info(f"  States represented: {', '.join(states)}")

    if not rows:
        log.warn("  No data parsed")
        log.finish(records=0)
        return

    payload = {
        "_meta": {
            "source":       "mmv_us_partners",
            "active_year":  ACTIVE_YEAR,
            "record_count": len(rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": rows,
    }
    key = raw_key("mmv-partners", "mmv-us-partners.json", date=date)

    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL dim_partner"):
            try:
                from pipelines.utils.db import upsert_many
                SQL = """
                    INSERT INTO malaria.dim_partner
                        (name, entity_type, entity_type_raw, city, state_code,
                         country_iso3, notes, active_year, data_source)
                    VALUES %s
                    ON CONFLICT (name, active_year) DO UPDATE SET
                        entity_type     = EXCLUDED.entity_type,
                        entity_type_raw = EXCLUDED.entity_type_raw,
                        city            = EXCLUDED.city,
                        state_code      = EXCLUDED.state_code,
                        notes           = EXCLUDED.notes,
                        ingested_at     = NOW()
                """
                db_rows = [
                    (r["name"], r["entity_type"], r["entity_type_raw"],
                     r["city"], r["state_code"], r["country_iso3"],
                     r["notes"], r["active_year"], "mmv_us_partners")
                    for r in rows
                ]
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} partner rows")
            except Exception as e:
                log.warn(f"  DB upsert failed: {e}")
    else:
        log.info(f"[DRY RUN] {len(rows)} partner rows ready")
        for r in rows[:5]:
            log.info(f"  {r['name']} | {r['entity_type']} | {r['city']}, {r['state_code']} | {(r['notes'] or '')[:60]}")

    log.finish(records=len(rows), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest MMV US active partners")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--file", default=None, help="Path to the partners .xlsx file")
    args = parser.parse_args()
    run(
        dry_run=args.dry_run,
        date=args.date,
        xlsx_path=Path(args.file) if args.file else None,
    )
