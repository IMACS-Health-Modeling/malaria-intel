"""
Pipeline orchestrator — runs L0 → L1 → L2 in sequence.

Usage:
    python pipelines/run_all.py [--dry-run] [--skip-ingest] [--skip-transform]
    python pipelines/run_all.py --chapter command   # only command-page pipeline
    python pipelines/run_all.py --chapter us        # only US-facing pipeline

Env vars required:
    MALARIA_INTEL_BUCKET  (default: cdah-malaria-intel-dev)
    DATABASE_URL          (default: postgresql://postgres:postgres@localhost:5432/malaria_intel)
    AWS_PROFILE or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
"""

import argparse
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipelines.utils.logger import PipelineLogger

# Module → dim_source.code mapping for last_fetched tracking
MODULE_SOURCE_MAP: dict[str, str] = {
    "pipelines.ingest.who_gho_full":           "who_gho",
    "pipelines.ingest.wmr_annexes":            "wmr_2025",
    "pipelines.ingest.who_don":                "who_don",
    "pipelines.ingest.global_fund_full":       "global_fund_v4",
    "pipelines.ingest.paho_plisa":             "paho_plisa",
    "pipelines.ingest.cdc_mmwr_malaria":       "cdc_mmwr",
    "pipelines.ingest.map_data":               "map_project",
    "pipelines.ingest.drug_resistance_ingest": "wmr_2024",
    "pipelines.ingest.nasa_power_climate":     "nasa_power",
    "pipelines.ingest.dhs_malaria":            "dhs",
    "pipelines.ingest.worldbank_malaria":      "worldbank",
    "pipelines.ingest.nih_reporter":           "nih_reporter",
    "pipelines.ingest.usaspending_geography":  "usaspending",
}


def _update_last_fetched(module_path: str) -> None:
    """Mark dim_source.last_fetched = NOW() for the source tied to this module."""
    source_code = MODULE_SOURCE_MAP.get(module_path)
    if not source_code:
        return
    try:
        import psycopg2
        import os
        db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/malaria_intel")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("UPDATE malaria.dim_source SET last_fetched=NOW() WHERE code=%s", (source_code,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass  # Non-critical — don't fail the pipeline


# ── Global disease / command-page pipeline ────────────────────────────────
L0_GLOBAL = [
    "pipelines.ingest.who_gho_full",        # All countries, 35 malaria indicators
    "pipelines.ingest.wmr_annexes",          # WMR Excel annexes 2022-2025 (gold standard)
    "pipelines.ingest.who_don",              # WHO DON + Bedrock NLP + DCI
    "pipelines.ingest.global_fund_full",     # Global Fund grants + financials
    "pipelines.ingest.paho_plisa",           # PAHO Americas malaria
    "pipelines.ingest.cdc_mmwr_malaria",     # CDC MMWR US malaria surveillance
    "pipelines.ingest.map_data",             # MAP Pf/Pv parasite rates
    "pipelines.ingest.drug_resistance_ingest", # WMR drug resistance
    "pipelines.ingest.nasa_power_climate",   # NASA POWER monthly climate
    "pipelines.ingest.dhs_malaria",          # DHS household surveys (RDT prevalence, ITN use)
    "pipelines.ingest.worldbank_malaria",    # World Bank malaria indicators (all countries)
]

L1_GLOBAL = [
    "pipelines.transform.normalize_burden",  # Dedup + canonical burden from all sources
    "pipelines.transform.compute_dci_llm",   # DCI scores for unscored outbreaks
]

L2_GLOBAL = [
    "pipelines.serve.build_command_data",    # Command page JSON
]

# ── US-facing pipeline (existing) ─────────────────────────────────────────
L0_US = [
    "pipelines.ingest.nih_reporter",
    "pipelines.ingest.usaspending_geography",
    "pipelines.ingest.clinicaltrials",
    "pipelines.ingest.foreign_assistance",
    "pipelines.ingest.who_rbm",
]

L1_US = [
    "pipelines.transform.aggregate_us_states",
    "pipelines.transform.compute_financial_flows",
]

L2_US = [
    "pipelines.serve.build_all_chapters",
]

# Combined (default)
L0_MODULES = L0_GLOBAL + L0_US
L1_MODULES = L1_GLOBAL + L1_US
L2_MODULES = L2_GLOBAL + L2_US


def run_module(module_path: str, dry_run: bool) -> bool:
    """Import and run a pipeline module. Returns True on success."""
    try:
        mod = importlib.import_module(module_path)
        mod.run(dry_run=dry_run)
        if not dry_run:
            _update_last_fetched(module_path)
        return True
    except Exception as e:
        print(f"  ✗ {module_path} failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Malaria Intel pipeline orchestrator")
    parser.add_argument("--dry-run",        action="store_true", help="Fetch + validate but don't write to S3/DB")
    parser.add_argument("--skip-ingest",    action="store_true", help="Skip L0 ingest (use existing raw data)")
    parser.add_argument("--skip-transform", action="store_true", help="Skip L1 transform")
    parser.add_argument("--only-serve",     action="store_true", help="Only run L2 serve")
    parser.add_argument("--chapter",        choices=["command", "us", "all"], default="all",
                        help="Which pipeline to run: command (global disease), us (US-facing), all (default)")
    args = parser.parse_args()

    if args.only_serve:
        args.skip_ingest = True
        args.skip_transform = True

    # Select module sets by chapter
    if args.chapter == "command":
        l0, l1, l2 = L0_GLOBAL, L1_GLOBAL, L2_GLOBAL
    elif args.chapter == "us":
        l0, l1, l2 = L0_US, L1_US, L2_US
    else:
        l0, l1, l2 = L0_MODULES, L1_MODULES, L2_MODULES

    log = PipelineLogger("run_all", dry_run=args.dry_run)
    log.info(f"Chapter: {args.chapter} | dry_run={args.dry_run}")
    failures: list[str] = []

    # ── L0: Ingest ───────────────────────────────────────────────────────────
    if not args.skip_ingest:
        log.info("═══ L0 Ingest ═══")
        for mod in l0:
            log.info(f"Running {mod}")
            if not run_module(mod, dry_run=args.dry_run):
                failures.append(mod)
    else:
        log.info("Skipping L0 ingest")

    # ── L1: Transform ────────────────────────────────────────────────────────
    if not args.skip_transform:
        log.info("═══ L1 Transform ═══")
        for mod in l1:
            log.info(f"Running {mod}")
            if not run_module(mod, dry_run=args.dry_run):
                failures.append(mod)
    else:
        log.info("Skipping L1 transform")

    # ── L2: Serve ────────────────────────────────────────────────────────────
    log.info("═══ L2 Serve ═══")
    for mod in l2:
        log.info(f"Running {mod}")
        if not run_module(mod, dry_run=args.dry_run):
            failures.append(mod)

    # ── Summary ──────────────────────────────────────────────────────────────
    if failures:
        log.error(f"Pipeline completed with {len(failures)} failure(s): {failures}")
        sys.exit(1)
    else:
        log.finish()
        print("\n✓ All pipeline stages completed successfully.")


if __name__ == "__main__":
    main()
