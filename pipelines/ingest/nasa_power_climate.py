"""
L0 — NASA POWER climate ingest.
PRIMARY: Reads per-country JSON files from foundation bucket:
  raw/malaria-intelligence/nasa_power/{ISO3}_monthly_climate.json  (80 countries)

Format: GeoJSON Feature — properties.parameter.{PARAM}.{YYYYMM} = value
  PRECTOTCORR = precipitation mm/day
  T2M / T2M_MAX / T2M_MIN = temperature °C
  RH2M = relative humidity %

FALLBACK: Live NASA POWER API for countries not in foundation.

Usage:
    python -m pipelines.ingest.nasa_power_climate [--dry-run] [--date YYYY-MM-DD] [--live]
"""

import argparse
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
FOUNDATION_PREFIX = "raw/malaria-intelligence/nasa_power"
NASA_API = "https://power.larc.nasa.gov/api/temporal/monthly/point"
SOURCE_CODE = "nasa_power"

# Centroids for countries not in foundation (live API fallback)
FALLBACK_CENTROIDS = {
    "NGA": (9.08, 8.68), "COD": (-4.04, 21.76), "MOZ": (-18.67, 35.53),
    "ETH": (9.15, 40.49), "TZA": (-6.37, 34.89), "UGA": (1.37, 32.29),
    "KEN": (-0.02, 37.91), "GHA": (7.95, -1.02), "MDG": (-18.77, 46.87),
    "MWI": (-13.25, 34.30), "ZMB": (-13.13, 27.85), "CMR": (3.85, 11.50),
    "BFA": (12.36, -1.53), "MLI": (17.57, -3.10), "GIN": (9.95, -11.24),
    "SEN": (14.50, -14.45), "AGO": (-11.20, 17.87), "ZWE": (-19.02, 29.15),
    "SDN": (15.56, 32.53), "PNG": (-6.31, 143.96), "MMR": (21.92, 95.96),
    "HTI": (18.97, -72.29), "RWA": (-1.94, 29.87), "TGO": (8.62, 0.82),
    "BEN": (9.31, 2.32), "COL": (4.57, -74.30), "BRA": (-14.24, -51.93),
    "IND": (20.59, 78.96), "IDN": (-0.79, 113.92), "PRK": (40.34, 127.51),
}

_s3 = boto3.client("s3", region_name="us-east-1")


def list_foundation_countries() -> list[str]:
    """List all ISO3 codes available in foundation nasa_power prefix."""
    paginator = _s3.get_paginator("list_objects_v2")
    iso3_list = []
    for page in paginator.paginate(Bucket=FOUNDATION_BUCKET, Prefix=f"{FOUNDATION_PREFIX}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.split("/")[-1]
            if filename.endswith("_monthly_climate.json"):
                iso3 = filename.replace("_monthly_climate.json", "")
                if len(iso3) == 3:
                    iso3_list.append(iso3)
    return iso3_list


def parse_nasa_geojson(iso3: str, data: dict) -> list[dict]:
    """
    Parse NASA POWER GeoJSON Feature.
    properties.parameter.{PARAM}.{YYYYMM} = float value
    YYYYMM: 200001 = Jan 2000, month 13 = annual mean (skip)
    """
    props = data.get("properties", {}).get("parameter", {})
    t2m    = props.get("T2M", {})
    t2mmax = props.get("T2M_MAX", {})
    t2mmin = props.get("T2M_MIN", {})
    prec   = props.get("PRECTOTCORR", {})
    rh2m   = props.get("RH2M", {})

    rows = []
    for yyyymm, temp in t2m.items():
        if len(yyyymm) != 6:
            continue
        try:
            year  = int(yyyymm[:4])
            month = int(yyyymm[4:])
        except ValueError:
            continue
        if month == 13:  # annual mean — skip
            continue
        if temp == -999:
            continue

        rain_raw = prec.get(yyyymm, None)
        rain_mm  = float(rain_raw) * 30 if rain_raw is not None and rain_raw != -999 else None

        rows.append({
            "iso3":        iso3,
            "year":        year,
            "month":       month,
            "temp_avg_c":  float(temp) if temp != -999 else None,
            "temp_max_c":  float(t2mmax[yyyymm]) if t2mmax.get(yyyymm, -999) != -999 else None,
            "temp_min_c":  float(t2mmin[yyyymm]) if t2mmin.get(yyyymm, -999) != -999 else None,
            "rainfall_mm": rain_mm,
            "humidity_pct": float(rh2m[yyyymm]) if rh2m.get(yyyymm, -999) != -999 else None,
            "source":      SOURCE_CODE,
        })
    return rows


def fetch_live_nasa(iso3: str, lat: float, lon: float) -> list[dict]:
    end_year = datetime.now().year - 1
    params = {
        "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M",
        "community": "AG", "longitude": lon, "latitude": lat,
        "start": "2000", "end": str(end_year), "format": "JSON",
    }
    try:
        resp = requests.get(NASA_API, params=params, timeout=60)
        resp.raise_for_status()
        return parse_nasa_geojson(iso3, resp.json())
    except Exception:
        return []


def run(dry_run: bool = False, date: str | None = None, live: bool = False) -> None:
    log = PipelineLogger("nasa_power_climate", dry_run=dry_run)
    all_rows: list[dict] = []

    # ── Foundation bucket ──────────────────────────────────────────────────
    with log.step("Load NASA POWER from foundation bucket"):
        foundation_iso3s = list_foundation_countries()
        log.info(f"  {len(foundation_iso3s)} countries in foundation")

        for iso3 in foundation_iso3s:
            key = f"{FOUNDATION_PREFIX}/{iso3}_monthly_climate.json"
            try:
                resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
                data = json.loads(resp["Body"].read())
                rows = parse_nasa_geojson(iso3, data)
                all_rows.extend(rows)
            except Exception as e:
                log.warn(f"  {iso3}: {e}")

        log.info(f"  Foundation rows: {len(all_rows)}")

    # ── Live API for countries not in foundation ───────────────────────────
    if live:
        missing = [iso3 for iso3 in FALLBACK_CENTROIDS if iso3 not in foundation_iso3s]
        with log.step(f"Fetch {len(missing)} missing countries via live API"):
            for iso3 in missing:
                lat, lon = FALLBACK_CENTROIDS[iso3]
                rows = fetch_live_nasa(iso3, lat, lon)
                log.info(f"  {iso3}: {len(rows)} rows")
                all_rows.extend(rows)

    # Deduplicate
    seen = set()
    deduped = []
    for r in all_rows:
        k = (r["iso3"], r["year"], r["month"])
        if k not in seen:
            seen.add(k)
            deduped.append(r)

    log.info(f"Total: {len(deduped)} country-month records ({len(set(r['iso3'] for r in deduped))} countries)")

    payload = {
        "_meta": {"source": SOURCE_CODE, "record_count": len(deduped),
                  "fetched_at": datetime.now(timezone.utc).isoformat()},
        "rows": deduped,
    }
    key = raw_key("nasa-power", "country-monthly.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_climate"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_climate
                        (iso3, year, month, temp_avg_c, temp_max_c, temp_min_c,
                         rainfall_mm, humidity_pct, source)
                    VALUES %s
                    ON CONFLICT (iso3, year, month, source)
                    DO UPDATE SET temp_avg_c=EXCLUDED.temp_avg_c,
                                  rainfall_mm=EXCLUDED.rainfall_mm, ingested_at=NOW()
                """
                db_rows = [
                    (r["iso3"], r["year"], r["month"],
                     r.get("temp_avg_c"), r.get("temp_max_c"), r.get("temp_min_c"),
                     r.get("rainfall_mm"), r.get("humidity_pct"), SOURCE_CODE)
                    for r in deduped if r.get("iso3") and r.get("year") and r.get("month")
                ]
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] {len(deduped)} rows")

    log.finish(records=len(deduped))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date, live=args.live)
