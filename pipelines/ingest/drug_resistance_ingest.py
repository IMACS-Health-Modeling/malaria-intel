"""
L0 — Malaria drug resistance ingest.

Sources:
  1. eLife 105544 kelch13 CSV (artemisinin partial resistance, global, 1980-2023)
     URL: https://cdn.elifesciences.org/articles/105544/elife-105544-fig1-data1-v1.csv
     112,934 sample-level rows. Columns: Sample, Country, Population, Year, Marker, Continent
     Marker = 'pfkelch13 mutation name' or '3D7_REF' (wildtype).
     Aggregated to: country × year × mutation → prevalence_pct + sample_size.
     Critical for: Africa R561H/A675V detections 2019-2023 (Rwanda, Uganda, Eritrea).

  2. MalariaGEN Pf8 (separate pipeline: malariagen_pf8.py)
     Handled by malariagen_pf8.py — this pipeline complements it with kelch13 specifics.

NOTE on foundation bucket:
  raw/malaria-intelligence/drug_resistance/elife_kelch13_artR_supp1.xlsx is a 7-row
  mutation CLASSIFICATION reference table, not sample data. Ignored here.
  raw/malaria-intelligence/drug_resistance/wmr2024_annex_2_drug_resistance.xlsx is
  ITN distribution data (Annex 2), not therapeutic efficacy data. Skipped.

Output:
  S3: raw/drug-resistance/dt=YYYY-MM-DD/elife-kelch13.json
  DB: malaria.fact_drug_resistance (data_source='elife_kelch13')

Usage:
    python -m pipelines.ingest.drug_resistance_ingest [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import csv
import io
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE = "elife_kelch13"

# eLife 105544 supplementary data — sample-level kelch13 genotypes
ELIFE_CSV_URL = "https://cdn.elifesciences.org/articles/105544/elife-105544-fig1-data1-v1.csv"

# Wildtype marker — not a resistance mutation
WILDTYPE_MARKER = "3D7_REF"

# WHO validated / candidate artemisinin partial resistance markers (pfkelch13)
# Source: WHO Technical Report on Artemisinin and ACT Resistance 2023
WHO_VALIDATED_MUTATIONS = {
    "F446I", "N458Y", "M476I", "Y493H", "R539T", "I543T", "P553L",
    "R561H", "P574L", "C580Y",
}
WHO_CANDIDATE_MUTATIONS = {
    "P441L", "G449A", "C469F", "C469Y", "A481V", "R515K", "P527H",
    "N537I", "N537D", "G538V", "V568G", "R622I", "A675V",
}

# Country name → ISO3 (covers all countries in the eLife dataset)
COUNTRY_ISO3: dict[str, str] = {
    "Papua New Guinea": "PNG", "Uganda": "UGA", "DRC": "COD",
    "Democratic Republic of the Congo": "COD", "Congo DRC": "COD",
    "Ghana": "GHA", "Kenya": "KEN", "Tanzania": "TZA", "Ethiopia": "ETH",
    "Rwanda": "RWA", "Malawi": "MWI", "Mozambique": "MOZ", "Zambia": "ZMB",
    "Mali": "MLI", "Burkina Faso": "BFA", "Senegal": "SEN", "Niger": "NER",
    "Guinea": "GIN", "Cameroon": "CMR", "Nigeria": "NGA", "Benin": "BEN",
    "Togo": "TGO", "Gambia": "GMB", "The Gambia": "GMB", "Sierra Leone": "SLE",
    "Liberia": "LBR", "Ivory Coast": "CIV", "Cote d'Ivoire": "CIV",
    "Madagascar": "MDG", "Zimbabwe": "ZWE", "Angola": "AGO",
    "South Sudan": "SSD", "Sudan": "SDN", "Eritrea": "ERI",
    "Somalia": "SOM", "Djibouti": "DJI", "Comoros": "COM",
    "Central African Republic": "CAF", "Chad": "TCD", "Gabon": "GAB",
    "Equatorial Guinea": "GNQ", "Sao Tome": "STP", "Congo": "COG",
    "Burundi": "BDI", "Namibia": "NAM", "Botswana": "BWA",
    "Cambodia": "KHM", "Myanmar": "MMR", "Thailand": "THA",
    "Vietnam": "VNM", "Laos": "LAO", "Indonesia": "IDN", "India": "IND",
    "Bangladesh": "BGD", "Pakistan": "PAK", "Philippines": "PHL",
    "China": "CHN", "Colombia": "COL", "Peru": "PER", "Brazil": "BRA",
    "Haiti": "HTI", "Guyana": "GUY", "Venezuela": "VEN",
    "Solomon Islands": "SLB", "Vanuatu": "VUT",
}


def _severity(mutation: str) -> str:
    if mutation in WHO_VALIDATED_MUTATIONS:
        return "full"
    if mutation in WHO_CANDIDATE_MUTATIONS:
        return "partial"
    return "low"


def fetch_and_aggregate(log) -> list[dict]:
    """
    Download eLife 105544 fig1-data1 CSV (112,934 sample rows).
    Aggregate to country × year × mutation → prevalence_pct + sample_size.

    Algorithm:
      For each (country, year): total = all samples (including wildtype)
      For each (country, year, mutation != 3D7_REF): mutant_count / total = prevalence
    """
    log.info(f"  Fetching {ELIFE_CSV_URL}")
    resp = requests.get(ELIFE_CSV_URL, timeout=120)
    resp.raise_for_status()
    log.info(f"  Downloaded {len(resp.content):,} bytes, {resp.text.count(chr(10)):,} lines")

    reader = csv.DictReader(io.StringIO(resp.text))

    # (country_name, year) → total sample count
    totals: dict[tuple[str, int], int] = defaultdict(int)
    # (country_name, year, mutation) → mutant count
    mutants: dict[tuple[str, int, str], int] = defaultdict(int)

    skipped = 0
    for row in reader:
        country = str(row.get("Country") or "").strip()
        year_raw = str(row.get("Year") or "").strip()
        marker   = str(row.get("Marker") or "").strip()

        if not country or not year_raw or not marker:
            skipped += 1
            continue
        try:
            year = int(float(year_raw))
        except (ValueError, TypeError):
            skipped += 1
            continue
        if year < 1984 or year > 2030:
            skipped += 1
            continue

        totals[(country, year)] += 1
        if marker != WILDTYPE_MARKER:
            mutants[(country, year, marker)] += 1

    log.info(f"  Skipped {skipped} malformed rows")
    log.info(f"  Country-year combinations: {len(totals)}")

    # Build aggregated rows
    rows_out: list[dict] = []
    for (country, year, mutation), count in mutants.items():
        total = totals.get((country, year), 0)
        if total == 0:
            continue
        iso3 = COUNTRY_ISO3.get(country)
        if not iso3:
            continue
        prevalence = count / total
        rows_out.append({
            "iso3":              iso3,
            "year":              year,
            "drug":              "artemisinin",
            "resistance_marker": "pfkelch13",
            "mutation":          mutation[:20],
            "prevalence_pct":    round(prevalence, 5),
            "sample_size":       total,
            "severity":          _severity(mutation),
        })

    return rows_out


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("drug_resistance_ingest", dry_run=dry_run)

    with log.step("Fetch + aggregate eLife 105544 kelch13 data"):
        rows = fetch_and_aggregate(log)

    if not rows:
        log.warn("No rows parsed")
        log.finish(records=0)
        return

    log.info(f"Total aggregated rows: {len(rows)}")

    # Summary stats
    countries = len({r["iso3"] for r in rows})
    years     = sorted({r["year"] for r in rows})
    mutations = len({r["mutation"] for r in rows})
    validated = [r for r in rows if r["mutation"] in WHO_VALIDATED_MUTATIONS]
    log.info(f"  Countries: {countries}, Years: {min(years)}-{max(years)}, Mutations: {mutations}")
    log.info(f"  WHO-validated mutation rows: {len(validated)}")

    # Africa 2019+ R561H specifically (key narrative data point)
    r561h_africa = [
        r for r in rows
        if r["mutation"] == "R561H" and r["year"] >= 2019
        and r["iso3"] in {"RWA", "UGA", "ERI", "ETH", "TZA", "KEN"}
    ]
    if r561h_africa:
        log.info(f"  R561H Africa 2019+: {len(r561h_africa)} rows")
        for r in sorted(r561h_africa, key=lambda x: -x["prevalence_pct"])[:5]:
            log.info(f"    {r['iso3']} {r['year']}: {r['prevalence_pct']*100:.1f}% ({r['sample_size']} samples)")

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "upstream_url": ELIFE_CSV_URL,
            "record_count": len(rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": rows,
    }
    key = raw_key("drug-resistance", "elife-kelch13.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_drug_resistance"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_drug_resistance
                        (iso3, year, drug, resistance_marker, mutation,
                         prevalence_pct, sample_size, data_source, severity)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], r["drug"], r["resistance_marker"],
                     r["mutation"], r["prevalence_pct"], r["sample_size"],
                     SOURCE_CODE, r["severity"])
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
        log.info(f"[DRY RUN] {len(rows)} rows ready")
        for r in rows[:3]:
            log.info(f"  {r['iso3']} {r['year']} {r['mutation']}: {r['prevalence_pct']*100:.2f}% (n={r['sample_size']})")

    log.finish(records=len(rows), s3_keys=[key] if not dry_run else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest eLife kelch13 artemisinin resistance data")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
