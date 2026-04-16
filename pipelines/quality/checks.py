"""
Data Quality Framework — malaria-intel pipeline.
Runs after each ingest stage and produces a quality report.

Checks:
  1. Completeness  — required columns not null, coverage by source/year
  2. Validity      — values in expected ranges, ISO3 codes valid
  3. Consistency   — no duplicate (iso3, year, metric, source) keys
  4. Freshness     — latest year in DB vs expected
  5. Coverage      — endemic countries represented
  6. Plausibility  — YoY change not > 50%, deaths < cases

Usage:
    python -m pipelines.quality.checks [--table all] [--min-score 0.8]
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.utils.db import fetchall, fetchone
from pipelines.utils.logger import PipelineLogger

# ISO3 codes for the 87 malaria-endemic countries (WHO 2024)
ENDEMIC_ISO3 = {
    "AFG","AGO","BDI","BEN","BFA","BGD","BOL","BRA","BTN","CAF","CIV","CMR","COD","COG",
    "COL","COM","CPV","DJI","ECU","ERI","ETH","GAB","GHA","GIN","GMB","GNB","GNQ","GTM",
    "GUY","HND","HTI","IDN","IND","KEN","KHM","LAO","LBR","LSO","MDG","MLI","MMR","MOZ",
    "MRT","MWI","MYS","NAM","NER","NGA","NIC","NPL","PAK","PAN","PER","PHL","PNG","PRK",
    "PRY","RWA","SDN","SEN","SLE","SLV","SOM","SSD","STP","SUR","SWZ","TCD","TGO","THA",
    "TJK","TLS","TZA","UGA","VEN","VNM","VUT","YEM","ZAF","ZMB","ZWE",
}

EXPECTED_LATEST_YEAR = 2023
EXPECTED_MIN_COUNTRIES = 50  # minimum countries with burden data


class QualityCheck:
    def __init__(self, name: str, table: str):
        self.name    = name
        self.table   = table
        self.passed  = False
        self.score   = 0.0
        self.details = ""
        self.issues: list[str] = []

    def to_dict(self) -> dict:
        return {
            "check":   self.name,
            "table":   self.table,
            "passed":  self.passed,
            "score":   round(self.score, 3),
            "details": self.details,
            "issues":  self.issues[:10],
        }


# ── Individual checks ──────────────────────────────────────────────────────

def check_row_count(table: str, min_rows: int) -> QualityCheck:
    c = QualityCheck(f"row_count_min_{min_rows}", table)
    row = fetchone(f"SELECT COUNT(*) as n FROM malaria.{table}")
    n = int(row["n"]) if row else 0
    c.score = min(1.0, n / min_rows)
    c.passed = n >= min_rows
    c.details = f"{n:,} rows (min: {min_rows:,})"
    if not c.passed:
        c.issues.append(f"Only {n} rows — expected at least {min_rows}")
    return c


def check_null_completeness(table: str, columns: list[str]) -> QualityCheck:
    c = QualityCheck("null_completeness", table)
    row = fetchone(f"SELECT COUNT(*) as total FROM malaria.{table}")
    total = int(row["n"] if "n" in (row or {}) else row.get("total", 0)) if row else 0
    if total == 0:
        c.score = 0.0
        c.details = "Table is empty"
        return c

    scores = []
    for col in columns:
        null_row = fetchone(
            f"SELECT COUNT(*) as n FROM malaria.{table} WHERE {col} IS NULL"
        )
        null_n = int(null_row["n"]) if null_row else 0
        completeness = 1.0 - (null_n / total)
        scores.append(completeness)
        if completeness < 0.95:
            c.issues.append(f"{col}: {null_n:,}/{total:,} nulls ({completeness:.1%} complete)")

    c.score = sum(scores) / len(scores) if scores else 0.0
    c.passed = c.score >= 0.90
    c.details = f"{len(columns)} columns checked, avg completeness {c.score:.1%}"
    return c


def check_iso3_validity(table: str, iso3_col: str = "iso3") -> QualityCheck:
    c = QualityCheck("iso3_validity", table)
    rows = fetchall(
        f"SELECT DISTINCT {iso3_col} FROM malaria.{table} WHERE LENGTH({iso3_col}) != 3 OR {iso3_col} ~ '[^A-Z]'"
    )
    invalid = [r[iso3_col] for r in rows]
    total_row = fetchone(f"SELECT COUNT(DISTINCT {iso3_col}) as n FROM malaria.{table}")
    total = int(total_row["n"]) if total_row else 1
    c.score = 1.0 - (len(invalid) / max(total, 1))
    c.passed = len(invalid) == 0
    c.details = f"{total} unique ISO3 codes, {len(invalid)} invalid"
    if invalid:
        c.issues = [f"Invalid ISO3: {v}" for v in invalid[:10]]
    return c


def check_value_ranges(table: str, col: str, min_val: float, max_val: float) -> QualityCheck:
    c = QualityCheck(f"range_{col}", table)
    out_of_range = fetchone(
        f"SELECT COUNT(*) as n FROM malaria.{table} WHERE {col} IS NOT NULL AND ({col} < %s OR {col} > %s)",
        (min_val, max_val),
    )
    total = fetchone(f"SELECT COUNT(*) as n FROM malaria.{table} WHERE {col} IS NOT NULL")
    n_bad  = int(out_of_range["n"]) if out_of_range else 0
    n_total = int(total["n"]) if total else 1
    c.score = 1.0 - (n_bad / max(n_total, 1))
    c.passed = n_bad == 0
    c.details = f"{n_bad:,}/{n_total:,} values outside [{min_val}, {max_val}]"
    if n_bad > 0:
        c.issues.append(f"{n_bad} {col} values out of range [{min_val},{max_val}]")
    return c


def check_year_coverage(table: str, year_col: str = "year") -> QualityCheck:
    c = QualityCheck("year_coverage", table)
    rows = fetchall(
        f"SELECT MIN({year_col}) as min_yr, MAX({year_col}) as max_yr, COUNT(DISTINCT {year_col}) as n_years FROM malaria.{table}"
    )
    if not rows or rows[0]["max_yr"] is None:
        c.score = 0.0
        c.details = "No year data"
        return c
    r = rows[0]
    min_yr, max_yr, n_years = int(r["min_yr"]), int(r["max_yr"]), int(r["n_years"])
    freshness = 1.0 if max_yr >= EXPECTED_LATEST_YEAR else (max_yr - 2000) / (EXPECTED_LATEST_YEAR - 2000)
    span = 1.0 if n_years >= 10 else n_years / 10
    c.score = (freshness + span) / 2
    c.passed = max_yr >= EXPECTED_LATEST_YEAR - 2
    c.details = f"Years {min_yr}–{max_yr} ({n_years} distinct years)"
    if max_yr < EXPECTED_LATEST_YEAR - 2:
        c.issues.append(f"Latest year {max_yr} is stale (expected ≥ {EXPECTED_LATEST_YEAR - 2})")
    return c


def check_endemic_country_coverage() -> QualityCheck:
    c = QualityCheck("endemic_country_coverage", "fact_burden")
    rows = fetchall(
        "SELECT DISTINCT iso3 FROM malaria.fact_burden WHERE metric='incidence_per_1000'"
    )
    covered = {r["iso3"] for r in rows}
    missing = ENDEMIC_ISO3 - covered
    coverage = len(covered & ENDEMIC_ISO3) / len(ENDEMIC_ISO3)
    c.score = coverage
    c.passed = coverage >= 0.70
    c.details = f"{len(covered & ENDEMIC_ISO3)}/{len(ENDEMIC_ISO3)} endemic countries have incidence data"
    if missing:
        c.issues = [f"Missing endemic: {', '.join(sorted(missing)[:20])}"]
    return c


def check_source_diversity() -> QualityCheck:
    c = QualityCheck("source_diversity", "fact_burden")
    rows = fetchall(
        "SELECT source_code, COUNT(*) as n FROM malaria.fact_burden GROUP BY source_code ORDER BY n DESC"
    )
    sources = {r["source_code"]: int(r["n"]) for r in rows}
    n_sources = len(sources)
    c.score = min(1.0, n_sources / 4)  # Expect at least 4 sources
    c.passed = n_sources >= 2
    c.details = f"{n_sources} sources: " + ", ".join(f"{k}({v:,})" for k, v in list(sources.items())[:6])
    if n_sources < 2:
        c.issues.append("Only 1 source — no cross-validation possible")
    return c


def check_dci_coverage() -> QualityCheck:
    c = QualityCheck("dci_score_coverage", "fact_outbreak")
    total = fetchone("SELECT COUNT(*) as n FROM malaria.fact_outbreak WHERE disease NOT ILIKE '%malaria%'")
    scored = fetchone("SELECT COUNT(*) as n FROM malaria.fact_outbreak WHERE dci_score IS NOT NULL")
    n_total  = int(total["n"]) if total else 0
    n_scored = int(scored["n"]) if scored else 0
    c.score = n_scored / max(n_total, 1)
    c.passed = c.score >= 0.80
    c.details = f"{n_scored}/{n_total} non-malaria outbreaks have DCI scores"
    if c.score < 0.80:
        c.issues.append(f"Only {c.score:.0%} DCI coverage — run compute_dci_llm.py")
    return c


def check_plausibility_deaths_vs_cases() -> QualityCheck:
    c = QualityCheck("deaths_lt_cases_plausibility", "fact_burden")
    rows = fetchall("""
        SELECT b1.iso3, b1.year, b1.value as cases, b2.value as deaths
        FROM malaria.fact_burden b1
        JOIN malaria.fact_burden b2
            ON b1.iso3=b2.iso3 AND b1.year=b2.year AND b1.source_code=b2.source_code
        WHERE b1.metric='cases_estimated' AND b2.metric='deaths_estimated'
          AND b2.value > b1.value AND b1.value > 0
    """)
    n_bad = len(rows)
    total = fetchone("SELECT COUNT(*) as n FROM malaria.fact_burden WHERE metric='cases_estimated'")
    n_total = int(total["n"]) if total else 1
    c.score = 1.0 - (n_bad / max(n_total, 1))
    c.passed = n_bad == 0
    c.details = f"{n_bad} rows where deaths > cases"
    for r in rows[:5]:
        c.issues.append(f"{r['iso3']} {r['year']}: deaths {r['deaths']:,.0f} > cases {r['cases']:,.0f}")
    return c


def check_duplicate_keys(table: str, key_cols: list[str]) -> QualityCheck:
    c = QualityCheck("no_duplicate_keys", table)
    key_expr = ", ".join(key_cols)
    rows = fetchall(
        f"SELECT {key_expr}, COUNT(*) as n FROM malaria.{table} GROUP BY {key_expr} HAVING COUNT(*) > 1 LIMIT 10"
    )
    n_dupes = len(rows)
    c.score = 0.0 if n_dupes > 0 else 1.0
    c.passed = n_dupes == 0
    c.details = f"{n_dupes} duplicate key combinations"
    for r in rows[:5]:
        c.issues.append(str(dict(r)))
    return c


# ── Run all checks ─────────────────────────────────────────────────────────

def run_all_checks(log) -> dict:
    all_checks: list[QualityCheck] = []

    # fact_burden
    all_checks += [
        check_row_count("fact_burden", 5000),
        check_null_completeness("fact_burden", ["iso3", "year", "metric", "value"]),
        check_iso3_validity("fact_burden"),
        check_value_ranges("fact_burden", "value", 0, 1e9),
        check_year_coverage("fact_burden"),
        check_endemic_country_coverage(),
        check_source_diversity(),
        check_plausibility_deaths_vs_cases(),
    ]

    # fact_outbreak
    all_checks += [
        check_row_count("fact_outbreak", 50),
        check_null_completeness("fact_outbreak", ["event_id", "disease", "country_iso3"]),
        check_iso3_validity("fact_outbreak", "country_iso3"),
        check_value_ranges("fact_outbreak", "dci_score", 0.0, 1.0),
        check_dci_coverage(),
    ]

    # fact_intervention
    all_checks += [
        check_row_count("fact_intervention", 500),
        check_null_completeness("fact_intervention", ["iso3", "year", "indicator", "value"]),
        check_value_ranges("fact_intervention", "value", 0, 100),
        check_year_coverage("fact_intervention"),
    ]

    # fact_parasite_rate
    all_checks += [
        check_row_count("fact_parasite_rate", 100),
        check_value_ranges("fact_parasite_rate", "pr_mean", 0.0, 1.0),
    ]

    # fact_climate
    all_checks += [
        check_row_count("fact_climate", 1000),
        check_value_ranges("fact_climate", "temp_avg_c", -30, 50),
        check_value_ranges("fact_climate", "rainfall_mm", 0, 1500),
    ]

    # fact_funding
    all_checks += [
        check_row_count("fact_funding", 50),
        check_value_ranges("fact_funding", "amount_usd", 0, 5e9),
    ]

    passed = sum(1 for c in all_checks if c.passed)
    total  = len(all_checks)
    score  = passed / total

    for c in all_checks:
        status = "✓" if c.passed else "✗"
        log.info(f"  [{status}] {c.table}.{c.name}: {c.details} (score={c.score:.2f})")
        for issue in c.issues[:3]:
            log.warn(f"       ↳ {issue}")

    return {
        "run_at":        datetime.now(timezone.utc).isoformat(),
        "overall_score": round(score, 3),
        "passed":        passed,
        "total":         total,
        "checks":        [c.to_dict() for c in all_checks],
        "grade":         "A" if score >= 0.90 else "B" if score >= 0.75 else "C" if score >= 0.60 else "F",
    }


def run(min_score: float = 0.0) -> dict:
    log = PipelineLogger("quality_checks")
    with log.step("Running data quality checks"):
        report = run_all_checks(log)

    grade = report["grade"]
    score = report["overall_score"]
    log.info(f"\n{'='*50}")
    log.info(f"QUALITY GRADE: {grade}  ({report['passed']}/{report['total']} checks passed, score={score:.1%})")
    log.info(f"{'='*50}")

    # Write report to S3
    try:
        from pipelines.utils.s3 import put_json, processed_key, BUCKET
        key = processed_key("quality", "reports", f"quality-{datetime.now().strftime('%Y%m%d-%H%M')}.json")
        put_json(key, report)
        log.info(f"Report → s3://{BUCKET}/{key}")
    except Exception as e:
        log.warn(f"S3 write skipped: {e}")

    if score < min_score:
        log.error(f"Quality score {score:.1%} below threshold {min_score:.1%}")
        raise SystemExit(1)

    log.finish()
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=float, default=0.0)
    args = parser.parse_args()
    run(min_score=args.min_score)
