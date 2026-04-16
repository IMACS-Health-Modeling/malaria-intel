"""
L0 — WHO Disease Outbreak News (DON) ingest.
PRIMARY: Reads pre-scraped CSV from foundation bucket:
  raw/health/disease-surveillance/outbreak-events/dons_unique_latest.csv   (1.6MB, unique events)
  raw/health/disease-surveillance/outbreak-events/dons_all_latest.csv      (6MB, all DON pages)
  raw/health/disease-burden/who-don/global-pandemic-and-epidemic-outbreaks.xlsx (426KB)

Format of dons_unique_latest.csv:
  Country, iso2, iso3, Year, icd10n, icd103n, Disease, DONs, Definition

FALLBACK: Live WHO DON CMS API if foundation files are missing or stale.

After loading, uses Bedrock Haiku to enrich with severity/geo_overlap scores,
then computes DCI scores via Bedrock Sonnet.

Usage:
    python -m pipelines.ingest.who_don [--dry-run] [--max 500] [--date YYYY-MM-DD] [--live]
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger
from pipelines.utils.bedrock import extract_disease_event, compute_dci, HAIKU_MODEL

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

# Confirmed foundation paths
FOUNDATION_PATHS = {
    "dons_unique": "raw/health/disease-surveillance/outbreak-events/dons_unique_latest.csv",
    "dons_all":    "raw/health/disease-surveillance/outbreak-events/dons_all_latest.csv",
    "outbreaks":   "raw/health/disease-surveillance/outbreak-events/outbreaks_latest.csv",
    "don_xlsx":    "raw/health/disease-burden/who-don/global-pandemic-and-epidemic-outbreaks.xlsx",
}

# ICD10 / disease keyword → event_type mapping
DISEASE_EVENT_TYPE = {
    "dengue": "arbovirus", "zika": "arbovirus", "chikungunya": "arbovirus",
    "yellow fever": "arbovirus", "rift valley": "arbovirus",
    "ebola": "hemorrhagic", "marburg": "hemorrhagic", "lassa": "hemorrhagic",
    "cholera": "bacterial", "plague": "bacterial", "meningitis": "bacterial",
    "typhoid": "bacterial",
    "mers": "respiratory", "influenza": "respiratory", "novel flu": "respiratory",
    "mpox": "viral", "monkeypox": "viral",
    "conflict": "conflict",
    "malaria": "parasitic", "leishmaniasis": "parasitic",
}

DON_API = "https://www.who.int/api/hubs/disease-outbreak-news"
SOURCE = "who_don"

_s3 = boto3.client("s3", region_name="us-east-1")
_malaria_cache: dict[str, float] = {}


def classify_event_type(disease: str) -> str:
    d = disease.lower()
    for keyword, etype in DISEASE_EVENT_TYPE.items():
        if keyword in d:
            return etype
    return "other"


def get_malaria_incidence(iso3: str) -> float:
    if iso3 in _malaria_cache:
        return _malaria_cache[iso3]
    try:
        from pipelines.utils.db import fetchone
        row = fetchone(
            "SELECT value FROM malaria.fact_burden WHERE iso3=%s AND metric='incidence_per_1000' ORDER BY year DESC LIMIT 1",
            (iso3,),
        )
        val = float(row["value"]) if row else 0.0
    except Exception:
        val = 0.0
    _malaria_cache[iso3] = val
    return val


def load_foundation_csv(path_key: str) -> list[dict]:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=path_key)
        content = resp["Body"].read().decode("utf-8", errors="replace")
        return list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []


def normalize_don_row(row: dict) -> dict | None:
    """
    Normalize a row from dons_unique_latest.csv.
    Columns: Country, iso2, iso3, Year, icd10n, icd103n, icd104n, icd10c, ...
             Disease, DONs, Definition
    """
    iso3    = (row.get("iso3") or row.get("ISO3") or "").strip().upper()
    country = (row.get("Country") or row.get("country") or "").strip()
    year    = (row.get("Year") or row.get("year") or "")
    disease = (row.get("Disease") or row.get("disease") or row.get("icd103n") or "").strip()
    don_ref = (row.get("DONs") or row.get("don_id") or "").strip()
    defn    = (row.get("Definition") or row.get("definition") or "").strip()

    if not iso3 or len(iso3) != 3:
        return None
    if not disease:
        return None

    try:
        year_int = int(float(str(year)))
    except (ValueError, TypeError):
        year_int = None

    event_id = f"who_don:{don_ref}" if don_ref else f"who_don:{hashlib.md5((iso3+disease+str(year)).encode()).hexdigest()[:12]}"

    return {
        "event_id":    event_id,
        "source":      SOURCE,
        "disease":     disease,
        "event_type":  classify_event_type(disease),
        "country_iso3": iso3,
        "country":     country,
        "start_date":  f"{year_int}-01-01" if year_int else None,
        "narrative":   defn[:500] if defn else "",
        "source_url":  "",
        "don_ref":     don_ref,
    }


def enrich_with_bedrock(events: list[dict], log) -> list[dict]:
    """Add severity, geo_overlap, and DCI scores to events using Bedrock."""
    enriched = []
    for i, ev in enumerate(events):
        disease    = ev.get("disease", "")
        iso3       = ev.get("country_iso3", "")
        event_type = ev.get("event_type", "other")
        narrative  = ev.get("narrative", "")

        # Skip malaria events for DCI (no self-confusion)
        if "malaria" in disease.lower():
            ev["severity_score"] = 0.2
            ev["overlap_with_malaria_zone"] = 1.0
            ev["dci_score"] = None
            enriched.append(ev)
            continue

        # Use Haiku to extract severity + geo_overlap if we have narrative text
        severity   = 0.3
        geo_overlap = 0.0

        if narrative and len(narrative) > 50:
            extracted = extract_disease_event(f"{disease} in {ev.get('country', iso3)}\n{narrative}")
            if extracted:
                severity    = float(extracted.get("severity", 0.3) or 0.3)
                geo_overlap = float(extracted.get("overlap_with_malaria_zone", 0.0) or 0.0)

        # DCI via Sonnet
        malaria_inc = get_malaria_incidence(iso3)
        dci_result = compute_dci(
            country=ev.get("country", iso3),
            iso3=iso3,
            malaria_incidence=malaria_inc,
            disease=disease,
            event_type=event_type,
            severity=severity,
            geo_overlap=geo_overlap,
        )

        ev["severity_score"]              = severity
        ev["overlap_with_malaria_zone"]   = geo_overlap
        ev["dci_score"]                   = dci_result.get("dci_score")
        ev["dci_reasoning"]               = dci_result.get("reasoning", "")
        enriched.append(ev)

        if (i + 1) % 20 == 0:
            log.info(f"  Enriched {i+1}/{len(events)}")

    return enriched


def fetch_live_don_api(max_items: int = 200) -> list[dict]:
    """Fallback: scrape WHO DON CMS API."""
    items = []
    offset = 0
    while len(items) < max_items:
        try:
            params = {
                "$orderby": "PublicationDateAndTime desc",
                "$skip": offset, "$top": 20,
                "$count": "true", "sf_culture": "en",
            }
            resp = requests.get(DON_API, params=params, timeout=60,
                                headers={"Accept": "application/json"})
            resp.raise_for_status()
            page = resp.json()
            batch = page.get("value", [])
            if not batch:
                break
            items.extend(batch)
            total = page.get("@odata.count", 0)
            if len(items) >= min(total, max_items):
                break
            offset += 20
        except Exception:
            break
    return items


def run(dry_run: bool = False, max_items: int = 500, date: str | None = None, live: bool = False) -> None:
    log = PipelineLogger("who_don", dry_run=dry_run)
    raw_events: list[dict] = []

    # ── Primary: foundation CSV ────────────────────────────────────────────
    with log.step("Load DON events from foundation bucket"):
        # Try dons_unique (de-duplicated, smaller)
        rows = load_foundation_csv(FOUNDATION_PATHS["dons_unique"])
        if rows:
            log.info(f"  dons_unique_latest.csv: {len(rows)} rows")
            for row in rows:
                ev = normalize_don_row(row)
                if ev:
                    raw_events.append(ev)
        else:
            # Fall back to full dons_all
            rows = load_foundation_csv(FOUNDATION_PATHS["dons_all"])
            log.info(f"  dons_all_latest.csv: {len(rows)} rows")
            seen_ids = set()
            for row in rows:
                ev = normalize_don_row(row)
                if ev and ev["event_id"] not in seen_ids:
                    seen_ids.add(ev["event_id"])
                    raw_events.append(ev)

        log.info(f"  Normalized events: {len(raw_events)}")

    # ── Also load outbreaks_latest.csv (broader event set) ────────────────
    with log.step("Load outbreaks_latest.csv"):
        outbreak_rows = load_foundation_csv(FOUNDATION_PATHS["outbreaks"])
        if outbreak_rows:
            log.info(f"  outbreaks_latest.csv: {len(outbreak_rows)} rows")
            existing_ids = {e["event_id"] for e in raw_events}
            for row in outbreak_rows:
                ev = normalize_don_row(row)
                if ev and ev["event_id"] not in existing_ids:
                    existing_ids.add(ev["event_id"])
                    raw_events.append(ev)
            log.info(f"  Total after merge: {len(raw_events)}")

    # ── Fallback: live API ─────────────────────────────────────────────────
    if live or not raw_events:
        with log.step("Fetch live WHO DON API"):
            api_items = fetch_live_don_api(max_items)
            log.info(f"  Live API items: {len(api_items)}")
            existing_refs = {e.get("don_ref") for e in raw_events}
            for item in api_items:
                url_slug = item.get("ItemDefaultUrl", "").strip("/").split("/")[-1]
                if url_slug in existing_refs:
                    continue
                title   = item.get("Title", "")
                summary = item.get("Summary") or item.get("ShortText") or ""
                body    = item.get("ItemContent") or summary
                text    = f"{title}\n\n{body[:3000]}"
                extracted = extract_disease_event(text)
                if not extracted or not extracted.get("country_iso3"):
                    continue
                ev = {
                    "event_id":    f"who_don:{url_slug or hashlib.md5(title.encode()).hexdigest()[:12]}",
                    "source":      SOURCE,
                    "disease":     extracted.get("disease", "Unknown"),
                    "event_type":  extracted.get("event_type", "other"),
                    "country_iso3": extracted.get("country_iso3", ""),
                    "country":     extracted.get("country", ""),
                    "start_date":  extracted.get("start_date") or item.get("PublicationDateAndTime", "")[:10],
                    "cases_reported": extracted.get("cases_reported"),
                    "deaths_reported": extracted.get("deaths_reported"),
                    "narrative":   extracted.get("narrative", summary[:400]),
                    "source_url":  f"https://www.who.int{item.get('ItemDefaultUrl', '')}",
                    "don_ref":     url_slug,
                }
                raw_events.append(ev)

    # Cap at max_items
    raw_events = raw_events[:max_items]
    log.info(f"Events before enrichment: {len(raw_events)}")

    # ── Bedrock enrichment (DRY RUN skips Bedrock calls) ──────────────────
    if not dry_run:
        with log.step("Enrich with Bedrock (severity + DCI)"):
            events = enrich_with_bedrock(raw_events, log)
    else:
        events = raw_events
        log.info("[DRY RUN] Skipping Bedrock enrichment")

    log.info(f"Final events: {len(events)}")

    # ── S3 raw ─────────────────────────────────────────────────────────────
    payload = {
        "_meta": {"source": SOURCE, "record_count": len(events),
                  "fetched_at": datetime.now(timezone.utc).isoformat()},
        "events": events,
    }
    key = raw_key("who-don", "events.json", date=date)

    if not dry_run:
        with log.step("Upload to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
        log.info(f"s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_outbreak"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_outbreak (
                        event_id, source, disease, event_type, country_iso3,
                        start_date, cases_reported, deaths_reported,
                        severity_score, overlap_with_malaria_zone,
                        dci_score, narrative, source_url, extracted_by
                    ) VALUES %s
                    ON CONFLICT (event_id) DO UPDATE SET
                        dci_score      = EXCLUDED.dci_score,
                        severity_score = EXCLUDED.severity_score,
                        ingested_at    = NOW()
                """
                db_rows = [
                    (
                        e["event_id"], SOURCE, e.get("disease", ""), e.get("event_type", "other"),
                        e.get("country_iso3", ""),
                        e.get("start_date") or None,
                        e.get("cases_reported"), e.get("deaths_reported"),
                        e.get("severity_score", 0.3), e.get("overlap_with_malaria_zone", 0.0),
                        e.get("dci_score"), (e.get("narrative") or "")[:2000],
                        e.get("source_url", ""), "bedrock-haiku-4-5",
                    )
                    for e in events if e.get("country_iso3")
                ]
                # Deduplicate by event_id (index 0) to avoid ON CONFLICT batch errors
                seen_ids: set = set()
                deduped_rows = []
                for row in db_rows:
                    if row[0] not in seen_ids:
                        seen_ids.add(row[0])
                        deduped_rows.append(row)
                if len(deduped_rows) < len(db_rows):
                    log.info(f"  Deduped {len(db_rows) - len(deduped_rows)} duplicate event_ids")
                db_rows = deduped_rows
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=4)
                if skipped:
                    log.info(f"  Skipped {skipped} outbreak rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} outbreak rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")
    else:
        log.info(f"[DRY RUN] Would write {len(events)} events to s3://{BUCKET}/{key}")

    log.finish(records=len(events))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max", type=int, default=500)
    parser.add_argument("--date", default=None)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run, max_items=args.max, date=args.date, live=args.live)
