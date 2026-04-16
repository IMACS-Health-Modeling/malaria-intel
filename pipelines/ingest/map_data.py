"""
L0 — Malaria Atlas Project (MAP) parasite rate ingest.
PRIMARY: Reads pre-fetched JSON from foundation bucket:
  raw/malaria-intelligence/map/public_pf_data.json   (54MB)
  raw/malaria-intelligence/map/public_pv_data.json   (15MB)
  raw/malaria-intelligence/map/pf_parasite_rate_surveys_202406.json (68MB)
  raw/malaria-intelligence/map/pv_parasite_rate_surveys_202406.json (20MB)

Also reads admin-level MAP summary CSVs:
  raw/health/disease-burden/map/pf_incidence_rate.csv
  raw/health/disease-burden/map/pf_mortality_rate.csv
  raw/health/disease-burden/map/itn_access.csv

Aggregates survey data to country-year mean parasite rate.

Usage:
    python -m pipelines.ingest.map_data [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

# Confirmed S3 keys from bucket audit
MAP_SURVEY_FILES = {
    "pf": [
        "raw/malaria-intelligence/map/pf_parasite_rate_surveys_202406.json",  # 68MB, preferred
        "raw/malaria-intelligence/map/public_pf_data.json",                    # 54MB, fallback
    ],
    "pv": [
        "raw/malaria-intelligence/map/pv_parasite_rate_surveys_202406.json",  # 20MB, preferred
        "raw/malaria-intelligence/map/public_pv_data.json",                    # 15MB, fallback
    ],
}

MAP_ADMIN_FILES = {
    "pf_incidence_rate": "raw/health/disease-burden/map/pf_incidence_rate.csv",
    "pf_mortality_rate": "raw/health/disease-burden/map/pf_mortality_rate.csv",
    "itn_access":        "raw/health/disease-burden/map/itn_access.csv",
}

SOURCE_CODE = "map_project"
_s3 = boto3.client("s3", region_name="us-east-1")


def load_foundation_json(key: str) -> list | dict | None:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
        return json.loads(resp["Body"].read())
    except Exception:
        return None


def load_foundation_csv(key: str) -> list[dict]:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
        content = resp["Body"].read().decode("utf-8", errors="replace")
        return list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []


def parse_map_json_surveys(data: list | dict, species: str) -> list[dict]:
    """
    Parse MAP survey JSON. Structure varies by version:
    - GeoJSON FeatureCollection: {"type": "FeatureCollection", "features": [{"properties": {...}}, ...]}
    - Array of survey objects with keys: ISO3/country_id, year/year_start, pr/pf_pr/pv_pr, examined, latitude, longitude
    - Or {"data": [...]} wrapper
    """
    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            # GeoJSON: extract properties from each feature
            records = [
                f["properties"] for f in data.get("features", [])
                if isinstance(f, dict) and isinstance(f.get("properties"), dict)
            ]
        else:
            records = data.get("data", data.get("surveys", data.get("value", [])))
    else:
        records = data

    buckets: dict[tuple, list[float]] = defaultdict(list)
    samples: dict[tuple, int] = defaultdict(int)
    lats: dict[tuple, list[float]] = defaultdict(list)
    lngs: dict[tuple, list[float]] = defaultdict(list)

    for r in records:
        if not isinstance(r, dict):
            continue
        # ISO3 field
        iso3 = (r.get("ISO3") or r.get("iso3") or r.get("country_id") or
                r.get("COUNTRY_ID") or r.get("iso") or "").strip().upper()
        if len(iso3) != 3:
            continue

        # Year
        year_raw = (r.get("year_start") or r.get("year") or r.get("Year") or
                    r.get("YEAR") or r.get("survey_year") or "")
        try:
            year = int(float(str(year_raw).split(".")[0]))
        except (ValueError, TypeError):
            continue

        # PR value
        pr_raw = (r.get(f"{species}_pr") or r.get("pr") or r.get("PR") or
                  r.get("parasite_rate") or r.get("Parasite_Rate") or
                  r.get("prevalence") or "")
        try:
            pr = float(pr_raw)
            if pr > 1.0:
                pr = pr / 100.0
            if not (0.0 <= pr <= 1.0):
                continue
        except (ValueError, TypeError):
            continue

        sample_raw = (r.get("examined") or r.get("EXAMINED") or r.get("sample_size") or
                      r.get("n_examined") or 0)
        try:
            sample = int(float(str(sample_raw)))
        except (ValueError, TypeError):
            sample = 0

        key_t = (iso3, year)
        buckets[key_t].append(pr)
        samples[key_t] += sample
        try:
            lats[key_t].append(float(r.get("latitude") or r.get("lat") or r.get("Lat") or 0))
            lngs[key_t].append(float(r.get("longitude") or r.get("lng") or r.get("Long") or 0))
        except (ValueError, TypeError):
            pass

    results = []
    for (iso3, year), pr_vals in buckets.items():
        lat_vals = [v for v in lats[(iso3, year)] if v != 0]
        lng_vals = [v for v in lngs[(iso3, year)] if v != 0]
        results.append({
            "iso3":         iso3,
            "species":      species,
            "year":         year,
            "pr_mean":      round(mean(pr_vals), 5),
            "sample_size":  samples[(iso3, year)],
            "survey_count": len(pr_vals),
            "lat":          round(mean(lat_vals), 4) if lat_vals else None,
            "lng":          round(mean(lng_vals), 4) if lng_vals else None,
        })

    return sorted(results, key=lambda x: (x["iso3"], x["year"]))


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("map_data", dry_run=dry_run)
    all_agg: list[dict] = []

    # ── Survey JSON files ──────────────────────────────────────────────────
    for species, candidate_keys in MAP_SURVEY_FILES.items():
        data = None
        used_key = None
        with log.step(f"Load MAP {species.upper()} surveys from foundation bucket"):
            for s3_key in candidate_keys:
                log.info(f"  Trying: {s3_key}")
                data = load_foundation_json(s3_key)
                if data is not None:
                    used_key = s3_key
                    break

        if data is None:
            log.warn(f"  No {species} survey data found in foundation bucket")
            continue

        with log.step(f"Aggregate {species.upper()} to country-year"):
            agg = parse_map_json_surveys(data, species)
            log.info(f"  {len(agg)} country-year records from {used_key}")
            all_agg.extend(agg)

    # ── Admin summary CSVs ─────────────────────────────────────────────────
    with log.step("Load MAP admin summary CSVs"):
        for name, s3_key in MAP_ADMIN_FILES.items():
            rows = load_foundation_csv(s3_key)
            log.info(f"  {name}: {len(rows)} rows")
            # These are country-level summary stats — store as intervention metrics
            for r in rows:
                iso3 = (r.get("ISO3") or r.get("iso3") or r.get("country_code") or "").upper()
                year = r.get("year") or r.get("Year")
                value = r.get("value") or r.get("Value") or r.get("mean")
                if iso3 and len(iso3) == 3 and year and value:
                    all_agg.append({
                        "iso3":    iso3, "species": "pf",
                        "year":    int(float(str(year))),
                        "pr_mean": float(str(value).replace(",", "")),
                        "sample_size": 0, "survey_count": 0,
                        "lat": None, "lng": None,
                        "metric_type": name,
                    })

    log.info(f"Total aggregated records: {len(all_agg)}")

    # ── S3 output ──────────────────────────────────────────────────────────
    payload = {
        "_meta": {
            "source": SOURCE_CODE, "record_count": len(all_agg),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "parasite_rates": all_agg,
    }
    key = raw_key("map-aggregated", "country-year-pr.json", date=date)

    if not dry_run:
        with log.step("Upload aggregated JSON to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_parasite_rate"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_parasite_rate
                        (iso3, species, year, survey_type, pr_mean, sample_size, lat, lng, raw_s3_key)
                    VALUES %s ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["species"], r["year"], "community",
                     r["pr_mean"], r.get("sample_size", 0), r.get("lat"), r.get("lng"), key)
                    for r in all_agg if r.get("pr_mean") is not None
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] Would write {len(all_agg)} rows")

    log.finish(records=len(all_agg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
