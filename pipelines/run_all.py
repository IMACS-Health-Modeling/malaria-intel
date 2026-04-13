"""
Pipeline orchestrator — runs L0 → L1 → L2 in sequence.

Usage:
    python pipelines/run_all.py [--dry-run] [--skip-ingest] [--skip-transform]

Env vars required:
    MALARIA_INTEL_BUCKET  (default: cdah-malaria-intel-dev)
    AWS_PROFILE or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
"""

import argparse
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipelines.utils.logger import PipelineLogger

L0_MODULES = [
    "pipelines.ingest.nih_reporter",
    "pipelines.ingest.usaspending_geography",
    "pipelines.ingest.clinicaltrials",
    "pipelines.ingest.foreign_assistance",
    "pipelines.ingest.who_rbm",
]

L1_MODULES = [
    "pipelines.transform.aggregate_us_states",
    "pipelines.transform.compute_financial_flows",
]

L2_MODULES = [
    "pipelines.serve.build_all_chapters",
]


def run_module(module_path: str, dry_run: bool) -> bool:
    """Import and run a pipeline module. Returns True on success."""
    try:
        mod = importlib.import_module(module_path)
        mod.run(dry_run=dry_run)
        return True
    except Exception as e:
        print(f"  ✗ {module_path} failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Malaria Intel pipeline orchestrator")
    parser.add_argument("--dry-run",        action="store_true", help="Fetch + validate but don't write to S3")
    parser.add_argument("--skip-ingest",    action="store_true", help="Skip L0 ingest (use existing raw data)")
    parser.add_argument("--skip-transform", action="store_true", help="Skip L1 transform (use existing processed data)")
    parser.add_argument("--only-serve",     action="store_true", help="Only run L2 serve (equivalent to --skip-ingest --skip-transform)")
    args = parser.parse_args()

    if args.only_serve:
        args.skip_ingest = True
        args.skip_transform = True

    log = PipelineLogger("run_all", dry_run=args.dry_run)
    failures: list[str] = []

    # ── L0: Ingest ───────────────────────────────────────────────────────────
    if not args.skip_ingest:
        log.info("═══ L0 Ingest ═══")
        for mod in L0_MODULES:
            log.info(f"Running {mod}")
            if not run_module(mod, dry_run=args.dry_run):
                failures.append(mod)
    else:
        log.info("Skipping L0 ingest")

    # ── L1: Transform ────────────────────────────────────────────────────────
    if not args.skip_transform:
        log.info("═══ L1 Transform ═══")
        for mod in L1_MODULES:
            log.info(f"Running {mod}")
            if not run_module(mod, dry_run=args.dry_run):
                failures.append(mod)
    else:
        log.info("Skipping L1 transform")

    # ── L2: Serve ────────────────────────────────────────────────────────────
    log.info("═══ L2 Serve ═══")
    for mod in L2_MODULES:
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
