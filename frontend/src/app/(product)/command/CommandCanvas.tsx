"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  TrendingUp, TrendingDown, Minus,
  ArrowUpRight, X, AlertTriangle, ShieldCheck,
} from "lucide-react";
import { GlobalIntelMap } from "@/components/map/GlobalIntelMap";
import { LayerToggle } from "@/components/map/LayerToggle";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { METRIC_META } from "@/lib/metric-metadata";
import { cn } from "@/lib/cn";
import type { MetricMeta } from "@/lib/metric-metadata";
import type {
  GlobalSummary,
  CommandCountrySummary,
  ThreatEvent,
  GlobalTimeseriesPoint,
  EndemicBoundaries,
} from "@/lib/data";

type Props = {
  summary:    GlobalSummary;
  countries:  CommandCountrySummary[];
  threats:    ThreatEvent[];
  timeseries: GlobalTimeseriesPoint[];
  boundaries: EndemicBoundaries;
};

/* ── Formatters ────────────────────────────────────────────────────────────── */
function fmt(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
}
function fmtPct(n: number): string {
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

/* ── KPI chip ──────────────────────────────────────────────────────────────── */
function KpiChip({
  label, value, change, sub, meta,
}: { label: string; value: string; change?: number | null; sub?: string; meta?: MetricMeta }) {
  const Dir =
    change == null ? Minus
    : change > 0   ? TrendingUp
    : TrendingDown;
  const changeColor =
    change == null ? "text-txt-muted"
    : change > 0   ? "text-red-500"
    : "text-emerald-500";

  return (
    <div className="bg-white/90 backdrop-blur-[18px] border border-white/80 rounded-[14px] px-4 py-2.5 shadow-card min-w-[130px]">
      <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em] mb-0.5">{label}</p>
      <div className="flex items-center">
        <p className="font-gothic text-[28px] leading-none text-txt-primary" style={{ fontSynthesis: "none" }}>
          {value}
        </p>
        {meta && <InfoTooltip meta={meta} size={10} />}
      </div>
      {change != null && (
        <p className={cn("flex items-center gap-1 text-[10px] font-mono mt-0.5", changeColor)}>
          <Dir size={9} />{fmtPct(change)} YoY
        </p>
      )}
      {sub && change == null && (
        <p className="text-[10px] text-txt-muted mt-0.5">{sub}</p>
      )}
    </div>
  );
}

/* ── Coverage bar ──────────────────────────────────────────────────────────── */
function CoverageBar({ label, value, meta }: { label: string; value: number; meta?: MetricMeta }) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-[11px] text-txt-secondary">{label}</span>
        <div className="flex items-center">
          <span className="text-[11px] font-mono font-semibold text-txt-primary">{value.toFixed(0)}%</span>
          {meta && <InfoTooltip meta={meta} size={10} />}
        </div>
      </div>
      <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(value, 100)}%`,
            background: value >= 70 ? "#10b981" : value >= 40 ? "#f59e0b" : "#ef4444",
          }}
        />
      </div>
    </div>
  );
}

/* ── Country modal ─────────────────────────────────────────────────────────── */
function CountryModal({
  country,
  onClose,
}: {
  country: CommandCountrySummary;
  onClose: () => void;
}) {
  const changeColor = !country.cases_change_yoy ? "text-txt-muted"
    : country.cases_change_yoy > 0 ? "text-red-500" : "text-emerald-500";
  const ChangeIcon = !country.cases_change_yoy ? Minus
    : country.cases_change_yoy > 0 ? TrendingUp : TrendingDown;

  const alertHigh = country.alert_level === "high" || country.alert_level === "critical";

  return (
    <motion.div
      className="absolute inset-0 z-30 pointer-events-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      {/* Backdrop — click to close */}
      <div
        className="absolute inset-0 pointer-events-auto"
        onClick={onClose}
      />

      {/* Panel — slides in from right */}
      <motion.div
        className="absolute top-4 right-4 bottom-4 w-[340px] bg-white/96 backdrop-blur-2xl border border-surface-3 rounded-[22px] shadow-overlay flex flex-col overflow-hidden pointer-events-auto"
        initial={{ x: 40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 40, opacity: 0 }}
        transition={{ type: "spring", stiffness: 320, damping: 32 }}
      >
        {/* Header */}
        <div className="px-5 pt-5 pb-4 border-b border-surface-2 shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                {alertHigh && (
                  <AlertTriangle size={13} className="text-amber-500 shrink-0" />
                )}
                {country.elimination_phase && (
                  <ShieldCheck size={13} className="text-emerald-500 shrink-0" />
                )}
                <span className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em]">
                  {country.iso3} · {country.region ?? "—"}
                </span>
              </div>
              <h2 className="font-gothic text-2xl text-txt-primary leading-tight" style={{ fontSynthesis: "none" }}>
                {country.name}
              </h2>
              {country.elimination_phase && (
                <span className="inline-block mt-1 text-[10px] font-mono text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-pill px-2 py-0.5">
                  {country.elimination_phase}
                </span>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-[8px] hover:bg-surface-2 text-txt-muted hover:text-txt-primary transition-colors shrink-0"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {/* Burden */}
          <div>
            <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em] mb-3">Burden</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surface-1 rounded-[14px] p-3">
                <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.08em] mb-1">Cases</p>
                <div className="flex items-center">
                  <p className="font-gothic text-[26px] leading-none text-txt-primary" style={{ fontSynthesis: "none" }}>
                    {fmt(country.cases)}
                  </p>
                  <InfoTooltip meta={METRIC_META.country_cases} size={10} />
                </div>
                {country.cases_change_yoy != null && (
                  <p className={cn("flex items-center gap-1 text-[10px] font-mono mt-1", changeColor)}>
                    <ChangeIcon size={9} />{fmtPct(country.cases_change_yoy)} YoY
                  </p>
                )}
              </div>
              <div className="bg-surface-1 rounded-[14px] p-3">
                <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.08em] mb-1">Deaths</p>
                <div className="flex items-center">
                  <p className="font-gothic text-[26px] leading-none text-txt-primary" style={{ fontSynthesis: "none" }}>
                    {fmt(country.deaths)}
                  </p>
                  <InfoTooltip meta={METRIC_META.country_deaths} size={10} />
                </div>
                <p className="text-[10px] text-txt-muted font-mono mt-1">est. 2023</p>
              </div>
            </div>
            <div className="bg-surface-1 rounded-[14px] p-3 mt-3">
              <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.08em] mb-1">Incidence</p>
              <div className="flex items-end gap-1.5">
                <span className="font-gothic text-[26px] leading-none text-txt-primary" style={{ fontSynthesis: "none" }}>
                  {country.incidence_per_1000.toFixed(1)}
                </span>
                <InfoTooltip meta={METRIC_META.country_incidence} size={10} />
                <span className="text-[11px] text-txt-muted font-mono mb-1">per 1,000 pop at risk</span>
              </div>
            </div>
          </div>

          {/* Interventions */}
          {(country.llin_coverage != null || country.irs_coverage != null || country.act_coverage != null) && (
            <div>
              <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em] mb-3">Intervention Coverage</p>
              <div className="space-y-2.5">
                {country.llin_coverage != null && (
                  <CoverageBar label="ITN / LLIN use" value={country.llin_coverage} meta={METRIC_META.llin_coverage} />
                )}
                {country.irs_coverage != null && (
                  <CoverageBar label="Indoor residual spraying" value={country.irs_coverage} meta={METRIC_META.irs_coverage} />
                )}
                {country.act_coverage != null && (
                  <CoverageBar label="ACT treatment" value={country.act_coverage} meta={METRIC_META.act_coverage} />
                )}
              </div>
            </div>
          )}

          {/* Funding */}
          {country.funding_per_capita != null && (
            <div>
              <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em] mb-2">Financing</p>
              <div className="bg-surface-1 rounded-[14px] p-3 flex items-center justify-between">
                <span className="text-[12px] text-txt-secondary">External funding / capita</span>
                <div className="flex items-center">
                  <span className="font-mono font-semibold text-[15px] text-txt-primary">
                    ${country.funding_per_capita.toFixed(2)}
                  </span>
                  <InfoTooltip meta={METRIC_META.funding_per_capita} size={10} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer CTA */}
        <div className="px-5 py-4 border-t border-surface-2 shrink-0">
          <p className="text-[10px] text-txt-muted font-mono mb-3">
            Sources: WHO WMR 2024 · Global Fund API · WHO GHED
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ── Main canvas ───────────────────────────────────────────────────────────── */
export function CommandCanvas({ summary, countries, threats, boundaries }: Props) {
  const g       = summary.global;
  const router  = useRouter();
  const lookup  = new Map(countries.map((c) => [c.iso3, c]));

  const [selected, setSelected] = useState<CommandCountrySummary | null>(null);

  function handleCountryClick(iso3: string) {
    const c = lookup.get(iso3);
    if (c) setSelected(c);
  }

  return (
    <div
      className="relative w-full overflow-hidden"
      style={{ height: "calc(100vh - 64px)" }}
    >
      {/* ── Full-viewport map ── */}
      <div className="absolute inset-0">
        <GlobalIntelMap
          countries={countries}
          threats={threats}
          boundaries={boundaries}
          onCountryClick={handleCountryClick}
        />
      </div>

      {/* ── Top-left: headline ── */}
      <motion.div
        className="absolute top-5 left-5 z-10 max-w-sm pointer-events-none"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
      >
        <div className="inline-flex items-center gap-2 bg-white/80 backdrop-blur-sm border border-surface-3 rounded-pill px-3 py-1 mb-2 pointer-events-auto">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse-slow" />
          <span className="text-[10px] font-mono text-txt-muted uppercase tracking-[0.1em]">
            Global Intelligence · WHO WMR 2024
          </span>
        </div>
        <h1
          className="font-gothic text-txt-primary uppercase pointer-events-auto"
          style={{ fontSize: "clamp(28px, 3.5vw, 48px)", lineHeight: 1.05, fontSynthesis: "none" }}
        >
          The curve has bent<br />the wrong way.
        </h1>
      </motion.div>

      {/* ── Top-right: layer toggle ── */}
      <motion.div
        className="absolute top-5 right-5 z-10"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.4 }}
      >
        <LayerToggle />
      </motion.div>

      {/* ── Bottom-left: KPI chips ── */}
      <motion.div
        className="absolute bottom-5 left-5 z-10 flex gap-2.5 flex-wrap"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.5 }}
      >
        <KpiChip label="Estimated Cases"   value={fmt(g.estimated_cases)}  change={g.cases_change_yoy} meta={METRIC_META.global_cases} />
        <KpiChip label="Estimated Deaths"  value={fmt(g.estimated_deaths)} change={g.deaths_change_yoy ?? null} meta={METRIC_META.global_deaths} />
        <KpiChip label="Endemic Countries" value={String(g.countries_endemic)} sub={`${g.countries_in_alert} in alert`} meta={METRIC_META.endemic_countries} />
      </motion.div>

      {/* ── Bottom-right: Follow the money ── */}
      <motion.button
        onClick={() => router.push("/investment")}
        className="absolute bottom-5 right-5 z-10 flex items-center gap-2 bg-white/90 backdrop-blur-md border border-surface-3 rounded-[14px] px-4 py-2.5 shadow-card hover:shadow-card-hover hover:bg-white transition-all duration-200 group"
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.7 }}
      >
        <span className="text-[11px] font-mono text-txt-secondary uppercase tracking-[0.08em] group-hover:text-txt-primary transition-colors">
          Follow the money
        </span>
        <ArrowUpRight size={14} className="text-txt-muted group-hover:text-txt-primary transition-colors" />
      </motion.button>

      {/* ── Click hint ── */}
      <motion.div
        className="absolute bottom-[60px] left-1/2 -translate-x-1/2 z-10 pointer-events-none"
        initial={{ opacity: 0 }}
        animate={{ opacity: selected ? 0 : 0.7 }}
        transition={{ duration: 0.4, delay: 1.5 }}
      >
        <div className="bg-white/80 backdrop-blur-sm border border-surface-3 rounded-pill px-3 py-1.5">
          <span className="text-[10px] font-mono text-txt-muted uppercase tracking-[0.1em]">
            Click any country for details
          </span>
        </div>
      </motion.div>

      {/* ── Country detail modal ── */}
      <AnimatePresence>
        {selected && (
          <CountryModal
            country={selected}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
