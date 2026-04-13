# Malaria Intel — Data Pipeline

Three-layer pipeline: **L0 Ingest → L1 Transform → L2 Serve**

All data lands in S3 bucket `cdah-malaria-intel-dev` (prod: `cdah-malaria-intel-prod`).

## Quick Start

```bash
# Install dependencies
pip install boto3 requests

# Set AWS credentials
export AWS_PROFILE=cdah-dev
export MALARIA_INTEL_BUCKET=cdah-malaria-intel-dev

# Full pipeline run
python pipelines/run_all.py

# Dry run (fetch + validate, no S3 writes)
python pipelines/run_all.py --dry-run

# Only rebuild serving JSONs (skip ingest + transform)
python pipelines/run_all.py --only-serve

# Run a single chapter
python pipelines/run_all.py --only-serve --chapter investment
```

## S3 Structure

```
cdah-malaria-intel-dev/
  raw/                          # L0 — immutable, date-partitioned
    nih-reporter/dt=YYYY-MM-DD/
    usaspending/dt=YYYY-MM-DD/
    clinicaltrials/dt=YYYY-MM-DD/
    foreign-assistance/dt=YYYY-MM-DD/
    who-rbm/dt=YYYY-MM-DD/
    pmi/annual-reports/FY{year}/
    global-fund/dt=YYYY-MM-DD/
    oecd/dt=YYYY-MM-DD/
    reference/                  # Static curated files (manually updated)
  processed/                    # L1 — cleaned, aggregated
    financial/flows-by-country/
    us-states/by-state/
    impact/
    risk/
  serving/v1/                   # L2 — frontend-ready JSONs
    investment/overview.json
    flows/world-map.json
    us-ecosystem/states.json
    us-ecosystem/state-detail/{STATE}.json
    impact/results.json
    risk/outlook.json
    meta/last-updated.json
```

## Data Sources

| Source | Script | Frequency | Notes |
|--------|--------|-----------|-------|
| NIH Reporter | `ingest/nih_reporter.py` | Weekly | API v2, malaria keyword search |
| USAspending | `ingest/usaspending_geography.py` | Monthly | `/spending_by_geography/` endpoint |
| ClinicalTrials.gov | `ingest/clinicaltrials.py` | Weekly | API v2, US sponsors |
| ForeignAssistance.gov | `ingest/foreign_assistance.py` | Monthly | Full CSV download |
| WHO/RBM | `ingest/who_rbm.py` | Monthly | GHO API |

## Known Issues / Gaps

1. **PMI country-level allocations** — currently using FY2024 reference figures from CBJ. `ingest/pmi_annual_reports.py` (PDF scraping) not yet built — add when PMI publishes FY2025 CBJ.
2. **OECD DAC2A** — 1.4GB file available in foundation bucket at `raw/oda_finance/oecd_crs/oecd_dac2a_aid_by_sector.csv`. Not yet wired into L1 transform — use for US bilateral health ODA by recipient country.
3. **Global Fund full financials** — `AllFinancialIndicators` (6 parts) in foundation bucket but not yet registered in Glue. Wire into `compute_financial_flows.py` for transaction-level GF data.
4. **Implementing partners directory** — `raw/reference/implementing-partners.json` is manually maintained. No automated ingest exists — update manually when PMI publishes new partner lists.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MALARIA_INTEL_BUCKET` | `cdah-malaria-intel-dev` | Target S3 bucket |
| `AWS_PROFILE` | (system default) | AWS credentials profile |
| `AWS_DEFAULT_REGION` | `us-east-1` | AWS region |
