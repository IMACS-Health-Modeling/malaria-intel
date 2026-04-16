"""
L0 — WHO World Malaria Report annex ingest.
PRIMARY: Reads pre-downloaded WMR Excel files from foundation bucket:
  imacs-mm-foundation-data-prod/raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4h.xlsx
  imacs-mm-foundation-data-prod/raw/malaria-intelligence/who_wmr2025/wmr2025_annex_4h.xlsx

FALLBACK: CDN download if foundation file missing.

Parses annex 4h (gold-standard burden estimates, cases/deaths 2000–present)
plus other annexes for interventions, drug resistance, etc.

Usage:
    python -m pipelines.ingest.wmr_annexes [--dry-run] [--year 2024]
"""

import argparse
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import openpyxl
import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"

# Foundation bucket paths — exact keys confirmed by S3 audit
FOUNDATION_ANNEXES = {
    2024: {
        "4h": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4f.xlsx",  # 4F = all-years burden estimates
        "4a": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4a.xlsx",
        "4b": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4b.xlsx",
        "4c": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4c.xlsx",
        "4d": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4d.xlsx",
        "4f": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4f.xlsx",
        "4g": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4g.xlsx",
        "4i": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4i.xlsx",
        "4j": "raw/malaria-intelligence/who_wmr2024/wmr2024_annex_4j.xlsx",
    },
    2025: {
        "4h": "raw/malaria-intelligence/who_wmr2025/wmr2025_annex_4h.xlsx",
        "4d": "raw/malaria-intelligence/who_wmr2025/wmr2025_annex_4d.xlsx",
        "4f": "raw/malaria-intelligence/who_wmr2025/wmr2025_annex_4f.xlsx",
        "4g": "raw/malaria-intelligence/who_wmr2025/wmr2025_annex_4g.xlsx",
    },
}

# CDN fallback URLs
CDN_FALLBACK = {
    2024: "https://cdn.who.int/media/docs/default-source/malaria/world-malaria-reports/wmr-2024-annexes.xlsx",
    2025: "https://cdn.who.int/media/docs/default-source/malaria/world-malaria-reports/wmr-2025-annexes.xlsx",
    2023: "https://cdn.who.int/media/docs/default-source/malaria/world-malaria-reports/wmr-2023-annexes.xlsx",
    2022: "https://cdn.who.int/media/docs/default-source/malaria/world-malaria-reports/wmr-2022-annexes.xlsx",
}

SOURCE_CODE_MAP = {2025: "wmr_2025", 2024: "wmr_2024", 2023: "wmr_2023", 2022: "wmr_2022"}
DISEASE_CODE = "malaria"

_s3 = boto3.client("s3", region_name="us-east-1")


def load_foundation_xlsx(s3_key: str) -> openpyxl.Workbook | None:
    try:
        resp = _s3.get_object(Bucket=FOUNDATION_BUCKET, Key=s3_key)
        return openpyxl.load_workbook(io.BytesIO(resp["Body"].read()), data_only=True)
    except Exception:
        return None


def load_cdn_xlsx(wmr_year: int) -> openpyxl.Workbook | None:
    url = CDN_FALLBACK.get(wmr_year)
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=120, headers={"User-Agent": "malaria-intel-pipeline/1.0"})
        resp.raise_for_status()
        return openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
    except Exception:
        return None


# Country name → ISO3 for WMR wide-format sheets (names stripped of superscripts)
_WMR_COUNTRY_ISO3: dict[str, str] = {
    "afghanistan":"AFG","algeria":"DZA","angola":"AGO","argentina":"ARG",
    "azerbaijan":"AZE","bangladesh":"BGD","belize":"BLZ","benin":"BEN",
    "bhutan":"BTN","bolivia":"BOL","botswana":"BWA","brazil":"BRA",
    "burkina faso":"BFA","burundi":"BDI","cabo verde":"CPV","cambodia":"KHM",
    "cameroon":"CMR","central african republic":"CAF","chad":"TCD","china":"CHN",
    "colombia":"COL","comoros":"COM","congo":"COG","costa rica":"CRI",
    "côte d'ivoire":"CIV","cote d'ivoire":"CIV","djibouti":"DJI",
    "democratic republic of the congo":"COD","dominican republic":"DOM",
    "ecuador":"ECU","el salvador":"SLV","equatorial guinea":"GNQ",
    "eritrea":"ERI","eswatini":"SWZ","ethiopia":"ETH","gabon":"GAB",
    "gambia":"GMB","ghana":"GHA","guatemala":"GTM","guinea":"GIN",
    "guinea-bissau":"GNB","guyana":"GUY","haiti":"HTI","honduras":"HND",
    "india":"IND","indonesia":"IDN","iran":"IRN","kenya":"KEN",
    "lao pdr":"LAO","laos":"LAO","lesotho":"LSO","liberia":"LBR",
    "madagascar":"MDG","malawi":"MWI","malaysia":"MYS","mali":"MLI",
    "mauritania":"MRT","mexico":"MEX","mozambique":"MOZ","myanmar":"MMR",
    "namibia":"NAM","nepal":"NPL","nicaragua":"NIC","niger":"NER",
    "nigeria":"NGA","pakistan":"PAK","panama":"PAN","papua new guinea":"PNG",
    "paraguay":"PRY","peru":"PER","philippines":"PHL","republic of korea":"KOR",
    "rwanda":"RWA","sao tome and principe":"STP","senegal":"SEN",
    "sierra leone":"SLE","solomon islands":"SLB","somalia":"SOM",
    "south africa":"ZAF","south sudan":"SSD","sri lanka":"LKA","sudan":"SDN",
    "suriname":"SUR","tajikistan":"TJK","thailand":"THA","timor-leste":"TLS",
    "togo":"TGO","trinidad and tobago":"TTO","uganda":"UGA",
    "united republic of tanzania":"TZA","tanzania":"TZA",
    "vanuatu":"VUT","venezuela":"VEN","viet nam":"VNM","vietnam":"VNM",
    "yemen":"YEM","zambia":"ZMB","zimbabwe":"ZWE",
    "democratic people's republic of korea":"PRK","dpr korea":"PRK",
    "equatorial guinea":"GNQ","swaziland":"SWZ",
}

# WHO region headers to skip when parsing wide-format sheets
_REGION_NAMES = {
    "african","americas","eastern mediterranean","european",
    "south-east asia","western pacific","global",
    "african region","region of the americas","emro","searo","wpro","amro","afro","euro",
}


def _strip_superscripts(name: str) -> str:
    """Remove trailing footnote markers from country names like 'Algeria1,2,3' or 'Mali*'."""
    import re
    # Only strip trailing digits, commas, and punctuation — NOT letters (would corrupt names)
    return re.sub(r'[\d,.*†‡§¶#]+$', '', name.strip()).strip()


def _name_to_iso3(name: str) -> str | None:
    cleaned = _strip_superscripts(name).lower()
    return _WMR_COUNTRY_ISO3.get(cleaned)


def _num(v) -> float | None:
    if v is None: return None
    s = str(v).replace(",", "").replace("–", "").replace("-", "").strip()
    if not s: return None
    try: return float(s)
    except: return None


def parse_long_format(ws) -> list[dict]:
    """
    Parse WMR Long_Format sheet: region, iso, country, year, indicator, value.
    Used by WMR 2025 and later editions.
    """
    rows_out: list[dict] = []
    header_row: list[str] = []
    for row in ws.iter_rows(values_only=True):
        if not any(row):
            continue
        if not header_row:
            row_lower = [str(c).lower().strip() if c else "" for c in row]
            if "iso" in row_lower and "year" in row_lower and "indicator" in row_lower:
                header_row = row_lower
                iso_idx  = header_row.index("iso")
                year_idx = header_row.index("year")
                ind_idx  = header_row.index("indicator")
                val_idx  = header_row.index("value")
            continue

        iso3 = str(row[iso_idx] or "").strip().upper()
        if len(iso3) != 3:
            continue
        try:
            year = int(row[year_idx])
        except (TypeError, ValueError):
            continue
        indicator = str(row[ind_idx] or "").strip().lower()
        value = _num(row[val_idx])
        if value is None:
            continue

        # Map indicator text to our metric fields
        rec = {"iso3": iso3, "year": year}
        if "cases lower" in indicator:
            rec["cases_low"] = value
        elif "cases upper" in indicator:
            rec["cases_high"] = value
        elif "cases point" in indicator or indicator == "cases":
            rec["cases_est"] = value
        elif "deaths lower" in indicator:
            rec["deaths_low"] = value
        elif "deaths upper" in indicator:
            rec["deaths_high"] = value
        elif "deaths point" in indicator or indicator == "deaths":
            rec["deaths_est"] = value
        else:
            continue
        rows_out.append(rec)

    # Collapse per (iso3, year) — multiple rows per country-year
    from collections import defaultdict
    collapsed: dict[tuple, dict] = defaultdict(dict)
    for rec in rows_out:
        key = (rec["iso3"], rec["year"])
        collapsed[key].update(rec)

    return list(collapsed.values())


def parse_annex_wide(ws) -> list[dict]:
    """
    Parse WMR wide-format burden sheet where:
      col 0 = Country name (carried forward, with superscripts)
      col 1 = Year
      col 2 = Population at risk
      col 3 = Cases lower
      col 4 = Cases point  ← gold-standard
      col 5 = Cases upper
      col 6 = Deaths lower
      col 7 = Deaths point
      col 8 = Deaths upper
    Used by WMR 2024 Annex 4F and WMR 2025 ANNEX_H.
    """
    rows_out: list[dict] = []
    current_iso3 = None
    data_started = False

    for row in ws.iter_rows(values_only=True):
        if not any(row):
            continue

        col0 = str(row[0]).strip() if row[0] else ""
        col1 = row[1]

        # Detect start of data: col1 is a year integer ~2000
        if not data_started:
            try:
                y = int(float(str(col1))) if col1 else 0
                if 1990 <= y <= 2030:
                    data_started = True
            except (ValueError, TypeError):
                pass

        if not data_started:
            # Still in header — try to capture country name if present
            if col0 and col0.upper() not in [r.upper() for r in _REGION_NAMES]:
                iso3 = _name_to_iso3(col0)
                if iso3:
                    current_iso3 = iso3
            continue

        # New country row (col0 is non-empty and not a region header)
        if col0:
            col0_clean = col0.strip()
            col0_up = col0_clean.upper()
            if col0_up in {r.upper() for r in _REGION_NAMES}:
                current_iso3 = None
                continue
            iso3 = _name_to_iso3(col0_clean)
            if iso3:
                current_iso3 = iso3
            else:
                current_iso3 = None

        if not current_iso3:
            continue

        try:
            year = int(float(str(col1)))
        except (TypeError, ValueError):
            continue
        if not (1990 <= year <= 2030):
            continue

        rows_out.append({
            "iso3":       current_iso3,
            "year":       year,
            "cases_low":  _num(row[3] if len(row) > 3 else None),
            "cases_est":  _num(row[4] if len(row) > 4 else None),
            "cases_high": _num(row[5] if len(row) > 5 else None),
            "deaths_low": _num(row[6] if len(row) > 6 else None),
            "deaths_est": _num(row[7] if len(row) > 7 else None),
            "deaths_high":_num(row[8] if len(row) > 8 else None),
        })

    return rows_out


def process_wmr_year(wmr_year: int, log, dry_run: bool, date: str | None) -> list[tuple]:
    """Load annex 4h for a WMR year. Returns list of (row_dict, source_code)."""
    source_code = SOURCE_CODE_MAP.get(wmr_year, f"wmr_{wmr_year}")
    log.info(f"  WMR {wmr_year}")

    # Try foundation bucket first
    wb = None
    foundation_keys = FOUNDATION_ANNEXES.get(wmr_year, {})
    if "4h" in foundation_keys:
        log.info(f"    Loading from foundation: {foundation_keys['4h']}")
        wb = load_foundation_xlsx(foundation_keys["4h"])

    if wb is None:
        log.warn(f"    Foundation missing, falling back to CDN")
        wb = load_cdn_xlsx(wmr_year)

    if wb is None:
        log.warn(f"    Could not load WMR {wmr_year}")
        return []

    # Pick best available sheet — prefer Long_Format (has ISO3), fall back to wide format
    sheet_names_lower = {n.lower(): n for n in wb.sheetnames}
    rows: list[dict] = []

    if "long_format" in sheet_names_lower:
        ws = wb[sheet_names_lower["long_format"]]
        log.info(f"    Using Long_Format sheet")
        rows = parse_long_format(ws)
    else:
        # Try 4F (all-years burden) then 4H then active sheet
        preferred = ["annex4f_allyears", "annex_4f", "4f", "annex_4h", "annex4h", "4h"]
        ws = None
        for p in preferred:
            if p in sheet_names_lower:
                ws = wb[sheet_names_lower[p]]
                break
        if ws is None:
            ws = wb.active
        if ws is None:
            log.warn(f"    No suitable sheet found. Sheets: {wb.sheetnames}")
            return []
        log.info(f"    Using wide-format sheet '{ws.title}'")
        rows = parse_annex_wide(ws)

    log.info(f"    Parsed {len(rows)} country-year rows from sheet '{ws.title}'")

    if not dry_run and rows:
        payload = {
            "_meta": {
                "source": source_code, "wmr_year": wmr_year, "sheet": ws.title,
                "record_count": len(rows), "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            "rows": rows,
        }
        key = raw_key(f"wmr-{wmr_year}", "annex4h-burden.json", date=date)
        put_json(key, payload)
        put_meta(key, payload["_meta"])
        log.info(f"    → s3://{BUCKET}/{key}")

    return [(row, source_code) for row in rows]


def run(dry_run: bool = False, date: str | None = None, years: list[int] | None = None) -> None:
    log = PipelineLogger("wmr_annexes", dry_run=dry_run)
    target_years = years or [2025, 2024, 2023, 2022]

    all_tuples: list[tuple] = []
    with log.step(f"Process WMR annexes: {target_years}"):
        for yr in target_years:
            result = process_wmr_year(yr, log, dry_run, date)
            all_tuples.extend(result)

    log.info(f"Total country-year rows: {len(all_tuples)}")

    if not dry_run and all_tuples:
        with log.step("Upsert WMR burden → PostgreSQL"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_burden
                        (iso3, disease_code, year, source_code, metric, value, value_low, value_high, is_modeled)
                    VALUES %s
                    ON CONFLICT (iso3, disease_code, year, source_code, metric, age_group, sex)
                    DO UPDATE SET value=EXCLUDED.value, value_low=EXCLUDED.value_low,
                                  value_high=EXCLUDED.value_high, ingested_at=NOW()
                """
                db_rows = []
                for row, src in all_tuples:
                    if row.get("cases_est") is not None:
                        db_rows.append((row["iso3"], DISEASE_CODE, row["year"], src,
                                        "cases_estimated", row["cases_est"],
                                        row.get("cases_low"), row.get("cases_high"), True))
                    if row.get("deaths_est") is not None:
                        db_rows.append((row["iso3"], DISEASE_CODE, row["year"], src,
                                        "deaths_estimated", row["deaths_est"],
                                        row.get("deaths_low"), row.get("deaths_high"), True))
                db_rows, skipped = filter_valid_iso3(db_rows, iso3_col=0)
                if skipped:
                    log.info(f"  Skipped {skipped} rows (ISO3 not in dim_country)")
                inserted = upsert_many(SQL, db_rows)
                log.info(f"  Upserted {inserted} rows")
            except Exception as e:
                log.warn(f"  DB skipped: {e}")

    log.finish(records=len(all_tuples))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date, years=[args.year] if args.year else None)
