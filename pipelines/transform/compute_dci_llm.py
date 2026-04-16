"""
L1 — Compute DCI scores for all fact_outbreak rows that lack them.
Uses Claude Sonnet via Bedrock for each unscored event.
Also re-scores events where malaria incidence data has been updated.

Usage:
    python -m pipelines.transform.compute_dci_llm [--dry-run] [--rescore-all] [--limit N]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.logger import PipelineLogger
from pipelines.utils.db import fetchall, execute
from pipelines.utils.bedrock import compute_dci


def get_malaria_incidence(iso3: str, incidence_cache: dict[str, float]) -> float:
    """Cached lookup of latest malaria incidence per 1000."""
    if iso3 in incidence_cache:
        return incidence_cache[iso3]
    try:
        from pipelines.utils.db import fetchone
        row = fetchone(
            """SELECT value FROM malaria.fact_burden
               WHERE iso3=%s AND metric='incidence_per_1000'
               ORDER BY year DESC LIMIT 1""",
            (iso3,),
        )
        val = float(row["value"]) if row else 0.0
    except Exception:
        val = 0.0
    incidence_cache[iso3] = val
    return val


def run(dry_run: bool = False, rescore_all: bool = False, limit: int = 500) -> None:
    log = PipelineLogger("compute_dci_llm", dry_run=dry_run)

    # ── Load events needing DCI ────────────────────────────────────────────
    with log.step("Load outbreak events from PostgreSQL"):
        if rescore_all:
            events = fetchall(
                "SELECT * FROM malaria.fact_outbreak "
                "WHERE disease NOT ILIKE '%malaria%' "
                "ORDER BY ingested_at DESC LIMIT %s",
                (limit,),
            )
        else:
            events = fetchall(
                "SELECT * FROM malaria.fact_outbreak "
                "WHERE dci_score IS NULL AND disease NOT ILIKE '%malaria%' "
                "ORDER BY ingested_at DESC LIMIT %s",
                (limit,),
            )
        log.info(f"  {len(events)} events to score")

    if not events:
        log.info("No events need DCI scoring")
        log.finish(records=0)
        return

    # ── Compute DCI via Bedrock Sonnet ─────────────────────────────────────
    incidence_cache: dict[str, float] = {}
    scored = 0
    failed = 0

    with log.step(f"Compute DCI scores ({len(events)} events)"):
        for i, event in enumerate(events):
            iso3 = event.get("country_iso3", "")
            if not iso3:
                continue

            disease = event.get("disease", "Unknown")
            event_type = event.get("event_type", "other")
            severity = float(event.get("severity_score") or 0.3)
            geo_overlap = float(event.get("overlap_with_malaria_zone") or 0.0)

            malaria_inc = get_malaria_incidence(iso3, incidence_cache)

            log.info(f"  [{i+1}/{len(events)}] {iso3} {disease} (inc={malaria_inc:.1f})")

            result = compute_dci(
                country=iso3,
                iso3=iso3,
                malaria_incidence=malaria_inc,
                disease=disease,
                event_type=event_type,
                severity=severity,
                geo_overlap=geo_overlap,
            )

            dci_score = result.get("dci_score")
            reasoning = result.get("reasoning", "")

            if dci_score is None:
                log.warn(f"    DCI computation failed")
                failed += 1
                continue

            log.info(f"    DCI={dci_score:.3f}: {reasoning[:80]}")
            scored += 1

            if not dry_run:
                try:
                    execute(
                        """UPDATE malaria.fact_outbreak
                           SET dci_score = %s, narrative = COALESCE(narrative, '') || ' [DCI: ' || %s || ']'
                           WHERE id = %s""",
                        (dci_score, reasoning[:200], event["id"]),
                    )
                except Exception as e:
                    log.warn(f"    DB update failed: {e}")

    log.info(f"Scored: {scored}, Failed: {failed}")

    # ── DCI distribution summary ───────────────────────────────────────────
    if not dry_run:
        with log.step("Write DCI summary to S3"):
            try:
                from pipelines.utils.s3 import put_json, processed_key, BUCKET
                scored_events = fetchall(
                    "SELECT country_iso3, disease, event_type, dci_score, start_date "
                    "FROM malaria.fact_outbreak WHERE dci_score IS NOT NULL "
                    "ORDER BY dci_score DESC"
                )
                buckets = {"negligible": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
                for e in scored_events:
                    s = e.get("dci_score") or 0
                    if s < 0.2:   buckets["negligible"] += 1
                    elif s < 0.4: buckets["low"] += 1
                    elif s < 0.6: buckets["moderate"] += 1
                    elif s < 0.8: buckets["high"] += 1
                    else:         buckets["critical"] += 1

                summary = {
                    "_meta": {"computed_at": datetime.now(timezone.utc).isoformat()},
                    "total_scored": len(scored_events),
                    "distribution": buckets,
                    "top_events": [
                        {k: v for k, v in e.items() if k != "id"}
                        for e in scored_events[:50]
                    ],
                }
                key = processed_key("outbreaks", "dci", "dci-summary.json")
                put_json(key, summary)
                log.info(f"  s3://{BUCKET}/{key}")
                log.info(f"  DCI dist: {buckets}")
            except Exception as e:
                log.warn(f"  S3 write skipped: {e}")

    log.finish(records=scored)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rescore-all", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    run(dry_run=args.dry_run, rescore_all=args.rescore_all, limit=args.limit)
