/** Central data fetcher — reads from filesystem in dev, S3 in prod */

import { readFileSync } from "fs";
import { join } from "path";

const ROOT = process.env.DATA_ROOT ?? "";
const IS_S3 = ROOT && !ROOT.includes("localhost");

async function get<T>(path: string): Promise<T> {
  if (!IS_S3) {
    // Local dev: read directly from public/ on the filesystem — no circular HTTP
    const filePath = join(process.cwd(), "public", path);
    const content = readFileSync(filePath, "utf-8");
    return JSON.parse(content) as T;
  }
  const url = `${ROOT}/${path}`;
  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Data fetch failed: ${url} (${res.status})`);
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface Meta {
  generated_at: string;
  sources: string[];
  record_count: number;
  pipeline_version: string;
}

export interface InvestmentDonor {
  name: string;
  flag: string;
  total_usd: number;
  share_pct: number;
}

export interface InvestmentDiseaseEfficiency {
  disease: string;
  color: string;
  badge: string | null;
  cost_per_death_averted_usd: number;
  annual_deaths_thousands: number;
  annual_cases_millions: number;
  us_annual_usd: number;
  pct_children: number;
}

export interface InvestmentLeverageComponent {
  label: string;
  ratio: number;
  color: string;
}

export interface InvestmentOverview {
  _meta: Meta;
  total_committed_usd: number;
  pmi_annual_avg_usd: number;
  gf_us_contribution_usd: number;
  gf_malaria_disbursed_usd: number;
  nih_annual_avg_usd: number;
  us_rank: number;
  us_donor_share_pct: number;
  years: { year: number; pmi: number; gf: number; nih: number }[];
  disease_split: { disease: string; pct: number; usd: number }[];
  authorized_vs_deployed: { year: number; authorized: number; deployed: number }[];
  donors: InvestmentDonor[];
  disease_efficiency: InvestmentDiseaseEfficiency[];
  leverage: { pmi_ratio: number; components: InvestmentLeverageComponent[]; description: string };
  channel: { bilateral_pct: number; multilateral_pct: number };
  milestones: { year: number; label: string }[];
}

export interface CountryFlow {
  iso3: string;
  name: string;
  region: string;
  us_allocation_usd: number;
  malaria_deaths: number;
  malaria_cases: number;
  funding_rank: number;
  burden_rank: number;
  programs: string[];
  gf_disbursed_usd?: number | null;
  gf_committed_usd?: number | null;
  usaspending_actual_usd?: number;
}

export interface WorldMapData {
  _meta: Meta;
  flows: CountryFlow[];
}

export interface StateData {
  code: string;
  name: string;
  nih_grants_usd: number;
  usaspending_usd: number;
  clinical_trials: number;
  org_count: number;
  countries_reached: number;
  top_orgs: { name: string; type: string; usd: number; countries: string[] }[];
}

export interface TopContractor {
  rank: number;
  name: string;
  amount_usd: number;
  type: string;
  hq_state: string | null;
}

export interface USEcosystemData {
  _meta: Meta;
  states: StateData[];
  total_nih_usd: number;
  total_orgs: number;
  total_trials: number;
  top_contractors?: TopContractor[];
}

export interface ImpactResults {
  _meta: Meta;
  lives_saved_total: number;
  cases_averted_annual: number;
  child_deaths_prevented: number;
  cost_per_life_saved_usd: number;
  gf_nets_distributed_millions?: number;
  gf_cases_treated_millions?: number;
  gf_smc_children_millions?: number;
  gf_malaria_disbursed_usd?: number;
  cost_vs_comparators: { intervention: string; cost_usd: number }[];
  country_progress: {
    iso3: string;
    name: string;
    cases_2010: number;
    cases_2023: number;
    pct_reduction: number;
    note?: string;
  }[];
}

export interface OutlookData {
  _meta: Meta;
  funding_gap_usd: number;
  who_target_usd: number;
  current_funded_usd: number;
  high_dependency_countries: {
    iso3: string;
    name: string;
    us_pct_of_budget: number;
    at_risk_programs: number;
  }[];
  resistance_hotspots: {
    iso3: string;
    name: string;
    severity: "low" | "moderate" | "high";
    drug: string;
  }[];
  economic_cost_trade_partners_usd: number;
  scenarios: {
    label: string;
    lives_at_risk: number;
    cases_rebound: number;
  }[];
}

export interface GeographicSpendCountry {
  country_code: string;
  country_name: string;
  amount: number;
}

export interface GeographicSpendData {
  by_country: GeographicSpendCountry[];
  top_implementing_partners: { name: string; amount_usd: number }[];
}

// ── Fetchers ─────────────────────────────────────────────────────────────────

export interface CaseTrendCountry {
  iso3: string;
  name: string;
  cases_by_year: number[];
  cases_2010: number;
  cases_2023: number;
  peak_year: number;
  trend: "rising" | "stable" | "declining";
}

export interface CaseTrendsData {
  _meta: { years: number[]; source: string };
  countries: CaseTrendCountry[];
}

export const fetchInvestment      = () => get<InvestmentOverview>("data/investment/overview.json");
export const fetchGeographicSpend = () => get<GeographicSpendData>("data/usaspending/geographic-spend.json");
export const fetchCaseTrends      = () => get<CaseTrendsData>("data/burden/case-trends.json");
export const fetchWorldMap    = () => get<WorldMapData>("data/flows/world-map.json");
export const fetchCountryCards = () => get<{ flows: CountryFlow[] }>("data/flows/country-cards.json");
export const fetchUSEcosystem = () => get<USEcosystemData>("data/us-ecosystem/states.json");
export const fetchStateDetail = (code: string) => get<StateData>(`data/us-ecosystem/state-detail/${code}.json`);
export const fetchImpact      = () => get<ImpactResults>("data/impact/results.json");
export const fetchOutlook     = () => get<OutlookData>("data/risk/outlook.json");

// ── Command page — live S3 data (WHO DON, burden, threats) ──────────────────

const CMD_ROOT =
  process.env.DATA_ROOT_COMMAND ??
  "https://malariascope-dev-data-019847570980.s3.amazonaws.com/v1";

async function getCmd<T>(path: string): Promise<T> {
  const url = `${CMD_ROOT}/${path}`;
  const res = await fetch(url, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`Command data fetch failed: ${url} (${res.status})`);
  return res.json() as Promise<T>;
}

export type GlobalSummary = {
  period: string;
  global: {
    estimated_cases: number;
    estimated_deaths: number;
    countries_endemic: number;
    countries_in_alert: number;
    pf_proportion: number;
    pv_proportion: number;
    cases_change_yoy: number;
    deaths_change_yoy: number;
    funding_gap_usd: number;
    total_funding_usd?: number;
    active_febrile_overlaps?: number;
  };
  top_burden_countries: CommandCountrySummary[];
};

export type CommandCountrySummary = {
  iso3: string;
  name: string;
  region?: string;
  incidence_per_1000: number;
  cases: number;
  deaths: number;
  cases_change_yoy: number | null;
  deaths_change_yoy?: number;
  llin_coverage?: number;
  irs_coverage?: number;
  act_coverage?: number;
  rdt_coverage?: number;
  funding_per_capita?: number;
  elimination_phase?: string;
  population_at_risk?: number | null;
  alert_level: string;
  lat?: number;
  lng?: number;
  change_yoy?: number;
  data_year?: number;
};

export type ThreatEvent = {
  event_id: string;
  disease: string;
  event_type: string;
  country_iso3: string;
  country_name: string;
  admin1: string;
  severity: number;
  start_date: string;
  status: string;
  cases_reported: number | null;
  deaths_reported: number | null;
  overlap_with_malaria_zone: number;
  dci_score: number | null;
  source: string;
  lat: number;
  lng: number;
  narrative: string;
};

export type GlobalTimeseriesPoint = {
  year: number;
  cases_millions: number;
  deaths_thousands: number;
  incidence_per_1000: number;
  llin_coverage: number;
  act_coverage: number;
};

export type EndemicBoundaries = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: { iso3: string; name: string };
    geometry: { type: string; coordinates: unknown };
  }>;
};

export const getGlobalSummary    = () => getCmd<GlobalSummary>("burden/global-summary.json");
export const getCommandCountries = () => getCmd<CommandCountrySummary[]>("burden/countries.json");
export const getActiveThreats    = () => getCmd<ThreatEvent[]>("events/active-threats.json");
export const getGlobalTimeseries = () => getCmd<GlobalTimeseriesPoint[]>("burden/timeseries-global.json");
export const getEndemicBoundaries = () => getCmd<EndemicBoundaries>("geo/endemic-boundaries.json");

// ── US Map geometry (server-side only) ───────────────────────────────────────

export type { StatePath } from "./map-types";
export { MAP_W, MAP_H } from "./map-types";
import type { StatePath } from "./map-types";
import { MAP_W, MAP_H } from "./map-types";

interface GeoFeature {
  type: string;
  properties: { name: string } | null;
  geometry: unknown;
}
interface GeoFeatureCollection { type: string; features: GeoFeature[] }

export async function fetchUSStatePaths(): Promise<StatePath[]> {
  // This function MUST only run server-side — d3-geo is safe in Node.
  const { geoAlbersUsa, geoPath } = await import("d3-geo");
  const geo = await get<GeoFeatureCollection>("data/us-ecosystem/us-states.json");
  const features = geo.features.filter((f) => f.properties?.name !== "Puerto Rico");
  const collection = { ...geo, features };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const projection = geoAlbersUsa().fitSize([MAP_W, MAP_H], collection as any);
  const pathGen = geoPath(projection);
  return features.map((feature) => {
    const rawName = feature.properties?.name ?? "";
    const stateName = rawName === "District of Columbia" ? "Washington DC" : rawName;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = pathGen(feature as any) ?? "";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = pathGen.centroid(feature as any);
    const centroid: [number, number] | null =
      c && !isNaN(c[0]) && !isNaN(c[1]) ? [c[0], c[1]] : null;
    return { stateName, d, centroid };
  });
}
