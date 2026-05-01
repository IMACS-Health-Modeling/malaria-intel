"""
L0 — IR Mapper insecticide resistance ingest.

Source: IR Mapper (IVCC / Liverpool School of Tropical Medicine)
URL:    https://www.irmapper.com / https://data.irmapper.net/api/v2/

IR Mapper collects WHO tube bioassay and CDC bottle assay results for
Anopheles vector species globally. Covers 60+ countries, 1950–present.

API strategy:
  1. Try the IR Mapper REST API (public endpoint, no auth for read)
  2. Fall back to a paginated CSV export if JSON API unavailable

Output:
  S3: raw/irmapper/dt=YYYY-MM-DD/irmapper-resistance.json
  DB: malaria.fact_insecticide_resistance

Resistance classification (WHO 2016 threshold):
  mortality_pct >= 98%  → susceptible
  90% ≤ mortality < 98% → possible_resistance
  mortality < 90%       → confirmed_resistance

Usage:
    python -m pipelines.ingest.irmapper_resistance [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import boto3
import requests
from pipelines.utils.s3 import put_json, put_meta, raw_key, BUCKET
from pipelines.utils.logger import PipelineLogger

SOURCE_CODE = "irmapper"

FOUNDATION_BUCKET = "imacs-mm-foundation-data-prod"
FOUNDATION_PREFIX = "raw/malaria-intelligence/insecticide_resistance/"

# Files from IR Mapper "Analysis Ready Datasets" (uploaded 2026-04-16)
# File 1 = standard WHO tube test (primary for bioassay mortality %)
# File 3 = CDC bottle bioassay
# Files 6-8 = Vgsc allele frequencies (resistance gene — different table eventually)
WHO_TUBE_KEY = FOUNDATION_PREFIX + "1_standard-WHO-susc-test_complex-subgroup.csv"
CDC_BOTTLE_KEY = FOUNDATION_PREFIX + "3_CDC-bottle-bioassay_complex-subgroup.csv"

# Known insecticide → class mapping
INSECTICIDE_CLASS_MAP = {
    # Pyrethroids
    "permethrin": "pyrethroid", "deltamethrin": "pyrethroid",
    "alpha-cypermethrin": "pyrethroid", "alphacypermethrin": "pyrethroid",
    "lambda-cyhalothrin": "pyrethroid", "lambdacyhalothrin": "pyrethroid",
    "cypermethrin": "pyrethroid", "bifenthrin": "pyrethroid",
    "etofenprox": "pyrethroid",
    # Organochlorines
    "ddt": "organochloride", "dieldrin": "organochloride",
    # Carbamates
    "bendiocarb": "carbamate", "propoxur": "carbamate",
    # Organophosphates
    "malathion": "organophosphate", "fenitrothion": "organophosphate",
    "pirimiphos-methyl": "organophosphate", "chlorpyrifos": "organophosphate",
}

# Species normalisation
SPECIES_MAP = {
    "gambiae": "an_gambiae", "an. gambiae": "an_gambiae",
    "arabiensis": "an_arabiensis", "an. arabiensis": "an_arabiensis",
    "funestus": "an_funestus", "an. funestus": "an_funestus",
    "stephensi": "an_stephensi", "an. stephensi": "an_stephensi",
    "coluzzii": "an_coluzzii", "an. coluzzii": "an_coluzzii",
    "minimus": "an_minimus", "an. minimus": "an_minimus",
    "dirus": "an_dirus", "an. dirus": "an_dirus",
}


def classify_resistance(mortality_pct: float | None) -> str:
    """WHO 2016 criteria for insecticide resistance classification."""
    if mortality_pct is None:
        return "unknown"
    if mortality_pct >= 98.0:
        return "susceptible"
    if mortality_pct >= 90.0:
        return "possible_resistance"
    return "confirmed_resistance"


def normalise_species(raw: str) -> str:
    raw_l = raw.lower().strip()
    for k, v in SPECIES_MAP.items():
        if k in raw_l:
            return v
    # Generic fallback — keep first two words e.g. "An. gambiae s.l." → "an_gambiae"
    parts = raw_l.replace(".", "").replace(",", "").split()
    if len(parts) >= 2:
        return f"an_{parts[1]}"
    return raw_l.replace(" ", "_")[:40]


def normalise_insecticide(raw: str) -> tuple[str, str]:
    """Return (insecticide_slug, insecticide_class)."""
    slug = raw.lower().strip().replace(" ", "_").replace("-", "_")
    for k, v in INSECTICIDE_CLASS_MAP.items():
        if k.replace("-", "_") in slug or slug in k.replace("-", "_"):
            return slug[:60], v
    return slug[:60], "unknown"


def _load_foundation_csv(key: str) -> list[dict]:
    """Read a CSV from the foundation S3 bucket, return list-of-dicts."""
    import io, csv as _csv
    s3 = boto3.client("s3", region_name="us-east-1")
    resp = s3.get_object(Bucket=FOUNDATION_BUCKET, Key=key)
    content = resp["Body"].read().decode("latin-1")
    reader = _csv.DictReader(io.StringIO(content))
    return list(reader)


def normalise_irmapper_row(r: dict, test_method: str = "who_tube") -> dict | None:
    """
    Normalise a raw IR Mapper Analysis Ready Dataset row.
    Columns of interest: Country, Start year, Complex/Subgroup (species),
    Insecticide tested, Insecticide class, Percent mortality, Latitude, Longitude, Site name.
    """
    country = str(r.get("Country") or "").strip()
    if not country:
        return None

    # Map country name → ISO3 using pycountry or a simple lookup
    iso3 = _country_to_iso3(country)
    if not iso3:
        return None

    year_raw = r.get("Start year") or r.get("End year") or r.get("Publication year") or ""
    try:
        year = int(float(str(year_raw).strip()))
    except (ValueError, TypeError):
        return None
    if year < 1950 or year > 2030:
        return None

    species_raw   = str(r.get("Complex/Subgroup") or r.get("Species") or "").strip()
    insect_raw    = str(r.get("Insecticide tested") or r.get("Insecticide") or "unknown").strip()
    ins_class_raw = str(r.get("Insecticide class") or "").strip()
    mortality_raw = str(r.get("Percent mortality") or r.get("% Mortality") or "").strip()
    site_name     = str(r.get("Site name") or r.get("Site name 1") or "").strip()

    try:
        lat = float(str(r.get("Latitude") or r.get("Latitude 1") or "").strip() or "0")
        lng = float(str(r.get("Longitude") or r.get("Longitude 1") or "").strip() or "0")
    except (ValueError, TypeError):
        lat, lng = None, None

    try:
        mortality = float(mortality_raw.replace("%", "").strip())
    except (ValueError, TypeError):
        mortality = None

    insecticide_slug, ins_class = normalise_insecticide(insect_raw)
    if ins_class_raw and ins_class == "unknown":
        ins_class = ins_class_raw.lower().replace(" ", "_")[:40]

    return {
        "iso3":               iso3,
        "year":               year,
        "vector_species":     normalise_species(species_raw) if species_raw else "unknown",
        "insecticide_class":  ins_class,
        "insecticide":        insecticide_slug,
        "test_method":        test_method,
        "mortality_pct":      mortality,
        "resistance_status":  classify_resistance(mortality),
        "sample_size":        None,
        "site_name":          site_name[:200] or None,
        "lat":                lat if lat else None,
        "lng":                lng if lng else None,
        "admin1":             None,
        "data_source":        "irmapper",
        "publication_ref":    str(r.get("Source 1 citation") or "")[:500] or None,
    }


# Hardcoded map covering all 38 countries in IR Mapper Analysis Ready Datasets
# (Africa-focused dataset; extend if new regions added)
_COUNTRY_ISO3_MAP: dict[str, str] = {
    "angola": "AGO", "benin": "BEN", "botswana": "BWA", "burkina faso": "BFA",
    "burundi": "BDI", "cameroon": "CMR", "central african republic": "CAF",
    "chad": "TCD", "congo": "COG", "republic of the congo": "COG",
    "côte d'ivoire": "CIV", "cote d'ivoire": "CIV", "ivory coast": "CIV",
    "democratic republic of the congo": "COD", "drc": "COD", "dr congo": "COD",
    "equatorial guinea": "GNQ", "ethiopia": "ETH", "gabon": "GAB",
    "ghana": "GHA", "guinea": "GIN", "guinea-bissau": "GNB", "guinea bissau": "GNB",
    "kenya": "KEN", "liberia": "LBR", "madagascar": "MDG", "malawi": "MWI",
    "mali": "MLI", "mayotte": "MYT", "mozambique": "MOZ", "namibia": "NAM",
    "niger": "NER", "nigeria": "NGA", "rwanda": "RWA", "senegal": "SEN",
    "south africa": "ZAF", "sudan": "SDN", "south sudan": "SSD",
    "swaziland": "SWZ", "eswatini": "SWZ",
    "tanzania, united republic of": "TZA", "tanzania": "TZA",
    "the gambia": "GMB", "gambia": "GMB",
    "togo": "TGO", "uganda": "UGA", "zambia": "ZMB", "zimbabwe": "ZWE",
    # Additional countries in CDC bottle / other files
    "cameroun": "CMR", "cambodia": "KHM", "india": "IND", "myanmar": "MMR",
    "thailand": "THA", "vietnam": "VNM", "viet nam": "VNM", "laos": "LAO",
    "indonesia": "IDN", "papua new guinea": "PNG", "solomon islands": "SLB",
    "colombia": "COL", "peru": "PER", "ecuador": "ECU", "brazil": "BRA",
}


def _country_to_iso3(name: str) -> str | None:
    # Strip encoding artifacts (latin-1 smart quotes, etc.)
    clean = name.lower().strip().replace("\x92", "'").replace("\x91", "'")
    return _COUNTRY_ISO3_MAP.get(clean)


def fetch_from_foundation_files() -> list[dict]:
    """Load and normalise IR Mapper WHO tube + CDC bottle bioassay files from S3."""
    rows: list[dict] = []

    for key, method in [(WHO_TUBE_KEY, "who_tube"), (CDC_BOTTLE_KEY, "cdc_bottle")]:
        raw = _load_foundation_csv(key)
        for r in raw:
            norm = normalise_irmapper_row(r, test_method=method)
            if norm:
                rows.append(norm)

    return rows


def fetch_gho_irs_coverage() -> list[dict]:
    """
    Fetch IRS (Indoor Residual Spraying) coverage from WHO GHO as a proxy signal
    for where insecticide pressure exists. Not bioassay resistance — but maps coverage.
    Stored as resistance_status='coverage_proxy' for filtering in viz layer.
    """
    result = []
    for indicator, label in WHO_IR_INDICATORS.items():
        try:
            url = f"{WHO_GHO_BASE}/{indicator}?$select=SpatialDim,TimeDim,NumericValue&$top=5000"
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            for r in resp.json().get("value", []):
                iso3 = r.get("SpatialDim", "")
                if len(iso3) != 3:
                    continue
                try:
                    year = int(r.get("TimeDim") or 0)
                    value = float(r.get("NumericValue") or 0)
                except (ValueError, TypeError):
                    continue
                result.append({
                    "iso3":               iso3,
                    "year":               year,
                    "vector_species":     "unknown",
                    "insecticide_class":  "pyrethroid",
                    "insecticide":        label,
                    "test_method":        "coverage_estimate",
                    "mortality_pct":      None,
                    "resistance_status":  "coverage_proxy",
                    "sample_size":        int(value),
                    "site_name":          None,
                    "lat":                None,
                    "lng":                None,
                    "admin1":             None,
                    "data_source":        "who_gho",
                    "publication_ref":    None,
                })
        except Exception:
            continue
    return result


def normalise_api_row(r: dict) -> dict | None:
    """Normalise a raw IR Mapper API row to our schema."""
    iso3 = (
        r.get("iso3") or r.get("country_iso3") or r.get("country_code") or
        r.get("ISO3") or ""
    ).strip().upper()
    if len(iso3) != 3:
        return None

    try:
        year = int(float(str(r.get("year") or r.get("collection_year") or r.get("Year") or 0)))
    except (ValueError, TypeError):
        return None
    if year < 1950 or year > 2030:
        return None

    species_raw   = str(r.get("mosquito_species") or r.get("species") or r.get("vector") or "")
    insect_raw    = str(r.get("insecticide") or r.get("compound") or r.get("chemical") or "unknown")
    method_raw    = str(r.get("test_method") or r.get("assay_type") or r.get("bioassay") or "")
    site_name     = str(r.get("site_name") or r.get("site") or r.get("location") or "")
    admin1        = str(r.get("admin1") or r.get("province") or r.get("state") or "")
    publication   = str(r.get("publication") or r.get("reference") or r.get("source") or "")

    try:
        mortality = float(str(r.get("mortality_pct") or r.get("mortality") or r.get("percent_mortality") or 0))
    except (ValueError, TypeError):
        mortality = None

    try:
        sample = int(float(str(r.get("sample_size") or r.get("n") or r.get("tested") or 0)))
    except (ValueError, TypeError):
        sample = None

    try:
        lat = float(str(r.get("latitude") or r.get("lat") or 0))
        lng = float(str(r.get("longitude") or r.get("lng") or r.get("lon") or 0))
    except (ValueError, TypeError):
        lat, lng = None, None

    insecticide_slug, ins_class = normalise_insecticide(insect_raw)

    return {
        "iso3":               iso3,
        "year":               year,
        "vector_species":     normalise_species(species_raw) if species_raw else "unknown",
        "insecticide_class":  ins_class,
        "insecticide":        insecticide_slug,
        "test_method":        method_raw[:40] or "who_tube",
        "mortality_pct":      mortality,
        "resistance_status":  classify_resistance(mortality),
        "sample_size":        sample,
        "site_name":          site_name[:200] or None,
        "lat":                lat,
        "lng":                lng,
        "admin1":             admin1[:100] or None,
        "data_source":        "irmapper",
        "publication_ref":    publication[:500] or None,
    }


def run(dry_run: bool = False, date: str | None = None) -> None:
    log = PipelineLogger("irmapper_resistance", dry_run=dry_run)

    rows: list[dict] = []

    with log.step("Load IR Mapper Analysis Ready Datasets from foundation S3"):
        rows = fetch_from_foundation_files()
        log.info(f"  {len(rows):,} normalised bioassay records")

    if not rows:
        log.warn("No insecticide resistance data retrieved")
        log.finish(records=0)
        return

    payload = {
        "_meta": {
            "source":       SOURCE_CODE,
            "record_count": len(rows),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        },
        "rows": rows,
    }
    key = raw_key("irmapper", "irmapper-resistance.json", date=date)

    if not dry_run:
        with log.step("Upload raw to S3"):
            put_json(key, payload)
            put_meta(key, payload["_meta"])
            log.info(f"  s3://{BUCKET}/{key}")

        with log.step("Upsert → PostgreSQL fact_insecticide_resistance"):
            try:
                from pipelines.utils.db import upsert_many, filter_valid_iso3
                SQL = """
                    INSERT INTO malaria.fact_insecticide_resistance
                        (iso3, year, source_code, vector_species, insecticide_class,
                         insecticide, test_method, mortality_pct, resistance_status,
                         sample_size, site_name, lat, lng, admin1, data_source,
                         publication_ref, raw_s3_key)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                db_rows = [
                    (r["iso3"], r["year"], SOURCE_CODE, r["vector_species"],
                     r["insecticide_class"], r["insecticide"], r["test_method"],
                     r["mortality_pct"], r["resistance_status"], r["sample_size"],
                     r["site_name"], r["lat"], r["lng"], r["admin1"],
                     r["data_source"], r["publication_ref"], key)
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

    log.finish(records=len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, date=args.date)
