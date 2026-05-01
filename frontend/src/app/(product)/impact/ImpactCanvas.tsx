"use client";

import { useEffect, useRef, useState } from "react";
import { scaleLinear } from "d3";
import type { ImpactResults, CaseTrendsData } from "@/lib/data";
import { ChapterHero } from "@/components/ui/ChapterHero";
import { KPICard } from "@/components/ui/KPICard";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { METRIC_META } from "@/lib/metric-metadata";

// ── In-view hook ──────────────────────────────────────────────────────────────

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setInView(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, inView };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCost(n: number): string {
  return "$" + n.toLocaleString();
}

function fmtCostAxis(n: number): string {
  if (n === 0) return "$0";
  return `$${(n / 1000).toFixed(0)}K`;
}

// ── Cost Effectiveness Chart ──────────────────────────────────────────────────

const CHART_MAX = 48000;
const BAR_H = 28;
const BAR_GAP = 8;
const LABEL_W = 160;
const VALUE_W = 68;
const CHART_INNER_W = 420;

function CostEffectivenessChart({
  data,
}: {
  data: ImpactResults["cost_vs_comparators"];
}) {
  const gridLines = [0, 10000, 20000, 30000, 40000, CHART_INNER_W === 420 ? 48000 : 50000];
  const totalH = data.length * (BAR_H + BAR_GAP) + 40; // +40 for x-axis

  return (
    <div className="glass-panel p-5">
      <div className="flex" style={{ gap: 0 }}>
        {/* Left labels */}
        <div
          className="flex-shrink-0 flex flex-col"
          style={{ width: LABEL_W, gap: BAR_GAP }}
        >
          {/* spacer for top padding */}
          <div style={{ height: 8 }} />
          {data.map((item) => (
            <div
              key={item.intervention}
              className="flex items-center"
              style={{ height: BAR_H }}
            >
              <span className="text-xs text-txt-secondary truncate leading-tight">
                {item.intervention}
              </span>
            </div>
          ))}
        </div>

        {/* SVG chart */}
        <div className="flex-1 min-w-0">
          <svg
            width="100%"
            viewBox={`0 0 ${CHART_INNER_W} ${totalH}`}
            preserveAspectRatio="xMinYMid meet"
            className="overflow-visible"
            style={{ height: totalH }}
          >
            {/* Grid lines */}
            {[0, 10000, 20000, 30000, 40000, 48000].map((v) => {
              const x = (v / CHART_MAX) * CHART_INNER_W;
              return (
                <g key={v}>
                  <line
                    x1={x}
                    y1={8}
                    x2={x}
                    y2={totalH - 32}
                    stroke="#e8e8e8"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                  <text
                    x={x}
                    y={totalH - 14}
                    textAnchor="middle"
                    style={{
                      fontSize: 9,
                      fontFamily: "'IBM Plex Mono', monospace",
                      fill: "#999",
                    }}
                  >
                    {fmtCostAxis(v)}
                  </text>
                </g>
              );
            })}

            {/* Bars */}
            {data.map((item, i) => {
              const isPMI = item.intervention === "PMI Malaria";
              const barW = Math.max(
                2,
                (Math.min(item.cost_usd, CHART_MAX) / CHART_MAX) * CHART_INNER_W
              );
              const y = 8 + i * (BAR_H + BAR_GAP);

              return (
                <g key={item.intervention}>
                  <rect
                    x={0}
                    y={y}
                    width={barW}
                    height={BAR_H}
                    fill={isPMI ? "#5B8FF4" : "#d5d5d5"}
                    rx={3}
                  />
                  {isPMI && (
                    <text
                      x={barW + 6}
                      y={y + BAR_H / 2 + 4}
                      style={{
                        fontSize: 9,
                        fontFamily: "'IBM Plex Mono', monospace",
                        fill: "#5B8FF4",
                        fontWeight: 600,
                      }}
                    >
                      ★ Best value
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Right values */}
        <div
          className="flex-shrink-0 flex flex-col"
          style={{ width: VALUE_W, gap: BAR_GAP }}
        >
          <div style={{ height: 8 }} />
          {data.map((item) => {
            const isPMI = item.intervention === "PMI Malaria";
            return (
              <div
                key={item.intervention}
                className="flex items-center justify-end"
                style={{ height: BAR_H }}
              >
                <span
                  className="text-xs font-mono"
                  style={{ color: isPMI ? "#5B8FF4" : "#888" }}
                >
                  {fmtCost(item.cost_usd)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Country Progress Table ────────────────────────────────────────────────────

function CountryProgressTable({
  data,
}: {
  data: ImpactResults["country_progress"];
}) {
  const maxCases = Math.max(...data.map((r) => Math.max(r.cases_2010, r.cases_2023)));

  // Sort: reductions first (ascending pct_reduction = largest reduction first), then increases
  const sorted = [...data].sort((a, b) => {
    const aPos = a.pct_reduction >= 0;
    const bPos = b.pct_reduction >= 0;
    if (aPos && !bPos) return -1;
    if (!aPos && bPos) return 1;
    if (aPos && bPos) return b.pct_reduction - a.pct_reduction; // biggest reduction first
    return a.pct_reduction - b.pct_reduction; // biggest increase last
  });

  return (
    <div className="glass-panel overflow-hidden">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-surface-3">
            <th className="text-left px-4 py-3 text-2xs font-mono uppercase tracking-widest text-txt-muted font-medium">
              Country
            </th>
            <th className="text-right px-4 py-3 text-2xs font-mono uppercase tracking-widest text-txt-muted font-medium">
              2010 Cases
            </th>
            <th className="text-right px-4 py-3 text-2xs font-mono uppercase tracking-widest text-txt-muted font-medium">
              2023 Cases
            </th>
            <th className="text-right px-4 py-3 text-2xs font-mono uppercase tracking-widest text-txt-muted font-medium">
              Reduction
            </th>
            <th className="px-4 py-3 text-2xs font-mono uppercase tracking-widest text-txt-muted font-medium w-32">
              Progress
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const isReduction = row.pct_reduction >= 0;
            const absPct = Math.abs(row.pct_reduction);
            const barWidth = Math.min(100, absPct);

            return (
              <tr
                key={row.iso3}
                className="border-b border-surface-2 hover:bg-surface-1 transition-colors"
              >
                <td className="px-4 py-2.5 text-txt-primary text-xs font-medium">
                  {row.name}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-txt-secondary tabular-nums">
                  {row.cases_2010.toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-txt-secondary tabular-nums">
                  {row.cases_2023.toLocaleString()}
                </td>
                <td
                  className="px-4 py-2.5 text-right font-mono text-xs tabular-nums font-semibold"
                  style={{ color: isReduction ? "#19bdc3" : "#dc2626" }}
                >
                  {isReduction ? "↓" : "↑"} {absPct.toFixed(0)}%
                </td>
                <td className="px-4 py-2.5">
                  <div className="h-2 bg-surface-2 rounded-full overflow-hidden w-full">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${barWidth}%`,
                        backgroundColor: isReduction ? "#19bdc3" : "#dc2626",
                        opacity: 0.8,
                      }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Case Trend Sparklines ─────────────────────────────────────────────────────

const SPARKLINE_W = 120;
const SPARKLINE_H = 40;

function Sparkline({ values, trend, inView, delay }: {
  values: number[];
  trend: "rising" | "stable" | "declining";
  inView: boolean;
  delay: number;
}) {
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (!inView) return;
    const t = setTimeout(() => setRevealed(true), delay);
    return () => clearTimeout(t);
  }, [inView, delay]);

  const yScale = scaleLinear()
    .domain([Math.min(...values) * 0.95, Math.max(...values) * 1.05])
    .range([SPARKLINE_H - 3, 3]);

  const xStep = SPARKLINE_W / (values.length - 1);
  const points = values.map((v, i) => `${i * xStep},${yScale(v)}`).join(" ");

  const color = trend === "declining" ? "#19bdc3" : trend === "rising" ? "#dc2626" : "#f59e0b";

  return (
    <svg width={SPARKLINE_W} height={SPARKLINE_H} className="overflow-visible">
      <defs>
        <clipPath id={`spark-clip-${delay}`}>
          <rect
            x={0} y={0} height={SPARKLINE_H + 4}
            width={revealed ? SPARKLINE_W + 4 : 0}
            style={{ transition: "width 1.4s cubic-bezier(0.4,0,0.2,1)" }}
          />
        </clipPath>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
        strokeLinecap="round"
        clipPath={`url(#spark-clip-${delay})`}
      />
      {/* Last point dot */}
      <circle
        cx={(values.length - 1) * xStep}
        cy={yScale(values[values.length - 1])}
        r={3}
        fill={color}
        style={{ opacity: revealed ? 1 : 0, transition: "opacity 0.3s 1.4s" }}
      />
    </svg>
  );
}

function CaseTrendSparklines({ trends }: { trends: CaseTrendsData }) {
  const { ref, inView } = useInView(0.1);
  const years = trends._meta.years;
  const first = years[0];
  const last  = years[years.length - 1];

  return (
    <div ref={ref}>
      <div className="grid grid-cols-3 gap-3">
        {trends.countries.map((c, i) => {
          const pctChange = ((c.cases_2023 - c.cases_2010) / c.cases_2010) * 100;
          const isDown = pctChange < 0;
          const fmtCases = (n: number) =>
            n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : `${(n / 1e3).toFixed(0)}K`;

          return (
            <div
              key={c.iso3}
              className="glass-panel p-4"
              style={{
                opacity: inView ? 1 : 0,
                transform: inView ? "none" : "translateY(8px)",
                transition: `opacity 0.4s ${i * 40}ms, transform 0.4s ${i * 40}ms`,
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className="text-xs font-medium text-txt-primary leading-tight">{c.name}</p>
                  <p className="text-2xs font-mono text-txt-muted">{c.iso3}</p>
                </div>
                <span
                  className="text-2xs font-mono font-bold px-1.5 py-0.5 rounded-badge"
                  style={{
                    background: isDown ? "rgba(25,189,195,0.12)" : "rgba(220,38,38,0.10)",
                    color: isDown ? "#19bdc3" : "#dc2626",
                  }}
                >
                  {isDown ? "↓" : "↑"}{Math.abs(pctChange).toFixed(0)}%
                </span>
              </div>

              <Sparkline
                values={c.cases_by_year}
                trend={c.trend}
                inView={inView}
                delay={i * 60}
              />

              <div className="flex justify-between mt-2">
                <div>
                  <p className="text-2xs font-mono text-txt-muted">{first}</p>
                  <p className="text-2xs font-mono text-txt-secondary">{fmtCases(c.cases_2010)}</p>
                </div>
                <div className="text-right">
                  <p className="text-2xs font-mono text-txt-muted">{last}</p>
                  <p className="text-2xs font-mono font-semibold text-txt-primary">{fmtCases(c.cases_2023)}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-2xs font-mono text-txt-muted mt-4 leading-relaxed">
        Source: WHO Global Health Observatory — MALARIA_EST_CASES indicator, point estimates {first}–{last}.
      </p>
    </div>
  );
}

// ── Main Canvas ───────────────────────────────────────────────────────────────

export function ImpactCanvas({ data, trends }: { data: ImpactResults; trends: CaseTrendsData }) {
  const livesSavedFmt = `${(data.lives_saved_total / 1e6).toFixed(1)}M`;
  const casesAvertedFmt = `${(data.cases_averted_annual / 1e6).toFixed(0)}M`;
  const childDeathsFmt = `${(data.child_deaths_prevented / 1e6).toFixed(1)}M`;
  const costPerLifeFmt = `$${data.cost_per_life_saved_usd.toLocaleString()}`;

  return (
    <div className="h-full overflow-y-auto bg-surface-1">
      {/* Section A — Hero */}
      <ChapterHero
        eyebrow="Chapter 04 — The Results"
        headline="WHAT THE INVESTMENT ACHIEVED"
        subheadline="Since 2010, US-funded malaria programs have saved over 2.2 million lives. Here's the evidence — from lives saved to cost per death averted compared to other global health interventions."
        accentColor="#5B8FF4"
      />

      {/* Section B — KPI Cards */}
      <section className="px-8 py-4">
        <div className="grid grid-cols-4 gap-4">
          <KPICard
            label="Lives Saved"
            value={livesSavedFmt}
            subvalue="Since 2010 (PMI-attributed)"
            glowColor="rgba(91,143,244,0.15)"
            accent="#5B8FF4"
            meta={METRIC_META.lives_saved}
          />
          <KPICard
            label="Cases Averted Annually"
            value={casesAvertedFmt}
            subvalue="Per year across PMI countries"
            glowColor="rgba(91,143,244,0.10)"
            accent="#5B8FF4"
            meta={METRIC_META.cases_averted}
          />
          <KPICard
            label="Child Deaths Prevented"
            value={childDeathsFmt}
            subvalue="Under-5 mortality reduction"
            glowColor="rgba(25,189,195,0.12)"
            accent="#19bdc3"
            meta={METRIC_META.child_deaths_prevented}
          />
          <KPICard
            label="Cost Per Life Saved"
            value={costPerLifeFmt}
            subvalue="Among most cost-effective interventions"
            glowColor="rgba(91,143,244,0.10)"
            accent="#5B8FF4"
            meta={METRIC_META.cost_per_death_averted}
          />
        </div>

        {/* Global Fund row */}
        {data.gf_nets_distributed_millions && (
          <div className="mt-3 grid grid-cols-4 gap-4">
            <KPICard
              label="Nets Distributed (GF)"
              value={`${data.gf_nets_distributed_millions}M`}
              subvalue="Insecticide-treated bed nets"
              glowColor="rgba(25,189,195,0.10)"
              accent="#19bdc3"
              meta={METRIC_META.gf_nets_distributed}
            />
            <KPICard
              label="Cases Treated (GF)"
              value={`${data.gf_cases_treated_millions}M`}
              subvalue="Confirmed cases treated"
              glowColor="rgba(25,189,195,0.10)"
              accent="#19bdc3"
              meta={METRIC_META.gf_cases_treated}
            />
            <KPICard
              label="Children via SMC (GF)"
              value={`${data.gf_smc_children_millions}M`}
              subvalue="Seasonal malaria chemoprevention"
              glowColor="rgba(25,189,195,0.10)"
              accent="#19bdc3"
            />
            <KPICard
              label="GF Malaria Disbursed"
              value={`$${((data.gf_malaria_disbursed_usd ?? 0) / 1e9).toFixed(1)}B`}
              subvalue="US-catalyzed Global Fund grants"
              glowColor="rgba(25,189,195,0.10)"
              accent="#19bdc3"
              meta={METRIC_META.gf_disbursed}
            />
          </div>
        )}
      </section>

      {/* Section B2 — Burden Trends */}
      <section className="px-8 py-4">
        <SectionHeader
          step="Burden Trends"
          title="Case Trajectory 2010–2023 — Top 15 Burden Countries"
          subtitle="WHO estimated malaria cases over 13 years. Declining trend (teal) shows US investment is working; rising trend (red) shows where more is needed."
          accentColor="#5B8FF4"
        />
        <CaseTrendSparklines trends={trends} />
      </section>

      {/* Section C — Cost Effectiveness */}
      <section className="px-8 py-4">
        <SectionHeader
          step="Cost Effectiveness"
          title="How Does Malaria Compare?"
          subtitle="Cost per life saved — lower is better. PMI malaria programs are among the most cost-effective health investments in the world."
          accentColor="#5B8FF4"
        />
        <CostEffectivenessChart data={data.cost_vs_comparators} />
      </section>

      {/* Section D — Country Progress */}
      <section className="px-8 py-4">
        <SectionHeader
          step="Country Progress"
          title="Progress in PMI Countries"
          subtitle="Change in malaria cases 2010–2023 across US priority countries. Most show significant reduction."
          accentColor="#5B8FF4"
        />
        <CountryProgressTable data={data.country_progress} />
      </section>

      {/* Section E — Accountability Note */}
      <section className="px-8 py-4 pb-8">
        <div className="bg-surface-2 rounded-panel p-5">
          <p className="text-sm font-semibold text-txt-primary mb-2">Methodology</p>
          <p className="text-sm text-txt-muted leading-relaxed">
            Impact figures are drawn from PMI&apos;s annual Congressional Budget Justifications
            and peer-reviewed attribution analyses. &ldquo;Lives saved&rdquo; reflects PMI&apos;s modeled
            attribution using the Lives Saved Tool (LiST). All cost figures are in constant 2023 USD.
          </p>
        </div>
      </section>
    </div>
  );
}
