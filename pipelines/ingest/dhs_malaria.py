"""
L0 — DHS (Demographic and Health Surveys) malaria ingest.
Reads pre-fetched DHS CSVs from foundation bucket:
  raw/health/disease-surveillance/dhs/dhs_malaria_prevalence.csv  — malaria RDT prevalence by country/region
  raw/health/disease-surveillance/dhs/dhs_itn_usage.csv           — ITN usage rates
  raw/health/disease-surveillance/dhs/dhs_fever_treatment.csv     — fever treatment rates

DHS data is household-survey-based — highly granular, sub-national, with confidence intervals.
Columns: country, iso2, region, survey_year, indicator, indicator_name, value, ci_low, ci_high, denominator

Writes to:
  - S3 raw layer
  - fact_intervention (ITN usage, fever treatment)
  - fact_parasite_rate (malaria prevalence as RDT-based parasite rate)

Usage:
    python -m pipelines.ingest.dhs_malaria [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

DHS_FILES = {
    "prevalence":      "raw/health/disease-surveillance/dhs/dhs_malaria_prevalence.csv",
    "itn_usage":       "raw/health/disease-surveillance/dhs/dhs_itn_usage.csv",
    "fever_treatment": "raw/health/disease-surveillance/dhs/dhs_fever_treatment.csv",
}

# DHS indicator → our metric name
INDICATOR_MAP = {
    "malaria_prevalence":  ("rdt_positivity_pct", "intervention"),
    "itn_use":             ("itn_use_pct",         "intervention"),
    "itn_usage":           ("itn_use_pct",         "intervention"),
    "fever_treatment":     ("fever_treatment_pct", "intervention"),
    "ml_pmal_c_rdt":       ("rdt_positivity_pct", "parasite_rate"),
    "ml_nets_u5":          ("itn_use_pct",         "intervention"),
    "ml_fever_trt_ttl":    ("fever_treatment_pct", "intervention"),
}

SOURCE_CODE = "dhs"
_s3 = boto3.client("s3", region_name="us-east-1")

# ISO2 → ISO3 lookup for common DHS countries
ISO2_TO_ISO3 = {
    "AO": "AGO", "BJ": "BEN", "BF": "BFA", "BI": "BDI", "CM": "CMR",
    "CF": "CAF", "TD": "TCD", "CD": "COD", "CG": "COG", "CI": "CIV",
    "ET": "ETH", "GA": "GAB", "GH": "GHA", "GN": "GIN", "GW": "GNB",
    "KE": "KEN", "LS": "LSO", "LR": "LBR", "MW": "MWI", "ML": "MLI",
    "MR": "MRT", "MZ": "MOZ", "NA": "NAM", "NE": "NER", "NG": "NGA",
    "RW": "RWA", "SN": "SEN", "SL": "SLE", "SO": "SOM", "ZA": "ZAF",
    "SD": "SDN", "SZ": "SWZ", "TZ": "TZA", "TG": "TGO", "UG": "UGA",
    "ZM": "ZMB", "ZW": "ZWE", "GY": "GUY", "HT": "HTI", "HN": "HND",
    "IN": "IND", "ID": "IDN", "KH": "KHM", "LA": "LAO", "MM": "MMR",
    "NP": "NPL", "PG": "PNG", "PH": "PHL", "TL": "TLS",
    "BO": "BOL", "CO": "COL", "PE": "PER", "PY": "PRY",
    "AF": "AFG", "PK": "PAK", "YE": "YEM",
}


def load_csv(path_key: str) -> list[dict]:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=path_key)
        content = resp["Body"].read().decode("utf-8", errors="replace")
        return list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []


def resolve_iso3(row: dict) -> str:
    iso3 = (row.get("iso3") or row.get("ISO3") or "").strip().upper()
    if len(iso3) == 3:
        return iso3
    iso2 = (row.get("iso2") or row.get("ISO2") or "").strip().upper()
    return ISO2_TO_ISO3.get(iso2, "")


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("dhs_malaria", dry_run=dry_run)
    all_rows: list[dict] = []

    for file_type, path_key in DHS_FILES.items():
        with log.step(f"Load DHS {file_type}"):
            rows = load_csv(path_key)
            if not rows:
                log.warn(f"  Not found or empty: {path_key}")
                continue
            log.info(f"  {len(rows)} rows")

            for row in rows:
                iso3 = resolve_iso3(row)
                if not iso3:
                    continue

                year_raw = row.get("survey_year") or row.get("year") or ""
                try:
                    year = int(float(str(year_raw).split("-")[0]))  # "2018-19" → 2018
                except (ValueError, TypeError):
                    continue

                indicator = (row.get("indicator") or row.get("indicator_name") or "").lower().strip()
                value_raw = row.get("value") or row.get("Value") or ""
                try:
                    value = float(str(value_raw).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue

                ci_low  = None
                ci_high = None
                try:
                    ci_low  = float(str(row.get("ci_low") or 0))
                    ci_high = float(str(row.get("ci_high") or 0))
                except (ValueError, TypeError):
                    pass

                region = row.get("region") or row.get("admin1") or ""

                # Map indicator to metric
                metric, table = None, None
                for kw, (m, t) in INDICATOR_MAP.items():
                    if kw in indicator:
                        metric, table = m, t
                        break
                if not metric:
                    # Infer from file_type
                    metric = "rdt_positivity_pct" if file_type == "prevalence" else \
                             "itn_use_pct" if file_type == "itn_usage" else "fever_treatment_pct"
                    table  = "parasite_rate" if file_type == "prevalence" else "intervention"

                all_rows.append({
                    "iso3":     iso3,
                    "year":     year,
                    "metric":   metric,
                    "table":    table,
                    "value":    value,
                    "ci_low":   ci_low,
                    "ci_high":  ci_high,
                    "region":   region,
                    "source":   SOURCE_CODE,
                })

    log.info(f"Total DHS rows parsed: {len(all_rows)}")

    payload = {
        "_meta": {"source": SOURCE_CODE, "record_count": len(all_rows),
                  "fetched_at": datetime.now(timezone.utc).isoformat()},
        "rows": all_rows,
    }
    key = raw_key("dhs-malaria", "dhs-indicators.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3

                int_rows = [r for r in all_rows if r["table"] == "intervention"]
                pr_rows  = [r for r in all_rows if r["table"] == "parasite_rate"]

                if int_rows:
                    SQL_I = """
                        INSERT INTO malaria.fact_intervention
                            (iso3, year, source_code, indicator, value, unit)
                        VALUES %s
                        ON CONFLICT (iso3, year, source_code, indicator)
                        DO UPDATE SET value=EXCLUDED.value, ingested_at=NOW()
                    """
                    i_tuples = [
                        (r["iso3"], r["year"], SOURCE_CODE, r["metric"], r["value"], "pct")
                        for r in int_rows
                    ]
                    i_tuples, i_skip = filter_valid_iso3(i_tuples, iso3_col=0)
                    if i_skip:
                        log.info(f"  Skipped {i_skip} intervention rows (ISO3 not in dim_country)")
                    # Dedup by conflict key (iso3, year, source_code, indicator)
                    seen_keys: set = set()
                    deduped_i = []
                    for row in i_tuples:
                        k = (row[0], row[1], row[2], row[3])
                        if k not in seen_keys:
                            seen_keys.add(k)
                            deduped_i.append(row)
                    if len(deduped_i) < len(i_tuples):
                        log.info(f"  Deduped {len(i_tuples)-len(deduped_i)} duplicate intervention rows")
                    i_tuples = deduped_i
                    upsert_many(SQL_I, i_tuples)
                    log.info(f"  Upserted {len(i_tuples)} intervention rows")

                if pr_rows:
                    SQL_PR = """
                        INSERT INTO malaria.fact_parasite_rate
                            (iso3, species, year, survey_type, pr_mean, pr_lower, pr_upper, admin1)
                        VALUES %s ON CONFLICT DO NOTHING
                    """
                    pr_tuples = [
                        (r["iso3"], "pf", r["year"], "rdt",
                         r["value"] / 100.0 if r["value"] > 1 else r["value"],
                         (r["ci_low"] or 0) / 100.0 if r.get("ci_low") else None,
                         (r["ci_high"] or 0) / 100.0 if r.get("ci_high") else None,
                         r.get("region", ""))
                        for r in pr_rows
                    ]
                    pr_tuples, pr_skip = filter_valid_iso3(pr_tuples, iso3_col=0)
                    if pr_skip:
                        log.info(f"  Skipped {pr_skip} parasite rate rows (ISO3 not in dim_country)")
                    upsert_many(SQL_PR, pr_tuples)
                    log.info(f"  Upserted {len(pr_tuples)} parasite rate rows")
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
