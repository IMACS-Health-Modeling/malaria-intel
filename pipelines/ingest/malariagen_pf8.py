"""
L0 — MalariaGEN Pf8 genomic drug resistance ingest.

Source: MalariaGEN Plasmodium falciparum Community Project, Release 8
URL:    https://pf8-release.cog.sanger.ac.uk/
Files:
  Pf8_samples.tsv           — per-sample metadata: country, year, site, drug resistance calls
  Pf8_drug_resistance_markers.tsv — per-sample validated resistance status

Output:
  S3: raw/malariagen-pf8/dt=YYYY-MM-DD/pf8-samples.tsv.gz  (raw download)
      raw/malariagen-pf8/dt=YYYY-MM-DD/pf8-resistance.json (aggregated country-year-mutation)
  DB: malaria.fact_drug_resistance  (data_source='malariagen_pf8')

Aggregation:
  Groups sample-level data → country × year × mutation prevalence %
  Only validated/validated_by_who_protocol mutations retained.

Usage:
    python -m pipelines.ingest.malariagen_pf8 [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import gzip
import io
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET, s3 as s3_client
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE  = "malariagen_pf8"
DISEASE_CODE = "malaria"
BASE_URL     = "https://pf8-release.cog.sanger.ac.uk"

# Correct Pf8 release file paths (from README)
PF8_SAMPLES_URL = f"{BASE_URL}/metadata/Pf8_samples.txt"   # country, year, lat/lng
PF8_DR_URL      = f"{BASE_URL}/Pf8_inferred_resistance_status_classification.tsv"
PF8_GENO_URL    = f"{BASE_URL}/Pf8_drug_resistance_marker_genotypes.tsv"

# Drug columns in Pf8_inferred_resistance_status_classification.tsv
# Values: "Resistant", "Sensitive", "Undetermined"
RESISTANCE_DRUGS = {
    "Chloroquine":    {"drug": "chloroquine",  "resistance_marker": "pfcrt",     "mutation": "K76T"},
    "Artemisinin":    {"drug": "artemisinin",  "resistance_marker": "pfkelch13", "mutation": "C580Y"},
    "Piperaquine":    {"drug": "piperaquine",  "resistance_marker": "pfpm23",    "mutation": "CNV"},
    "Mefloquine":     {"drug": "mefloquine",   "resistance_marker": "pfmdr1",    "mutation": "N86Y"},
    "Pyrimethamine":  {"drug": "sp",           "resistance_marker": "pfdhfr",    "mutation": "N51I"},
    "Sulfadoxine":    {"drug": "sp",           "resistance_marker": "pfdhps",    "mutation": "A437G"},
}

# Country name → ISO3 mapping (covers all 34 Pf8 countries)
COUNTRY_ISO3 = {
    "Bangladesh": "BGD", "Benin": "BEN", "Burkina Faso": "BFA", "Cambodia": "KHM",
    "Cameroon": "CMR", "Colombia": "COL", "Congo DRC": "COD",
    "Democratic Republic of the Congo": "COD", "Ethiopia": "ETH",
    "Gambia": "GMB", "The Gambia": "GMB", "Ghana": "GHA", "Guinea": "GIN",
    "India": "IND", "Indonesia": "IDN", "Kenya": "KEN", "Laos": "LAO",
    "Malawi": "MWI", "Mali": "MLI", "Mauritania": "MRT", "Mozambique": "MOZ",
    "Myanmar": "MMR", "Nigeria": "NGA", "Papua New Guinea": "PNG", "Peru": "PER",
    "Senegal": "SEN", "Sierra Leone": "SLE", "South Sudan": "SSD",
    "Sudan": "SDN", "Tanzania": "TZA", "Thailand": "THA", "Uganda": "UGA",
    "Vietnam": "VNM", "Zambia": "ZMB", "Zimbabwe": "ZWE",
}


def download_tsv(url: str, timeout: int = 300) -> list[dict]:
    """Download a TSV/TXT and return list-of-dict rows."""
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    content = resp.content
    if url.endswith(".gz"):
        content = gzip.decompress(content)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")), delimiter="\t")
    return list(reader)


def aggregate_resistance(samples: list[dict], dr_status: list[dict]) -> list[dict]:
    """
    Join sample metadata (country, year, lat/lng) with resistance classification.
    Aggregate to country × year × drug → prevalence %.

    samples columns:  Sample, Country, Country latitude, Country longitude, Year, QC pass
    dr_status columns: sample, Chloroquine, Artemisinin, Piperaquine, ...
    """
    # Index resistance status by sample ID
    dr_index: dict[str, dict] = {}
    for row in dr_status:
        sid = row.get("sample") or row.get("Sample") or ""
        if sid:
            dr_index[sid.strip()] = row

    # Counters: (iso3, year, drug, marker, mutation) → {total, resistant, lat_sum, lng_sum}
    counts: dict[tuple, dict] = defaultdict(
        lambda: {"total": 0, "resistant": 0, "lat_sum": 0.0, "lng_sum": 0.0}
    )

    skipped_qc = 0
    for s in samples:
        # QC filter
        if str(s.get("QC pass", "True")).strip().lower() not in ("true", "1", "yes"):
            skipped_qc += 1
            continue

        country_name = str(s.get("Country") or "").strip()
        iso3 = COUNTRY_ISO3.get(country_name, "")
        if len(iso3) != 3:
            continue

        year_raw = s.get("Year") or s.get("year") or ""
        try:
            year = int(float(str(year_raw)))
        except (ValueError, TypeError):
            continue
        if year < 1990 or year > 2030:
            continue

        try:
            lat = float(s.get("Country latitude") or 0)
            lng = float(s.get("Country longitude") or 0)
        except (ValueError, TypeError):
            lat, lng = 0.0, 0.0

        sid = str(s.get("Sample") or "").strip()
        dr  = dr_index.get(sid, {})
        if not dr:
            continue

        for drug_col, meta in RESISTANCE_DRUGS.items():
            status = str(dr.get(drug_col) or "").strip()
            if status == "Undetermined" or not status:
                continue

            is_resistant = status == "Resistant"
            key = (iso3, year, meta["drug"], meta["resistance_marker"], meta["mutation"])
            counts[key]["total"] += 1
            if is_resistant:
                counts[key]["resistant"] += 1
            counts[key]["lat_sum"] += lat
            counts[key]["lng_sum"] += lng

    result = []
    for (iso3, year, drug, marker, mutation), v in counts.items():
        total = v["total"]
        if total == 0:
            continue
        prevalence = v["resistant"] / total
        result.append({
            "iso3":              iso3,
            "year":              year,
            "drug":              drug,
            "resistance_marker": marker,
            "mutation":          mutation[:20],
            "prevalence_pct":    round(prevalence, 4),
            "sample_size":       total,
            "severity":          "full" if prevalence >= 0.1 else "partial" if prevalence > 0 else "low",
            "lat":               round(v["lat_sum"] / total, 4) if v["lat_sum"] else None,
            "lng":               round(v["lng_sum"] / total, 4) if v["lng_sum"] else None,
        })

    return result, skipped_qc


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("malariagen_pf8", dry_run=dry_run)

    with log.step("Download Pf8 sample metadata"):
        samples = download_tsv(PF8_SAMPLES_URL)
        log.info(f"  {len(samples):,} samples (metadata/Pf8_samples.txt)")

    with log.step("Download Pf8 resistance status classification"):
        dr_status = download_tsv(PF8_DR_URL)
        log.info(f"  {len(dr_status):,} resistance status rows")

    with log.step("Aggregate to country-year-drug prevalence"):
        agg, skipped_qc = aggregate_resistance(samples, dr_status)
        log.info(f"  {skipped_qc:,} samples skipped (QC fail)")
        log.info(f"  {len(agg):,} country-year-drug records")

    payload = {
        "_meta": {
            "source":        SOURCE_CODE,
            "release":       "Pf8",
            "n_samples":     len(samples),
            "record_count":  len(agg),
            "fetched_at":    datetime.now(timezone.utc).isoformat(),
        },
        "rows": agg,
    }

    key_json = raw_key("malariagen-pf8", "pf8-resistance.json", date=date)
    key_tsv  = raw_key("malariagen-pf8", "pf8-samples.tsv.gz",  date=date)

    if not dry_run:
        with log.step("Upload aggregated JSON to S3"):
            put_json(key_json, payload)
            put_meta(key_json, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key_json}")

        with log.step("Upload raw sample metadata TSV to S3"):
            resp = requests.get(PF8_SAMPLES_URL, timeout=300, stream=True)
            resp.raise_for_status()
            raw_bytes = gzip.compress(resp.content)
            s3_client.put_object(
                Bucket=BUCKET, Key=key_tsv, Body=raw_bytes,
                ContentType="text/tab-separated-values",
                ContentEncoding="gzip",
            )
            log.info(f"  s3://{BUCKET}/{key_tsv}")

        with log.step("Upsert → PostgreSQL fact_drug_resistance"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_drug_resistance
                        (iso3, year, drug, resistance_marker, mutation,
                         prevalence_pct, sample_size, data_source, severity, lat, lng)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], r["drug"], r["resistance_marker"],
                     r["mutation"], r["prevalence_pct"], r["sample_size"],
                     SOURCE_CODE, r["severity"], r.get("lat"), r.get("lng"))
                    for r in agg
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB upsert failed: {e}")
    else:
        log.info(f"[DRY RUN] {len(agg)} aggregated rows ready")

    log.finish(records=len(agg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
