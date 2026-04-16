"""
L0 — Malaria drug resistance ingest.
PRIMARY: Reads WMR drug resistance Excel from foundation bucket:
  raw/malaria-intelligence/drug_resistance/wmr2024_annex_2_drug_resistance.xlsx  (confirmed)
  raw/malaria-intelligence/drug_resistance/elife_kelch13_artR_supp1.xlsx         (artemisinin resistance)

Parses by country-year-drug-mutation and stores in PostgreSQL fact_drug_resistance.

Usage:
    python -m pipelines.ingest.drug_resistance_ingest [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import openpyxl
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

# Confirmed foundation paths from S3 audit
FOUNDATION_FILES = [
    {
        # NOTE: This file is WMR Annex 2 (ITN distribution data), NOT therapeutic efficacy.
        # It is skipped here; ITN data is ingested by dhs_malaria and who_gho_full pipelines.
        # True drug resistance data (WMR Annex 4 / WWARN) is not yet in the foundation bucket.
        "key":    "raw/malaria-intelligence/drug_resistance/wmr2024_annex_2_drug_resistance.xlsx",
        "source": "wmr_2024",
        "type":   "wmr_annex2",
        "skip":   True,
    },
    {
        "key":    "raw/malaria-intelligence/drug_resistance/elife_kelch13_artR_supp1.xlsx",
        "source": "wmr_2024",
        "type":   "elife_kelch13",
        "skip":   False,
    },
]

DRUG_KEYWORDS = {
    "artemisinin": ["artemisinin", "artesunate", "kelch", "k13", "pfkelch13", "c580y", "f446i", "r539t", "art"],
    "chloroquine": ["chloroquine", "cq", "pfcrt", "76t"],
    "sp":          ["sulfadoxine", "sp", "pyrimethamine", "pfdhfr", "pfdhps", "dhfr", "dhps"],
    "lumefantrine": ["lumefantrine", "lum", "pfmdr1"],
    "piperaquine": ["piperaquine", "pip", "plasmepsin"],
}

SEVERITY_KEYWORDS = {
    "full":    ["full", "high", "resistant", ">10%", ">20%"],
    "partial": ["partial", "moderate", "intermediate", "5-10%"],
    "low":     ["low", "suspected", "emerging", "rare", "<5%"],
}

_s3 = boto3.client("s3", region_name="us-east-1")


def load_foundation_xlsx(key: str) -> bytes | None:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
        return resp["Body"].read()
    except Exception:
        return None


def classify_drug(text: str) -> str:
    t = text.lower()
    for drug, kws in DRUG_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return drug
    return "unknown"


def classify_severity(text: str) -> str:
    t = text.lower()
    for severity, kws in SEVERITY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return severity
    return "low"


def parse_wmr_annex2(ws) -> list[dict]:
    """Parse WMR annex 2 drug resistance sheet."""
    rows_out: list[dict] = []
    header_found = False
    col_map: dict[str, int] = {}

    for row in ws.iter_rows(values_only=True):
        if not any(row):
            continue
        row_str = [str(c).lower().strip() if c is not None else "" for c in row]

        if not header_found:
            if any(k in row_str for k in ("iso3", "country", "country code")):
                header_found = True
                for j, cell in enumerate(row_str):
                    col_map[cell] = j
                continue
        else:
            def _get(*keys):
                for k in keys:
                    if k in col_map and row[col_map[k]] is not None:
                        return row[col_map[k]]
                return None

            iso3       = _get("iso3", "iso", "country code", "iso3_code")
            year       = _get("year", "survey_year", "report_year", "data_year")
            drug       = _get("drug", "antimalarial", "drug_name", "medicine", "treatment")
            mutation   = _get("mutation", "marker", "resistance_marker", "allele", "variant")
            prevalence = _get("prevalence_pct", "prevalence", "frequency", "frequency_pct", "%", "proportion")
            sample     = _get("sample_size", "n", "samples", "tested", "surveyed")
            severity   = _get("severity", "resistance_level", "level", "classification")
            lat        = _get("latitude", "lat")
            lng        = _get("longitude", "lng", "long", "lon")
            country    = _get("country", "country_name", "name")

            # Infer iso3 from country name if missing
            if not iso3 and country:
                iso3 = str(country).strip().upper()[:3]

            if not iso3 or len(str(iso3).strip()) != 3:
                continue
            try:
                year_int = int(float(str(year))) if year else None
            except (ValueError, TypeError):
                year_int = None
            if not year_int:
                continue

            drug_str = str(drug or "").strip()
            mut_str  = str(mutation or "").strip()
            sev_str  = str(severity or "").strip()

            try:
                prev = float(str(prevalence or 0).replace("%", "").replace(",", "").strip())
                if prev > 1.0:
                    prev = prev / 100.0
            except (ValueError, TypeError):
                prev = None

            rows_out.append({
                "iso3":              str(iso3).strip().upper(),
                "year":              year_int,
                "drug":              classify_drug(drug_str),
                "resistance_marker": mut_str[:50],
                "mutation":          mut_str[:20],
                "prevalence_pct":    prev,
                "sample_size":       int(float(str(sample))) if sample else None,
                "severity":          classify_severity(sev_str or drug_str),
                "lat":               float(lat) if lat else None,
                "lng":               float(lng) if lng else None,
            })

    return rows_out


def parse_kelch13(ws) -> list[dict]:
    """Parse eLife kelch13 artemisinin resistance supplementary data."""
    rows_out: list[dict] = []
    header_found = False
    col_map: dict[str, int] = {}

    for row in ws.iter_rows(values_only=True):
        if not any(row):
            continue
        row_str = [str(c).lower().strip() if c is not None else "" for c in row]

        if not header_found:
            if any(k in row_str for k in ("country", "iso3", "mutation", "kelch")):
                header_found = True
                for j, cell in enumerate(row_str):
                    col_map[cell] = j
                continue
        else:
            def _get(*keys):
                for k in keys:
                    if k in col_map and row[col_map[k]] is not None:
                        return row[col_map[k]]
                return None

            iso3     = _get("iso3", "iso", "country code")
            country  = _get("country", "country_name")
            year     = _get("year", "sample_year", "collection_year")
            mutation = _get("mutation", "variant", "allele", "kelch13_mutation")
            prev     = _get("prevalence", "frequency", "proportion", "%")
            sample   = _get("n", "sample_size", "samples")
            lat      = _get("latitude", "lat")
            lng      = _get("longitude", "lng", "long")

            if not iso3 and country:
                iso3 = str(country).strip().upper()[:3]
            if not iso3 or len(str(iso3).strip()) != 3:
                continue
            try:
                year_int = int(float(str(year))) if year else None
            except (ValueError, TypeError):
                year_int = None
            if not year_int:
                continue

            try:
                prev_f = float(str(prev or 0).replace("%", "").strip())
                if prev_f > 1.0:
                    prev_f = prev_f / 100.0
            except (ValueError, TypeError):
                prev_f = None

            rows_out.append({
                "iso3":              str(iso3).strip().upper(),
                "year":              year_int,
                "drug":              "artemisinin",
                "resistance_marker": "pfkelch13",
                "mutation":          str(mutation or "")[:20],
                "prevalence_pct":    prev_f,
                "sample_size":       int(float(str(sample))) if sample else None,
                "severity":          "partial",  # kelch13 = partial resistance
                "lat":               float(lat) if lat else None,
                "lng":               float(lng) if lng else None,
            })

    return rows_out


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("drug_resistance_ingest", dry_run=dry_run)
    all_rows: list[dict] = []

    for file_spec in FOUNDATION_FILES:
        key  = file_spec["key"]
        src  = file_spec["source"]
        kind = file_spec["type"]

        if file_spec.get("skip"):
            log.info(f"  Skipping {key.split('/')[-1]} (ITN data, not drug resistance)")
            continue

        with log.step(f"Load {kind} from foundation: {key.split('/')[-1]}"):
            content = load_foundation_xlsx(key)
            if content is None:
                log.warn(f"  Not found: {key}")
                continue

            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            log.info(f"  Sheets: {wb.sheetnames}")

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                if kind == "kelch13":
                    rows = parse_kelch13(ws)
                else:
                    rows = parse_wmr_annex2(ws)
                if rows:
                    log.info(f"  Sheet '{sheet_name}': {len(rows)} rows")
                    all_rows.extend(rows)

    log.info(f"Total drug resistance records: {len(all_rows)}")

    if not all_rows:
        log.warn("No data parsed — check sheet structure")
        log.finish(records=0)
        return

    payload = {
        "_meta": {
            "source": "wmr_2024",
            "record_count": len(all_rows),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "rows": all_rows,
    }
    key = raw_key("drug-resistance", "wmr-dr.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_drug_resistance"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_drug_resistance
                        (iso3, year, drug, resistance_marker, mutation,
                         prevalence_pct, sample_size, data_source, severity, lat, lng)
                    VALUES %s ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], r["drug"], r.get("resistance_marker", ""),
                     r.get("mutation", ""), r.get("prevalence_pct"), r.get("sample_size"),
                     "wmr_2024", r.get("severity", "low"), r.get("lat"), r.get("lng"))
                    for r in all_rows
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] {len(all_rows)} rows")

    log.finish(records=len(all_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
