# Graph Report - .  (2026-04-13)

## Corpus Check
- Corpus is ~19,345 words - fits in a single context window. You may not need a graph.

## Summary
- 206 nodes · 223 edges · 43 communities detected
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 24 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Malaria Intel Pipeline & Sources|Malaria Intel Pipeline & Sources]]
- [[_COMMUNITY_L1 Transform & Logging|L1 Transform & Logging]]
- [[_COMMUNITY_S3 Storage Utilities|S3 Storage Utilities]]
- [[_COMMUNITY_Frontend Data Fetching|Frontend Data Fetching]]
- [[_COMMUNITY_Investment Dashboard Canvas|Investment Dashboard Canvas]]
- [[_COMMUNITY_Data Validation Layer|Data Validation Layer]]
- [[_COMMUNITY_L2 Chapter Builders|L2 Chapter Builders]]
- [[_COMMUNITY_US Ecosystem Canvas|US Ecosystem Canvas]]
- [[_COMMUNITY_Flows World Map Canvas|Flows World Map Canvas]]
- [[_COMMUNITY_Outlook Canvas|Outlook Canvas]]
- [[_COMMUNITY_Impact Canvas|Impact Canvas]]
- [[_COMMUNITY_Pipeline Orchestrator|Pipeline Orchestrator]]
- [[_COMMUNITY_USAspending Ingest|USAspending Ingest]]
- [[_COMMUNITY_WHORBM Ingest|WHO/RBM Ingest]]
- [[_COMMUNITY_NIH Reporter Ingest|NIH Reporter Ingest]]
- [[_COMMUNITY_Foreign Assistance Ingest|Foreign Assistance Ingest]]
- [[_COMMUNITY_ClinicalTrials Ingest|ClinicalTrials Ingest]]
- [[_COMMUNITY_App Root Layout|App Root Layout]]
- [[_COMMUNITY_Home Page|Home Page]]
- [[_COMMUNITY_Product Layout|Product Layout]]
- [[_COMMUNITY_Investment Page Client|Investment Page Client]]
- [[_COMMUNITY_Investment Route|Investment Route]]
- [[_COMMUNITY_Ecosystem Page Client|Ecosystem Page Client]]
- [[_COMMUNITY_Ecosystem Route|Ecosystem Route]]
- [[_COMMUNITY_Flows Page Client|Flows Page Client]]
- [[_COMMUNITY_Flows Route|Flows Route]]
- [[_COMMUNITY_Impact Route|Impact Route]]
- [[_COMMUNITY_Outlook Route|Outlook Route]]
- [[_COMMUNITY_Chapter Hero Component|Chapter Hero Component]]
- [[_COMMUNITY_Section Header Component|Section Header Component]]
- [[_COMMUNITY_App Shell Layout|App Shell Layout]]
- [[_COMMUNITY_Top Navigation|Top Navigation]]
- [[_COMMUNITY_CSS Class Utility|CSS Class Utility]]
- [[_COMMUNITY_Next.js Types|Next.js Types]]
- [[_COMMUNITY_Tailwind Config|Tailwind Config]]
- [[_COMMUNITY_PostCSS Config|PostCSS Config]]
- [[_COMMUNITY_Next.js Config|Next.js Config]]
- [[_COMMUNITY_Service Worker|Service Worker]]
- [[_COMMUNITY_KPI Card Component|KPI Card Component]]
- [[_COMMUNITY_Map Type Definitions|Map Type Definitions]]
- [[_COMMUNITY_Implementing Partners Gap|Implementing Partners Gap]]
- [[_COMMUNITY_AWS Profile Config|AWS Profile Config]]
- [[_COMMUNITY_AWS Region Config|AWS Region Config]]

## God Nodes (most connected - your core abstractions)
1. `PipelineLogger` - 20 edges
2. `get()` - 10 edges
3. `L0 Ingest Layer` - 9 edges
4. `L2 Serve Layer` - 8 edges
5. `Malaria Intel Data Pipeline` - 7 edges
6. `require_keys()` - 6 edges
7. `L1 Transform Layer` - 6 edges
8. `require_nonempty()` - 5 edges
9. `StepContext` - 5 edges
10. `meta()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Malaria No More Brand Identity` --conceptually_related_to--> `Malaria Intel Data Pipeline`  [INFERRED]
  frontend/public/mnm-logo.webp → pipelines/README.md
- `Pipeline orchestrator — runs L0 → L1 → L2 in sequence.  Usage:     python pipeli` --uses--> `PipelineLogger`  [INFERRED]
  pipelines/run_all.py → pipelines/utils/logger.py
- `Import and run a pipeline module. Returns True on success.` --uses--> `PipelineLogger`  [INFERRED]
  pipelines/run_all.py → pipelines/utils/logger.py
- `L0 — WHO / RBM burden data ingest Fetches country-level malaria burden indicator` --uses--> `PipelineLogger`  [INFERRED]
  pipelines/ingest/who_rbm.py → pipelines/utils/logger.py
- `L0 — USAspending Geography ingest Uses the /spending_by_geography/ endpoint (fix` --uses--> `PipelineLogger`  [INFERRED]
  pipelines/ingest/usaspending_geography.py → pipelines/utils/logger.py

## Hyperedges (group relationships)
- **Three-Layer Data Pipeline (L0 → L1 → L2)** — readme_l0_ingest, readme_l1_transform, readme_l2_serve [EXTRACTED 1.00]
- **All Ingest Scripts (L0 Sources)** — readme_ingest_nih_reporter, readme_ingest_usaspending, readme_ingest_clinicaltrials, readme_ingest_foreign_assistance, readme_ingest_who_rbm [EXTRACTED 1.00]
- **Known Pipeline Gaps / Issues** — readme_gap_pmi_country_allocations, readme_gap_oecd_dac2a, readme_gap_global_fund, readme_gap_implementing_partners [EXTRACTED 1.00]
- **Frontend-Ready Serving JSONs (L2)** — readme_serving_investment, readme_serving_flows, readme_serving_us_ecosystem, readme_serving_impact, readme_serving_risk [EXTRACTED 1.00]

## Communities

### Community 0 - "Malaria Intel Pipeline & Sources"
Cohesion: 0.08
Nodes (30): Malaria No More — 20 Years Logo, Malaria No More 20th Anniversary, Malaria No More Brand Identity, compute_financial_flows.py, ClinicalTrials.gov (Data Source), ForeignAssistance.gov (Data Source), NIH Reporter (Data Source), USAspending.gov (Data Source) (+22 more)

### Community 1 - "L1 Transform & Logging"
Cohesion: 0.14
Nodes (8): L1 — Aggregate US state-level malaria activity Merges NIH Reporter grants + USAs, load_global_fund_flows(), L1 — Compute country-level US funding flows Merges PMI allocations + Global Fund, Load Global Fund grant data from existing raw layer., run(), PipelineLogger, Structured pipeline logging — writes to stdout and optionally to RDS pipeline_ru, StepContext

### Community 2 - "S3 Storage Utilities"
Cohesion: 0.12
Nodes (19): get_json(), key_exists(), latest_raw(), list_dates(), processed_key(), put_json(), put_meta(), S3 utilities for malaria-intel data pipeline. All reads/writes go through these (+11 more)

### Community 3 - "Frontend Data Fetching"
Cohesion: 0.3
Nodes (10): fetchCaseTrends(), fetchCountryCards(), fetchGeographicSpend(), fetchImpact(), fetchInvestment(), fetchOutlook(), fetchStateDetail(), fetchUSEcosystem() (+2 more)

### Community 4 - "Investment Dashboard Canvas"
Cohesion: 0.2
Nodes (2): AnimatedHeroKPI(), useCountUp()

### Community 5 - "Data Validation Layer"
Cohesion: 0.44
Nodes (9): Data validation helpers. Each validator raises ValueError on failure. Run before, require_keys(), require_nonempty(), require_positive(), validate_impact(), validate_investment_overview(), validate_outlook(), validate_us_ecosystem() (+1 more)

### Community 6 - "L2 Chapter Builders"
Cohesion: 0.31
Nodes (8): build_flows(), build_impact(), build_investment(), build_meta(), build_outlook(), meta(), L2 — Build all serving JSONs for the dashboard. Reads from processed/ layer and, run()

### Community 7 - "US Ecosystem Canvas"
Cohesion: 0.33
Nodes (0): 

### Community 8 - "Flows World Map Canvas"
Cohesion: 0.33
Nodes (0): 

### Community 9 - "Outlook Canvas"
Cohesion: 0.33
Nodes (0): 

### Community 10 - "Impact Canvas"
Cohesion: 0.4
Nodes (0): 

### Community 11 - "Pipeline Orchestrator"
Cohesion: 0.5
Nodes (4): main(), Pipeline orchestrator — runs L0 → L1 → L2 in sequence.  Usage:     python pipeli, Import and run a pipeline module. Returns True on success., run_module()

### Community 12 - "USAspending Ingest"
Cohesion: 0.5
Nodes (4): fetch_by_geography(), L0 — USAspending Geography ingest Uses the /spending_by_geography/ endpoint (fix, Fetch spending aggregated by recipient state for a keyword + FY., run()

### Community 13 - "WHO/RBM Ingest"
Cohesion: 0.67
Nodes (3): fetch_indicator(), L0 — WHO / RBM burden data ingest Fetches country-level malaria burden indicator, run()

### Community 14 - "NIH Reporter Ingest"
Cohesion: 0.67
Nodes (3): fetch_grants(), L0 — NIH Reporter ingest Fetches malaria R&D grants from the NIH Reporter API, e, run()

### Community 15 - "Foreign Assistance Ingest"
Cohesion: 0.67
Nodes (3): fetch_csv(), L0 — ForeignAssistance.gov ingest Fetches US bilateral foreign aid by country an, run()

### Community 16 - "ClinicalTrials Ingest"
Cohesion: 0.67
Nodes (3): fetch_trials(), L0 — ClinicalTrials.gov ingest Fetches malaria clinical trials with US sponsors/, run()

### Community 17 - "App Root Layout"
Cohesion: 1.0
Nodes (0): 

### Community 18 - "Home Page"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "Product Layout"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Investment Page Client"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "Investment Route"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Ecosystem Page Client"
Cohesion: 1.0
Nodes (0): 

### Community 23 - "Ecosystem Route"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Flows Page Client"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Flows Route"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Impact Route"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Outlook Route"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Chapter Hero Component"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Section Header Component"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "App Shell Layout"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Top Navigation"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "CSS Class Utility"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Next.js Types"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Tailwind Config"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "PostCSS Config"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Next.js Config"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Service Worker"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "KPI Card Component"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Map Type Definitions"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Implementing Partners Gap"
Cohesion: 1.0
Nodes (1): Known Gap: Implementing Partners Directory Manual Only

### Community 41 - "AWS Profile Config"
Cohesion: 1.0
Nodes (1): Env Var: AWS_PROFILE

### Community 42 - "AWS Region Config"
Cohesion: 1.0
Nodes (1): Env Var: AWS_DEFAULT_REGION

## Knowledge Gaps
- **30 isolated node(s):** `Data validation helpers. Each validator raises ValueError on failure. Run before`, `Structured pipeline logging — writes to stdout and optionally to RDS pipeline_ru`, `S3 utilities for malaria-intel data pipeline. All reads/writes go through these`, `Build a raw layer S3 key: raw/{source}/dt={date}/{filename}`, `Build a processed layer S3 key: processed/{domain}/{table}/{filename}` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `App Root Layout`** (2 nodes): `layout.tsx`, `RootLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Home Page`** (2 nodes): `page.tsx`, `Home()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Product Layout`** (2 nodes): `layout.tsx`, `ProductLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Investment Page Client`** (2 nodes): `InvestmentCanvasClient.tsx`, `InvestmentCanvasClient()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Investment Route`** (2 nodes): `page.tsx`, `InvestmentPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ecosystem Page Client`** (2 nodes): `EcosystemCanvasClient()`, `EcosystemCanvasClient.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ecosystem Route`** (2 nodes): `page.tsx`, `EcosystemPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Flows Page Client`** (2 nodes): `FlowsCanvasClient()`, `FlowsCanvasClient.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Flows Route`** (2 nodes): `page.tsx`, `FlowsPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Impact Route`** (2 nodes): `page.tsx`, `ImpactPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Outlook Route`** (2 nodes): `page.tsx`, `OutlookPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chapter Hero Component`** (2 nodes): `ChapterHero()`, `ChapterHero.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Section Header Component`** (2 nodes): `SectionHeader.tsx`, `SectionHeader()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App Shell Layout`** (2 nodes): `AppShell()`, `AppShell.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Top Navigation`** (2 nodes): `TopNav.tsx`, `handleClick()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CSS Class Utility`** (2 nodes): `cn()`, `cn.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Next.js Types`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tailwind Config`** (1 nodes): `tailwind.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PostCSS Config`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Next.js Config`** (1 nodes): `next.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Service Worker`** (1 nodes): `sw.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `KPI Card Component`** (1 nodes): `KPICard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Map Type Definitions`** (1 nodes): `map-types.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Implementing Partners Gap`** (1 nodes): `Known Gap: Implementing Partners Directory Manual Only`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AWS Profile Config`** (1 nodes): `Env Var: AWS_PROFILE`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AWS Region Config`** (1 nodes): `Env Var: AWS_DEFAULT_REGION`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PipelineLogger` connect `L1 Transform & Logging` to `L2 Chapter Builders`, `Pipeline Orchestrator`, `USAspending Ingest`, `WHO/RBM Ingest`, `NIH Reporter Ingest`, `Foreign Assistance Ingest`, `ClinicalTrials Ingest`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `L2 — Build all serving JSONs for the dashboard. Reads from processed/ layer and` connect `L2 Chapter Builders` to `L1 Transform & Logging`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `PipelineLogger` (e.g. with `Pipeline orchestrator — runs L0 → L1 → L2 in sequence.  Usage:     python pipeli` and `Import and run a pipeline module. Returns True on success.`) actually correct?**
  _`PipelineLogger` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `L0 Ingest Layer` (e.g. with `run_all.py Pipeline Runner` and `NIH Reporter Ingest Script`) actually correct?**
  _`L0 Ingest Layer` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Malaria Intel Data Pipeline` (e.g. with `Env Var: MALARIA_INTEL_BUCKET` and `Malaria No More Brand Identity`) actually correct?**
  _`Malaria Intel Data Pipeline` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Data validation helpers. Each validator raises ValueError on failure. Run before`, `Structured pipeline logging — writes to stdout and optionally to RDS pipeline_ru`, `S3 utilities for malaria-intel data pipeline. All reads/writes go through these` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Malaria Intel Pipeline & Sources` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._