export type MetricMeta = {
  title: string;
  methodology: string;
  source: string;
  sourceYear?: string;
  confidence: "high" | "medium" | "low";
  confidenceReason: string;
  notes?: string;
};

export const METRIC_META = {
  // ── Global burden ──────────────────────────────────────────
  global_cases: {
    title: "Estimated Global Malaria Cases",
    methodology:
      "WHO model-based estimates combining surveillance data, household surveys (DHS/MICS), and satellite-derived environmental covariates. Not directly observed — estimated with uncertainty intervals.",
    source: "WHO World Malaria Report 2024, Annex 4A",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Model-based estimates with ±15–25% uncertainty in high-burden countries where surveillance is weak. African countries account for ~94% of cases.",
  },
  global_deaths: {
    title: "Estimated Global Malaria Deaths",
    methodology:
      "WHO cause-of-death modelling using vital registration, verbal autopsy, and hospital data. Under-5 deaths are more reliably estimated via survey data.",
    source: "WHO World Malaria Report 2024, Annex 4A",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Deaths are harder to attribute than cases. Many occur outside health facilities. Confidence intervals typically ±20–30%.",
  },
  cases_change_yoy: {
    title: "Year-over-Year Case Change",
    methodology:
      "Percentage change from prior-year WHO estimates: (current_year_cases - prior_year_cases) / prior_year_cases × 100. Uses the same modelling framework across both years.",
    source: "WHO World Malaria Report 2024",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "YoY changes inherit uncertainty from both annual estimates. Small real changes may fall within model noise. Directional trends are more reliable than precise magnitudes.",
  },
  endemic_countries: {
    title: "Endemic Countries",
    methodology:
      "Countries classified as malaria-endemic by WHO based on confirmed local transmission in the preceding 3 years. Includes countries in all phases (high-burden through pre-elimination).",
    source: "WHO World Malaria Report 2024",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Binary classification with high agreement across monitoring systems. WHO regional offices verify annually.",
  },
  countries_in_alert: {
    title: "Countries in Alert",
    methodology:
      "Countries showing ≥10% increase in cases or deaths vs prior year, or countries flagged by WHO/NMCP for emergency response based on outbreak reports.",
    source: "WHO World Malaria Report 2024 · WHO Disease Outbreak News",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Alert thresholds are WHO-defined but depend on reporting quality. Low-surveillance countries may be under-alerted.",
  },
  financing_gap: {
    title: "Annual Financing Gap",
    methodology:
      "WHO Global Technical Strategy target of $8.3B/year (2021–2030) minus estimated total malaria disbursements in the reporting year from all donor sources.",
    source: "WHO Global Technical Strategy 2021–2030 · WHO World Malaria Report 2024",
    sourceYear: "2024",
    confidence: "low",
    confidenceReason:
      "Gap depends heavily on contested assumptions: the $8.3B GTS target itself is modelled, donor data is aggregated from inconsistent reporting timelines, and actual needs vary by epidemic trajectory.",
  },

  // ── Country-level burden ────────────────────────────────────
  country_cases: {
    title: "Country Estimated Cases",
    methodology:
      "Country-specific WHO model estimate combining NMCP surveillance, household surveys, and Plasmodium falciparum parasite rate (PfPR) from the Malaria Atlas Project.",
    source: "WHO World Malaria Report 2024, Annex 4A",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Country-level estimates vary in quality. High-income or elimination-phase countries have strong surveillance; Sub-Saharan African countries rely more heavily on modelling.",
  },
  country_deaths: {
    title: "Country Estimated Deaths",
    methodology:
      "WHO modelled deaths accounting for treatment-seeking rates, care quality, and age-specific mortality patterns. Validated against verbal autopsy data where available.",
    source: "WHO World Malaria Report 2024, Annex 4A",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Community deaths (outside health facilities) are estimated, not counted. Uncertainty is higher for countries with weak vital registration.",
  },
  country_incidence: {
    title: "Malaria Incidence per 1,000 Population at Risk",
    methodology:
      "Estimated cases ÷ estimated population living in malaria-transmission areas × 1,000. Population at risk excludes areas with zero or negligible transmission probability.",
    source: "WHO World Malaria Report 2024",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Inherits case estimate uncertainty plus population-at-risk estimate uncertainty. The denominator (population at risk) itself is modelled.",
  },
  llin_coverage: {
    title: "ITN / LLIN Use Among Population at Risk",
    methodology:
      "Percentage of population sleeping under an insecticide-treated net the previous night, from nationally representative household surveys (DHS, MIS, MICS). Coverage differs from 'distributed' — nets may not be used after distribution.",
    source: "WHO Global Health Observatory · DHS Program · USAID MIS",
    sourceYear: "2023",
    confidence: "medium",
    confidenceReason:
      "Surveys are conducted every 3–5 years; data may be 1–3 years old. Self-reported use rates can overestimate actual consistent use.",
    notes: "Coverage ≥80% is WHO target for universal coverage.",
  },
  irs_coverage: {
    title: "Indoor Residual Spraying Coverage",
    methodology:
      "Percentage of targeted structures sprayed with insecticide in the most recent IRS campaign, as reported by National Malaria Control Programs to WHO.",
    source: "WHO World Malaria Report 2024 · NMCP Reports",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Denominator (targeted structures) is NMCP-defined and varies by program scope. Reporting timeliness differs across countries.",
  },
  act_coverage: {
    title: "ACT Treatment Coverage",
    methodology:
      "Percentage of confirmed malaria cases treated with artemisinin-based combination therapy (ACT), as reported by health facilities to NMCP.",
    source: "WHO Global Health Observatory · WHO WMR 2024",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Denominator is only confirmed cases seen in health facilities — community-treated cases are excluded. Under-reporting of private-sector treatment is common.",
  },
  funding_per_capita: {
    title: "External Malaria Funding per Capita",
    methodology:
      "Total external malaria funding received (Global Fund disbursements + PMI/USAID bilateral + World Bank + other bilateral donors) ÷ total population. Uses IATI-reported disbursements aggregated from foreignassistance.gov, Global Fund Data Service API v4, and USAspending.gov.",
    source: "Global Fund API v4 · USAspending.gov · ForeignAssistance.gov IATI",
    sourceYear: "2023",
    confidence: "medium",
    confidenceReason:
      "Funding data lags 12–18 months. Some donors report commitments rather than actual disbursements. Population figures from WMR 2024 national estimates.",
  },

  // ── Investment page ─────────────────────────────────────────
  total_us_committed: {
    title: "Total US Malaria Commitment",
    methodology:
      "Cumulative US government malaria-specific obligations including PMI bilateral program, US contribution to Global Fund pledges, and NIH malaria research grants. Sourced from multiple appropriations cycles.",
    source: "OECD DAC1 · PMI FY2024 Congressional Justification · NIH RePORTER API",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Government-reported official development assistance is audited. Minor differences arise from obligation vs disbursement timing.",
  },
  pmi_annual: {
    title: "PMI Annual Program Funding",
    methodology:
      "USAID President's Malaria Initiative annual congressional appropriation for bilateral malaria programs. Separate from Global Fund contributions.",
    source: "PMI FY2024 Annual Report · USAID Congressional Budget Justification",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Appropriated and reported by US Congress. Actual spend may differ slightly from appropriation due to reprogramming.",
  },
  gf_us_contribution: {
    title: "US Contribution to Global Fund",
    methodology:
      "Annual US government pledge and disbursement to the Global Fund to Fight AIDS, TB and Malaria. Historically ~33% of total GF replenishment — US law caps contribution at 33% of total donor contributions.",
    source: "OECD DAC1 · Global Fund Donor Pledges",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Pledges are public record; disbursements are audited. The 33% cap is US law (Lantos-Hyde Act).",
  },
  nih_annual: {
    title: "NIH Annual Malaria Research Funding",
    methodology:
      "Sum of all active NIH grants with malaria as the primary disease focus, using NIH RePORTER API (project_terms contains 'malaria'). Includes NIAID, FIC, and other institutes.",
    source: "NIH RePORTER API v2",
    sourceYear: "2025",
    confidence: "high",
    confidenceReason:
      "NIH grant data is official federal records. Some multi-disease grants are partially attributed — the filter may include grants where malaria is secondary.",
    notes: "Our pipeline pulls 2015–2025 with $6.8B total across 8,207 grants.",
  },
  cost_per_death_averted: {
    title: "Cost per Death Averted",
    methodology:
      "Total intervention cost ÷ modelled deaths averted based on impact evaluation studies. PMI attribution uses the malaria mortality reduction model from PMI-commissioned evaluations (University of Washington, IHME).",
    source: "PMI FY2024 Impact Evaluation · Bhatt et al. 2015, Nature · IHME GBD 2023",
    sourceYear: "2024",
    confidence: "low",
    confidenceReason:
      "Attribution is inherently uncertain — counterfactual (deaths without PMI) must be modelled. Estimates range $900–$3,500/death averted depending on methodology.",
    notes: "WHO CHOICE benchmark: <GDP per capita per DALY averted = 'very cost-effective'.",
  },
  leverage_ratio: {
    title: "PMI Leverage Ratio",
    methodology:
      "Total malaria funding mobilized (Global Fund grants to PMI countries + host government contributions + other bilateral) ÷ PMI bilateral spend. Measures catalytic effect of PMI investment.",
    source: "PMI FY2024 Annual Report · Global Fund API v4",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Causality between PMI presence and other donor activity is assumed, not proven. Some GF grants would likely exist without PMI.",
  },
  funding_gap: {
    title: "Annual Malaria Financing Gap",
    methodology:
      "WHO GTS target ($8.3B/year) minus estimated total disbursements from all sources in the reporting year. Gap is the difference between what is needed (WHO model) and what is funded.",
    source: "WHO Global Technical Strategy 2021–2030",
    sourceYear: "2024",
    confidence: "low",
    confidenceReason:
      "The $8.3B target is itself modelled under optimistic coverage assumptions. Actual gap depends on contested definitions of 'need' and 'available funding'.",
  },

  // ── Impact page ─────────────────────────────────────────────
  cases_averted: {
    title: "Annual Cases Averted by PMI",
    methodology:
      "Modelled malaria cases prevented per year by PMI-supported interventions (ITNs, IRS, IPTp, case management), using counterfactual analysis comparing observed cases to projected cases without PMI programs. From PMI-commissioned evaluation using IHME burden data.",
    source: "PMI FY2024 Annual Report · IHME GBD 2023 · Bhatt et al. 2015",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Attribution model requires counterfactual assumptions. Actual averted burden is not directly observed. Estimates range by ±20–30% depending on methodology.",
  },
  child_deaths_prevented: {
    title: "Child Deaths Prevented (Under-5)",
    methodology:
      "Subset of PMI-attributed lives saved: deaths averted among children under 5 years of age. Estimated using age-stratified mortality models. Children under 5 account for ~76% of malaria deaths globally.",
    source: "PMI FY2024 Annual Report · WHO WMR 2024 · IHME GBD 2023",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Derived from the same PMI attribution model as total lives saved. Age-stratification adds an additional modelling layer. Child deaths are better captured in surveys than adult deaths.",
  },
  lives_saved: {
    title: "PMI-Attributed Lives Saved",
    methodology:
      "Cumulative deaths averted attributed to PMI interventions (ITNs, IRS, IPTp, case management) using a counterfactual modelling framework. Based on PMI-commissioned evaluation using IHME mortality data and intervention coverage.",
    source: "PMI FY2024 Annual Report · Bhatt et al. 2015 (ITN impact) · IHME GBD 2023",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Attribution models require counterfactual assumptions that cannot be directly observed. The figure is a model estimate, not a measured count.",
  },
  gf_nets_distributed: {
    title: "Insecticide-Treated Nets Distributed",
    methodology:
      "Cumulative ITN/LLIN units procured and distributed by Global Fund grants to recipients (NMCPs, NGOs). Reported by Principal Recipients to Global Fund and audited.",
    source: "Global Fund Key Results 2024",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Distribution is tracked through supply chain management systems and spot-checked by LFAs (Local Fund Agents). Actual net use is lower than distribution numbers.",
  },
  gf_cases_treated: {
    title: "Confirmed Malaria Cases Treated",
    methodology:
      "Confirmed malaria cases (RDT or microscopy) treated with first-line ACT within GF-supported health facilities, as reported by NMCPs. Cumulative across all GF malaria grants.",
    source: "Global Fund Key Results 2024",
    sourceYear: "2024",
    confidence: "high",
    confidenceReason:
      "Facility-based reporting is systematic. Private sector and community-level treatment is not captured in this figure.",
  },

  // ── Flows page ─────────────────────────────────────────────
  pmi_allocation: {
    title: "PMI Country Allocation",
    methodology:
      "USAID congressional appropriation allocated to PMI country bilateral program. Country-level allocations are announced annually via PMI Country Operating Plans (COPs). These are obligations, not necessarily disbursements.",
    source: "USAspending.gov API v2 · PMI Country Operating Plans",
    sourceYear: "2025",
    confidence: "high",
    confidenceReason:
      "US government financial data is audited. Some difference between obligation and disbursement timing.",
  },
  gf_disbursed: {
    title: "Global Fund Disbursed",
    methodology:
      "Actual cash transferred from Global Fund to Principal Recipients for malaria grants in the country. Reported via Global Fund Data Service OData API v4.",
    source: "Global Fund Data Service API v4",
    sourceYear: "2026",
    confidence: "high",
    confidenceReason:
      "Global Fund financial data is audited by independent LFAs. Disbursement data typically lags 3–6 months from actual transfer.",
  },
  gf_committed: {
    title: "Global Fund Committed",
    methodology:
      "Total funding committed (signed grant agreement) for active malaria grants in the country. Includes undisbursed amounts from current grant periods.",
    source: "Global Fund Data Service API v4",
    sourceYear: "2026",
    confidence: "high",
    confidenceReason:
      "Commitment data is from signed grant agreements. Actual disbursement depends on grant performance and absorptive capacity.",
  },

  // ── US Ecosystem ────────────────────────────────────────────
  nih_grants_state: {
    title: "NIH Malaria Research Grants by State",
    methodology:
      "Sum of total NIH grant funding (direct + indirect costs) for malaria-focused grants where the principal investigator's institution is in the state. Filtered from NIH RePORTER for project_terms matching 'malaria'.",
    source: "NIH RePORTER API v2",
    sourceYear: "2025",
    confidence: "high",
    confidenceReason:
      "Official federal grant records. Some multi-institution awards may be attributed to the lead PI's state only.",
  },
  usaspending_state: {
    title: "Federal Malaria-Related Contract Awards by State",
    methodology:
      "USAID malaria program contracts and grants where the recipient's primary address is in the state. Sourced from USAspending.gov, filtered by CFDA 72.001 (USAID health programs) with malaria keyword.",
    source: "USAspending.gov API v2",
    sourceYear: "2025",
    confidence: "high",
    confidenceReason:
      "Federal procurement data is public record. Some contracts are awarded to HQ locations even if work occurs elsewhere.",
  },

  // ── Outlook ─────────────────────────────────────────────────
  scenario_lives_at_risk: {
    title: "Lives at Additional Risk (Scenario)",
    methodology:
      "Modelled additional deaths that would occur if funding falls to the specified scenario level, based on dose-response relationships between intervention coverage and mortality from WHO GTS impact analysis.",
    source: "WHO Global Technical Strategy 2021–2030 · PMI Impact Evaluation",
    sourceYear: "2024",
    confidence: "low",
    confidenceReason:
      "Projection models involve multiple compounded assumptions. Actual impact depends on how quickly programs scale down, whether other donors backfill, and country-level programmatic capacity.",
    notes: "Range reflects uncertainty bounds on the impact model.",
  },
  us_pct_of_budget: {
    title: "US Share of Country Malaria Budget",
    methodology:
      "PMI country bilateral allocation ÷ total external malaria financing received by the country × 100. Based on aggregated Global Fund + PMI + bilateral donor data.",
    source: "PMI Country Operating Plans · Global Fund API v4 · WHO WMR 2024",
    sourceYear: "2024",
    confidence: "medium",
    confidenceReason:
      "Denominator requires aggregating multiple donor reporting systems with different fiscal year definitions and reporting lags.",
  },
} as const satisfies Record<string, MetricMeta>;

export type MetricKey = keyof typeof METRIC_META;
