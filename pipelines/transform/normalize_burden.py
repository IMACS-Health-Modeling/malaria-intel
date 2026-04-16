"""
L1 — Normalize all burden sources into a unified fact_burden table.
Reads from S3 raw layer and reconciles overlapping sources with
a priority-based merge: WMR > WHO GHO > PAHO > CDC MMWR.

Also computes derived metrics:
  - YoY case change %
  - 5-year trend (linear slope)
  - Alert level classification

Usage:
    python -m pipelines.transform.normalize_burden [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.logger import PipelineLogger
from pipelines.utils.db import fetchall, upsert_many

# Source priority for conflict resolution (higher = preferred)
SOURCE_PRIORITY = {
    "wmr_2025": 100,
    "wmr_2024": 90,
    "wmr_2023": 80,
    "wmr_2022": 70,
    "who_gho":  60,
    "paho_plisa": 50,
    "cdc_mmwr": 40,
    "ihme_gbd": 35,
}

# Alert level thresholds (incidence per 1000)
ALERT_THRESHOLDS = [
    (0.001, "none"),
    (1.0,   "low"),
    (50.0,  "moderate"),
    (150.0, "high"),
    (float("inf"), "critical"),
]

def classify_alert(incidence: float | None) -> str:
    if incidence is None:
        return "unknown"
    for threshold, level in ALERT_THRESHOLDS:
        if incidence < threshold:
            return level
    return "critical"


def compute_yoy(rows: list[dict]) -> dict[tuple, float | None]:
    """Compute year-over-year change for cases_estimated per (iso3, source)."""
    # Build map: (iso3, source) -> {year -> value}
    data: dict[tuple, dict[int, float]] = {}
    for r in rows:
        if r["metric"] != "cases_estimated":
            continue
        key = (r["iso3"], r["source_code"])
        if key not in data:
            data[key] = {}
        if r["value"] is not None:
            data[key][r["year"]] = r["value"]

    yoy: dict[tuple, float | None] = {}
    for (iso3, src), year_vals in data.items():
        years = sorted(year_vals.keys())
        if len(years) < 2:
            continue
        latest = years[-1]
        prev = years[-2]
        if year_vals[prev] and year_vals[prev] > 0:
            change = (year_vals[latest] - year_vals[prev]) / year_vals[prev]
            yoy[(iso3, src, latest)] = round(change, 4)

    return yoy


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("normalize_burden", dry_run=dry_run)

    # ── Read all burden rows from DB ───────────────────────────────────────
    with log.step("Load fact_burden from PostgreSQL"):
        rows = fetchall("SELECT * FROM malaria.fact_burden ORDER BY iso3, year, metric, source_code")
        log.info(f"  {len(rows)} rows loaded")

    if not rows:
        log.warn("No burden data found — run L0 ingest scripts first")
        log.finish(records=0)
        return

    # ── Deduplicate: keep highest-priority source per (iso3, year, metric) ─
    with log.step("Deduplicate by source priority"):
        best: dict[tuple, dict] = {}
        for row in rows:
            key = (row["iso3"], row["year"], row["metric"])
            priority = SOURCE_PRIORITY.get(row["source_code"], 0)
            if key not in best or priority > SOURCE_PRIORITY.get(best[key]["source_code"], 0):
                best[key] = row
        canonical = list(best.values())
        log.info(f"  {len(canonical)} canonical rows after dedup")

    # ── Compute derived metrics ────────────────────────────────────────────
    with log.step("Compute YoY + alert levels"):
        yoy_map = compute_yoy(canonical)

        # Build per-country latest incidence for alert classification
        incidence_by_country: dict[str, float] = {}
        for row in canonical:
            if row["metric"] == "incidence_per_1000" and row["value"]:
                iso3 = row["iso3"]
                if iso3 not in incidence_by_country or row["year"] > incidence_by_country.get(f"_yr_{iso3}", 0):
                    incidence_by_country[iso3] = row["value"]
                    incidence_by_country[f"_yr_{iso3}"] = row["year"]

    # ── Write derived metrics to processed layer ───────────────────────────
    if not dry_run:
        with log.step("Write processed burden JSON to S3"):
            try:
                from pipelines.utils.s3 import put_json, processed_key, BUCKET
                output = {
                    "_meta": {
                        "source":          "normalize_burden",
                        "canonical_rows":  len(canonical),
                        "sources_merged":  list(SOURCE_PRIORITY.keys()),
                        "processed_at":    datetime.now(timezone.utc).isoformat(),
                    },
                    "rows": [
                        {
                            **{k: v for k, v in row.items() if k not in ("id", "ingested_at")},
                            "alert_level": classify_alert(
                                incidence_by_country.get(row["iso3"])
                                if row["metric"] == "incidence_per_1000" else None
                            ),
                        }
                        for row in canonical
                    ],
                }
                key = processed_key("burden", "canonical", "all-countries.json")
                put_json(key, output)
                log.info(f"  s3://{BUCKET}/{key}")
            except Exception as e:
                log.warn(f"  S3 write skipped: {e}")

        # Write country-level alert summary
        with log.step("Write country alert summary → S3"):
            try:
                from pipelines.utils.s3 import put_json, processed_key, BUCKET
                country_summary = {}
                for row in canonical:
                    iso3 = row["iso3"]
                    if iso3 not in country_summary:
                        country_summary[iso3] = {"iso3": iso3, "metrics": {}}
                    m = row["metric"]
                    yr = row["year"]
                    if m not in country_summary[iso3]["metrics"] or yr > country_summary[iso3]["metrics"][m].get("year", 0):
                        country_summary[iso3]["metrics"][m] = {
                            "year":  yr,
                            "value": row["value"],
                            "low":   row.get("value_low"),
                            "high":  row.get("value_high"),
                            "src":   row["source_code"],
                        }

                for iso3, cs in country_summary.items():
                    inc = cs["metrics"].get("incidence_per_1000", {}).get("value")
                    cs["alert_level"] = classify_alert(inc)
                    cs["latest_year"] = max(
                        (v["year"] for v in cs["metrics"].values()), default=None
                    )

                key = processed_key("burden", "canonical", "country-summary.json")
                put_json(key, {"countries": list(country_summary.values())})
                log.info(f"  {len(country_summary)} countries summarized → s3://{BUCKET}/{key}")
            except Exception as e:
                log.warn(f"  Summary write skipped: {e}")
    else:
        log.info(f"[DRY RUN] Would process {len(canonical)} canonical burden rows")

    log.finish(records=len(canonical))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
