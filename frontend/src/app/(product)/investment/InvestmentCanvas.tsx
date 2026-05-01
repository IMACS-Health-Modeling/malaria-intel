"use client";

import { useRef, useEffect, useState } from "react";
import {
  scaleLinear,
  scalePoint,
  area as d3Area,
  stack,
  stackOrderNone,
  stackOffsetNone,
  curveMonotoneX,
  type SeriesPoint,
} from "d3";
import type { InvestmentOverview, GeographicSpendData } from "@/lib/data";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { METRIC_META } from "@/lib/metric-metadata";
import type { MetricMeta } from "@/lib/metric-metadata";

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1800, started = true): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>(0);
  useEffect(() => {
    if (!started) { setValue(0); return; }
    const startTime = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) rafRef.current = requestAnimationFrame(step);
      else setValue(target);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, started]);
  return value;
}

function useInView(threshold = 0.2) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setInView(true); observer.disconnect(); } },
      { threshold }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);
  return { ref, inView };
}

// ── Formatters ────────────────────────────────────────────────────────────────

const fmtB   = (n: number) => `$${(n / 1e9).toFixed(1)}B`;
const fmtM   = (n: number) => `$${(n / 1e6).toFixed(0)}M`;
const fmtK   = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(0)}K` : `$${n}`;
const fmtNum = (n: number) => n.toLocaleString();

// ── Section header ─────────────────────────────────────────────────────────────

function SectionLabel({ eyebrow, headline, accent = "#ED7238" }: {
  eyebrow: string; headline: string; accent?: string;
}) {
  return (
    <div className="mb-5">
      <p className="text-2xs font-mono uppercase tracking-[0.15em] mb-1" style={{ color: accent }}>
        {eyebrow}
      </p>
      <h2 className="text-lg font-bold text-txt-primary leading-tight">{headline}</h2>
    </div>
  );
}

// ── Animated Hero KPI (must be its own component — uses hook) ─────────────────

function AnimatedHeroKPI({ label, raw, display, accent, sub, meta }: {
  label: string; raw: number; display: (n: number) => string; accent: string; sub: string; meta?: MetricMeta;
}) {
  const count = useCountUp(raw, 1600, true);
  return (
    <div className="px-5 py-4 border-r border-white/10 last:border-r-0">
      <p className="text-2xs font-mono uppercase tracking-[0.1em] text-white/50 mb-1">{label}</p>
      <div className="flex items-center">
        <p className="text-2xl font-mono font-bold leading-none tabular-nums" style={{ color: accent }}>
          {display(count)}
        </p>
        {meta && <InfoTooltip meta={meta} size={11} className="opacity-60 hover:opacity-100" />}
      </div>
      <p className="text-2xs font-mono text-white/40 mt-1">{sub}</p>
    </div>
  );
}

// ── PMI Track Record Card ─────────────────────────────────────────────────────

function PMITrackRecord({ pmiAnnualUsd }: { pmiAnnualUsd: number }) {
  const yearsActive = new Date().getFullYear() - 2005;
  return (
    <div className="flex items-center gap-4 px-5 py-4 rounded-panel border border-accent-orange/25 bg-accent-orange/5">
      <div className="shrink-0 text-center">
        <p className="text-4xl font-mono font-black text-accent-orange leading-none">{yearsActive}</p>
        <p className="text-2xs font-mono text-txt-muted mt-1">years active</p>
      </div>
      <div className="w-px h-10 bg-accent-orange/20 shrink-0" />
      <div>
        <p className="text-xs font-mono font-semibold text-txt-primary">
          President's Malaria Initiative
        </p>
        <p className="text-2xs font-mono text-txt-muted mt-1 leading-relaxed">
          FY2024 Congressional appropriation: <strong className="text-accent-orange">{fmtM(pmiAnnualUsd)}</strong>
          <br />Source: PMI FY2024 Annual Report · USAID</p>
      </div>
    </div>
  );
}

// ── Stacked Area Chart ─────────────────────────────────────────────────────────

const STACK_KEYS  = ["nih", "gf", "pmi"] as const;
const STACK_COLORS: Record<string, string> = {
  nih: "#5B8FF4", gf: "#19bdc3", pmi: "#ED7238",
};
const STACK_LABELS: Record<string, string> = {
  pmi: "PMI — Malaria", gf: "US → Global Fund", nih: "NIH R&D",
};

type YearRow = { year: number; pmi: number; gf: number; nih: number };
const CHART_H = 250;
const M = { top: 22, right: 24, bottom: 36, left: 58 };

function StackedAreaChart({
  years, milestones,
}: {
  years: YearRow[];
  milestones: { year: number; label: string }[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth]       = useState(900);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    ro.observe(el);
    setWidth(el.clientWidth || 900);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setRevealed(true), 350);
    return () => clearTimeout(t);
  }, []);

  const innerW = width - M.left - M.right;
  const innerH = CHART_H - M.top - M.bottom;

  const xScale = scalePoint<string>()
    .domain(years.map(d => String(d.year)))
    .range([0, innerW])
    .padding(0.5);

  const maxVal = Math.max(...years.map(d => d.pmi + d.gf + d.nih));
  const yScale = scaleLinear().domain([0, maxVal * 1.08]).range([innerH, 0]).nice();

  const stackGen = stack<YearRow>()
    .keys([...STACK_KEYS])
    .order(stackOrderNone)
    .offset(stackOffsetNone);
  const series = stackGen(years);

  const areaGen = d3Area<SeriesPoint<YearRow>>()
    .x(d => xScale(String(d.data.year)) ?? 0)
    .y0(d => yScale(d[0]))
    .y1(d => yScale(d[1]))
    .curve(curveMonotoneX);

  const yTicks = yScale.ticks(5);
  const validMilestones = milestones.filter(m => m.year >= 2010);

  return (
    <div ref={containerRef} className="w-full">
      <svg width={width} height={CHART_H} className="overflow-visible">
        <defs>
          <clipPath id="area-reveal">
            <rect
              x={0} y={0} height={CHART_H + 20}
              width={revealed ? innerW + 40 : 0}
              style={{ transition: "width 2s cubic-bezier(0.4,0,0.2,1)" }}
            />
          </clipPath>
          {STACK_KEYS.map(k => (
            <linearGradient key={k} id={`grad-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={STACK_COLORS[k]} stopOpacity={0.88} />
              <stop offset="100%" stopColor={STACK_COLORS[k]} stopOpacity={0.55} />
            </linearGradient>
          ))}
        </defs>

        <g transform={`translate(${M.left},${M.top})`}>
          {/* Y gridlines */}
          {yTicks.map(t => (
            <g key={t} transform={`translate(0,${yScale(t)})`}>
              <line x1={0} x2={innerW} stroke="#e8edf4" strokeWidth={1} />
              <text x={-8} y={4} textAnchor="end" fill="#9baab8"
                style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace" }}>
                {fmtB(t)}
              </text>
            </g>
          ))}

          {/* Stacked areas — reveal left to right */}
          <g clipPath="url(#area-reveal)">
            {series.map(s => (
              <path key={s.key} d={areaGen(s) ?? ""} fill={`url(#grad-${s.key})`} />
            ))}
          </g>

          {/* Milestone markers */}
          {validMilestones.map(m => {
            const x = xScale(String(m.year)) ?? 0;
            return (
              <g key={m.year} transform={`translate(${x},0)`}>
                <line y1={0} y2={innerH} stroke="#1d499e" strokeWidth={1}
                  strokeDasharray="3,3" opacity={0.45} />
                <circle cy={2} r={3} fill="#1d499e" opacity={0.7} />
                <text y={-6} textAnchor="middle" fill="#1d499e" fontWeight={600}
                  style={{ fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }}>
                  {m.label}
                </text>
              </g>
            );
          })}

          {/* X axis labels */}
          {years.filter((_, i) => i % 2 === 0 || i === years.length - 1).map(d => (
            <text key={d.year}
              x={xScale(String(d.year)) ?? 0} y={innerH + 20}
              textAnchor="middle" fill="#9baab8"
              style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace" }}>
              {d.year}
            </text>
          ))}

          <line x1={0} x2={innerW} y1={innerH} y2={innerH} stroke="#d5dde8" strokeWidth={1} />
        </g>
      </svg>

      <div className="flex items-center gap-6 mt-2 ml-14">
        {(["pmi", "gf", "nih"] as const).map(k => (
          <div key={k} className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: STACK_COLORS[k] }} />
            <span className="text-2xs font-mono text-txt-muted">{STACK_LABELS[k]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Peer Comparison ────────────────────────────────────────────────────────────

function PeerComparison({ donors }: { donors: InvestmentOverview["donors"] }) {
  const { ref, inView } = useInView(0.15);
  const maxUsd = donors[0].total_usd;

  return (
    <div ref={ref}>
      <SectionLabel
        eyebrow="Global Leadership"
        headline="America Funds 1 in 3 Global Health Dollars"
        accent="#1d499e"
      />
      <div className="space-y-2.5">
        {donors.map((d, i) => {
          const isUS = d.name === "United States";
          const pct  = (d.total_usd / maxUsd) * 100;
          return (
            <div key={d.name} className="flex items-center gap-2.5">
              <span className="text-base w-6 shrink-0 leading-none">{d.flag}</span>
              <span className="text-xs font-mono shrink-0 w-28 truncate"
                style={{ color: isUS ? "#1d499e" : "#6b7a8d", fontWeight: isUS ? 700 : 400 }}>
                {d.name}
              </span>
              <div className="flex-1 h-6 bg-surface-2 rounded-sm overflow-hidden relative">
                <div
                  className="h-full rounded-sm absolute left-0 top-0 flex items-center"
                  style={{
                    width: inView ? `${pct}%` : "0%",
                    background: isUS ? "#1d499e" : "#8daad8",
                    transition: `width 1.1s cubic-bezier(0.4,0,0.2,1) ${i * 70}ms`,
                    minWidth: inView && pct > 15 ? 80 : 0,
                  }}
                >
                  {isUS && (
                    <span className="text-2xs font-mono font-bold text-white ml-auto mr-2 whitespace-nowrap"
                      style={{ opacity: inView ? 1 : 0, transition: `opacity 0.4s ${i * 70 + 900}ms` }}>
                      #1 · {d.share_pct}%
                    </span>
                  )}
                </div>
              </div>
              <span className="text-2xs font-mono text-txt-muted shrink-0 w-12 text-right tabular-nums">
                {fmtB(d.total_usd)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-2xs font-mono text-txt-muted mt-4 pt-3 border-t border-surface-3 leading-relaxed">
        Source: OECD DAC1 — Cumulative health ODA to LMICs, 2010–2024.
        Includes bilateral + multilateral contributions.
      </p>
    </div>
  );
}

// ── Disease Portfolio + Efficiency ────────────────────────────────────────────

function PortfolioSection({ split, efficiency }: {
  split: InvestmentOverview["disease_split"];
  efficiency: InvestmentOverview["disease_efficiency"];
}) {
  const { ref, inView } = useInView(0.1);
  const COLORS: Record<string, string> = {
    "HIV/AIDS (PEPFAR)":  "#dc2626",
    "Malaria (PMI)":      "#ED7238",
    "TB (USAID)":         "#7c3aed",
    "Other Global Health":"#c2c9d4",
  };

  return (
    <div ref={ref}>
      <SectionLabel
        eyebrow="The Portfolio"
        headline="Where Every Dollar Goes — and the ROI Case"
        accent="#ED7238"
      />

      {/* Segmented bar */}
      <div className="h-9 w-full flex rounded-panel overflow-hidden mb-2">
        {split.map((d, i) => (
          <div key={d.disease}
            style={{
              width: inView ? `${d.pct}%` : "0%",
              background: COLORS[d.disease] ?? "#ccc",
              transition: `width 1.2s cubic-bezier(0.4,0,0.2,1) ${i * 100}ms`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
            title={`${d.disease}: ${d.pct}%`}
          >
            {d.pct > 10 && (
              <span className="text-2xs font-mono font-bold text-white">{d.pct}%</span>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-5">
        {split.map(d => (
          <div key={d.disease} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: COLORS[d.disease] ?? "#ccc" }} />
            <span className="text-2xs font-mono text-txt-muted">
              {d.disease} <strong className="text-txt-primary">{d.pct}%</strong>
            </span>
          </div>
        ))}
      </div>

      {/* ROI callout */}
      <div className="bg-accent-orange/8 border border-accent-orange/25 rounded-panel px-4 py-3 mb-5">
        <p className="text-xs font-mono font-semibold text-accent-orange mb-1">The ROI Case for Malaria</p>
        <p className="text-xs text-txt-secondary leading-relaxed">
          Malaria gets only <strong className="text-accent-orange">7.7¢</strong> of every US global health dollar —
          yet delivers the <strong>lowest cost per death averted</strong> of any infectious disease program.
          That makes it the highest-value investment in the portfolio.
        </p>
      </div>

      {/* Efficiency bars */}
      <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted mb-3">
        Cost to Avert One Death — Comparative Efficiency
      </p>
      <div className="space-y-2.5">
        {efficiency.map((e, i) => {
          const maxCost = 28000;
          const barPct  = (e.cost_per_death_averted_usd / maxCost) * 100;
          return (
            <div key={e.disease}
              className="flex items-center gap-3 p-3 rounded-panel border"
              style={{
                borderColor: e.badge ? `${e.color}40` : "#e8edf4",
                background:  e.badge ? `${e.color}08` : "transparent",
                opacity:   inView ? 1 : 0,
                transform: inView ? "none" : "translateY(8px)",
                transition: `opacity 0.5s ${i * 120}ms, transform 0.5s ${i * 120}ms`,
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-xs font-mono font-semibold text-txt-primary">{e.disease}</span>
                  {e.badge && (
                    <span className="text-2xs font-mono font-bold px-1.5 py-0.5 rounded-badge text-white"
                      style={{ background: e.color }}>
                      {e.badge}
                    </span>
                  )}
                </div>
                <div className="h-2 w-full bg-surface-2 rounded-pill overflow-hidden">
                  <div className="h-full rounded-pill"
                    style={{
                      width: inView ? `${barPct}%` : "0%",
                      background: e.color,
                      transition: `width 1s cubic-bezier(0.4,0,0.2,1) ${i * 120 + 300}ms`,
                    }}
                  />
                </div>
              </div>
              <div className="text-right shrink-0 ml-3">
                <div className="flex items-center justify-end">
                  <p className="text-base font-mono font-bold" style={{ color: e.color }}>
                    {fmtK(e.cost_per_death_averted_usd)}
                  </p>
                  <InfoTooltip meta={METRIC_META.cost_per_death_averted} size={10} />
                </div>
                <p className="text-2xs font-mono text-txt-muted">per death averted</p>
                <p className="text-2xs font-mono text-txt-muted">{e.pct_children}% children</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── The Multiplier ─────────────────────────────────────────────────────────────

function MultiplierViz({ leverage }: { leverage: InvestmentOverview["leverage"] }) {
  const { ref, inView } = useInView(0.2);
  const total = leverage.components.reduce((s, c) => s + c.ratio, 0);

  return (
    <div ref={ref}>
      <SectionLabel
        eyebrow="The Leverage Effect"
        headline={`$1 US Catalyzes $${leverage.pmi_ratio.toFixed(1)} in Total Investment`}
        accent="#19bdc3"
      />

      {/* Dollar in → Total out */}
      <div className="flex items-center gap-3 mb-6">
        <div style={{ opacity: inView ? 1 : 0, transform: inView ? "none" : "scale(0.8)", transition: "opacity 0.5s, transform 0.5s" }}>
          <div className="w-16 h-16 rounded-panel border-2 border-accent-orange flex items-center justify-center bg-accent-orange/10">
            <span className="text-xl font-mono font-bold text-accent-orange">$1</span>
          </div>
          <p className="text-2xs font-mono text-txt-muted mt-1 text-center">US PMI</p>
        </div>

        <div className="flex-1 relative"
          style={{ opacity: inView ? 1 : 0, transition: "opacity 0.4s 0.35s" }}>
          <div className="h-0.5 w-full bg-gradient-to-r from-accent-orange to-accent-teal" />
          <div className="absolute right-0 top-1/2 -translate-y-1/2 border-t-2 border-r-2 border-accent-teal w-2.5 h-2.5 rotate-45" />
          <p className="text-2xs font-mono text-txt-muted text-center mt-1">catalyzes</p>
        </div>

        <div style={{ opacity: inView ? 1 : 0, transform: inView ? "none" : "scale(0.8)", transition: "opacity 0.5s 0.3s, transform 0.5s 0.3s" }}>
          <div className="w-20 h-20 rounded-panel border-2 border-accent-teal flex items-center justify-center bg-accent-teal/10">
            <span className="text-2xl font-mono font-bold text-accent-teal">${leverage.pmi_ratio.toFixed(1)}</span>
          </div>
          <p className="text-2xs font-mono text-txt-muted mt-1 text-center">Total Impact</p>
        </div>
      </div>

      {/* Stacked breakdown */}
      <div className="space-y-2">
        {leverage.components.map((c, i) => (
          <div key={c.label} className="flex items-center gap-3">
            <div className="h-7 rounded-sm flex items-center px-2 shrink-0 overflow-hidden"
              style={{
                width: inView ? `${(c.ratio / total) * 90}%` : "0%",
                background: c.color,
                minWidth: inView ? 52 : 0,
                transition: `width 1s cubic-bezier(0.4,0,0.2,1) ${i * 110}ms, min-width 1s ${i * 110}ms`,
              }}
            >
              <span className="text-2xs font-mono font-bold text-white whitespace-nowrap">
                ${c.ratio.toFixed(2)}
              </span>
            </div>
            <span className="text-2xs font-mono text-txt-muted">{c.label}</span>
          </div>
        ))}
      </div>

      <p className="text-2xs font-mono text-txt-muted mt-4 italic leading-relaxed">
        {leverage.description}
      </p>
    </div>
  );
}

// ── Channel Split ──────────────────────────────────────────────────────────────

function ChannelSplit({ channel }: { channel: InvestmentOverview["channel"] }) {
  const { ref, inView } = useInView(0.2);
  return (
    <div ref={ref} className="mt-6 pt-5 border-t border-surface-3">
      <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted mb-3">Delivery Channels</p>
      <div className="h-7 w-full flex rounded-sm overflow-hidden mb-2">
        <div className="h-full bg-accent-orange flex items-center justify-center"
          style={{
            width: inView ? `${channel.bilateral_pct}%` : "0%",
            transition: "width 1.2s cubic-bezier(0.4,0,0.2,1)",
          }}>
          <span className="text-2xs font-mono font-bold text-white">{channel.bilateral_pct}%</span>
        </div>
        <div className="h-full bg-accent-teal flex items-center justify-center"
          style={{
            width: inView ? `${channel.multilateral_pct}%` : "0%",
            transition: "width 1.2s cubic-bezier(0.4,0,0.2,1) 0.1s",
          }}>
          <span className="text-2xs font-mono font-bold text-white">{channel.multilateral_pct}%</span>
        </div>
      </div>
      <div className="flex gap-5">
        {[
          ["#ED7238", "Bilateral (PMI / PEPFAR / USAID TB)"],
          ["#19bdc3", "Multilateral (Global Fund)"],
        ].map(([color, label]) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: color }} />
            <span className="text-2xs font-mono text-txt-muted">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Congressional Accountability ──────────────────────────────────────────────

const AUTH_H = 210;
const AM = { top: 12, right: 12, bottom: 36, left: 58 };

function AuthVsDeployed({ data }: { data: InvestmentOverview["authorized_vs_deployed"] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { ref: sectionRef, inView } = useInView(0.15);
  const [width, setWidth] = useState(500);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    ro.observe(el);
    setWidth(el.clientWidth || 500);
    return () => ro.disconnect();
  }, []);

  const innerW = width - AM.left - AM.right;
  const innerH = AUTH_H - AM.top - AM.bottom;
  const maxVal = Math.max(...data.flatMap(d => [d.authorized, d.deployed]));
  const yScale = scaleLinear().domain([0, maxVal * 1.12]).range([innerH, 0]).nice();
  const groupW = innerW / data.length;
  const barW   = Math.max(3, groupW * 0.3);
  const gap    = Math.max(1, groupW * 0.06);
  const yTicks = yScale.ticks(4);

  const totalAuth  = data.reduce((s, d) => s + d.authorized, 0);
  const totalDeploy = data.reduce((s, d) => s + d.deployed, 0);
  const execRate   = ((totalDeploy / totalAuth) * 100).toFixed(1);

  return (
    <div ref={sectionRef}>
      <div className="flex items-start justify-between mb-4">
        <SectionLabel
          eyebrow="Congressional Accountability"
          headline="Authorized vs Deployed — 2010–2024"
          accent="#1d499e"
        />
        <div className="text-right shrink-0 ml-4 mt-1">
          <p className="text-2xs font-mono text-txt-muted">15-yr Execution Rate</p>
          <p className="text-3xl font-mono font-bold text-emerald-600 leading-none">{execRate}%</p>
          <p className="text-2xs font-mono text-emerald-600 mt-0.5">Most faithfully deployed</p>
        </div>
      </div>

      <div ref={containerRef} className="w-full">
        <svg width={width} height={AUTH_H} className="overflow-visible">
          <g transform={`translate(${AM.left},${AM.top})`}>
            {yTicks.map(t => (
              <g key={t} transform={`translate(0,${yScale(t)})`}>
                <line x1={0} x2={innerW} stroke="#e8edf4" strokeWidth={1} />
                <text x={-6} y={4} textAnchor="end" fill="#9baab8"
                  style={{ fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }}>
                  {fmtM(t)}
                </text>
              </g>
            ))}

            {data.map((d, i) => {
              const cx = (i + 0.5) * groupW;
              const authH = innerH - yScale(d.authorized);
              const deplH = innerH - yScale(d.deployed);
              return (
                <g key={d.year}>
                  {/* Authorized — navy, scale up from baseline */}
                  <rect
                    x={cx - barW - gap / 2}
                    y={inView ? yScale(d.authorized) : innerH}
                    width={barW}
                    height={inView ? authH : 0}
                    fill="#1d499e" fillOpacity={0.75} rx={1}
                    style={{
                      transition: `y 0.85s cubic-bezier(0.4,0,0.2,1) ${i * 45}ms, height 0.85s cubic-bezier(0.4,0,0.2,1) ${i * 45}ms`,
                    }}
                  />
                  {/* Deployed — orange */}
                  <rect
                    x={cx + gap / 2}
                    y={inView ? yScale(d.deployed) : innerH}
                    width={barW}
                    height={inView ? deplH : 0}
                    fill="#ED7238" fillOpacity={0.85} rx={1}
                    style={{
                      transition: `y 0.85s cubic-bezier(0.4,0,0.2,1) ${i * 45 + 70}ms, height 0.85s cubic-bezier(0.4,0,0.2,1) ${i * 45 + 70}ms`,
                    }}
                  />
                  <text x={cx} y={innerH + 20} textAnchor="middle" fill="#9baab8"
                    style={{ fontSize: 8, fontFamily: "'IBM Plex Mono', monospace" }}>
                    &apos;{String(d.year).slice(2)}
                  </text>
                </g>
              );
            })}

            <line x1={0} x2={innerW} y1={innerH} y2={innerH} stroke="#d5dde8" strokeWidth={1} />
          </g>
        </svg>

        <div className="flex items-center gap-5 mt-1 ml-14">
          {[["#1d499e", "Authorized by Congress"], ["#ED7238", "Deployed (PMI)"]].map(([color, label]) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: color }} />
              <span className="text-2xs font-mono text-txt-muted">{label}</span>
            </div>
          ))}
        </div>

        {/* Gap callout */}
        <div className="mt-4 p-3 bg-surface-1 border border-surface-3 rounded-panel">
          <p className="text-xs font-mono text-txt-muted leading-relaxed">
            <strong className="text-txt-primary">Gap = ${fmtNum(Math.round((totalAuth - totalDeploy) / 1e6))}M</strong> undeployed
            over 15 years — less than 1.5% of authorized funds, the lowest undeployed rate of any
            US foreign assistance program.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Geographic Spend Section ──────────────────────────────────────────────────

// Countries to exclude from recipient view (routing hubs, not direct beneficiaries)
const GEO_EXCLUDE = new Set(["CHE", "USA", "GBR"]);

const REGION_COLORS: Record<string, string> = {
  "Congo (Kinshasa)": "#ED7238",
  "Nigeria":          "#ED7238",
  "Ghana":            "#ED7238",
  "Ethiopia":         "#ED7238",
  "Tanzania":         "#19bdc3",
  "Mozambique":       "#19bdc3",
  "Rwanda":           "#19bdc3",
  "Zambia":           "#19bdc3",
  "Kenya":            "#19bdc3",
  "Malawi":           "#19bdc3",
  "Senegal":          "#1d499e",
  "Burkina Faso":     "#1d499e",
  "Uganda":           "#1d499e",
  "Guinea":           "#1d499e",
  "Madagascar":       "#1d499e",
};

function GeographicSpendSection({ geoSpend }: { geoSpend: GeographicSpendData }) {
  const { ref, inView } = useInView(0.1);

  const countries = geoSpend.by_country
    .filter((c) => !GEO_EXCLUDE.has(c.country_code) && c.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 15);

  const maxAmt = countries[0]?.amount ?? 1;

  return (
    <div ref={ref}>
      <SectionLabel
        eyebrow="Where Dollars Actually Go"
        headline="USAID Malaria Spend by Recipient Country (2019–2024)"
        accent="#ED7238"
      />
      <p className="text-xs font-mono text-txt-muted mb-5 leading-relaxed">
        Actual contract and grant disbursements from USAspending.gov — not allocations.
        Switzerland ($11.8B) and USA ($2.1B) excluded as routing/administrative hubs.
      </p>

      <div className="space-y-2">
        {countries.map((c, i) => {
          const pct = (c.amount / maxAmt) * 100;
          const color = REGION_COLORS[c.country_name] ?? "#8daad8";
          const amtB = c.amount >= 1e8
            ? `$${(c.amount / 1e9).toFixed(2)}B`
            : `$${(c.amount / 1e6).toFixed(0)}M`;

          return (
            <div key={c.country_code} className="flex items-center gap-3"
              style={{
                opacity: inView ? 1 : 0,
                transform: inView ? "none" : "translateX(-12px)",
                transition: `opacity 0.45s ${i * 45}ms, transform 0.45s ${i * 45}ms`,
              }}
            >
              <span className="text-2xs font-mono text-txt-muted w-5 text-right shrink-0">{i + 1}</span>
              <span className="text-xs font-mono text-txt-secondary w-28 truncate shrink-0">{c.country_name}</span>
              <div className="flex-1 h-6 bg-surface-2 rounded-sm overflow-hidden relative">
                <div
                  className="h-full rounded-sm absolute left-0 top-0"
                  style={{
                    width: inView ? `${pct}%` : "0%",
                    background: color,
                    opacity: 0.8,
                    transition: `width 1s cubic-bezier(0.4,0,0.2,1) ${i * 45}ms`,
                  }}
                />
              </div>
              <span className="text-xs font-mono text-txt-muted shrink-0 w-16 text-right tabular-nums">
                {amtB}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-2xs font-mono text-txt-muted mt-4 pt-3 border-t border-surface-3 leading-relaxed">
        Source: USAspending.gov API v2 /search/spending_by_geography/ — USAID malaria keyword
        awards, place of performance, FY2019–2024. Award count data not available in aggregate endpoint.
      </p>
    </div>
  );
}

// ── Main Canvas ───────────────────────────────────────────────────────────────

export function InvestmentCanvas({ data, geoSpend }: { data: InvestmentOverview; geoSpend: GeographicSpendData }) {
  const execRate = (
    data.authorized_vs_deployed.reduce((s, d) => s + d.deployed, 0) /
    data.authorized_vs_deployed.reduce((s, d) => s + d.authorized, 0) * 100
  ).toFixed(1);

  return (
    <div className="h-full overflow-y-auto bg-white">

      {/* ── HERO ─────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-br from-[#0c2151] to-[#1d499e] px-8 py-8 border-b border-white/10">
        <p className="text-2xs font-mono uppercase tracking-[0.18em] text-white/40 mb-2">
          Chapter 01 — The Commitment
        </p>
        <h1 className="text-3xl font-bold text-white mb-2 leading-tight">
          The US Investment in Malaria
        </h1>
        <p className="text-sm text-white/55 font-mono mb-8 max-w-2xl leading-relaxed">
          Fifteen years of sustained commitment — tracking every dollar, every program, and the
          strategic case for continued US leadership in global malaria control.
        </p>

        <div className="grid grid-cols-4 gap-0 bg-white/8 rounded-panel overflow-hidden border border-white/10">
          <AnimatedHeroKPI
            label="Total US Committed"
            raw={Math.round(data.total_committed_usd / 1e8)}
            display={n => `$${(n / 10).toFixed(1)}B`}
            accent="#ffffff" sub="2010–2024 cumulative"
            meta={METRIC_META.total_us_committed}
          />
          <AnimatedHeroKPI
            label="PMI Annual (FY2024)"
            raw={Math.round(data.years[data.years.length - 1].pmi / 1e6)}
            display={n => `$${n}M`}
            accent="#fbbf24" sub="President's Malaria Initiative"
            meta={METRIC_META.pmi_annual}
          />
          <AnimatedHeroKPI
            label="US → Global Fund"
            raw={Math.round(data.gf_us_contribution_usd / 1e8)}
            display={n => `$${(n / 10).toFixed(1)}B`}
            accent="#5eead4" sub="US share of GF contributions"
            meta={METRIC_META.gf_us_contribution}
          />
          <AnimatedHeroKPI
            label="NIH Malaria R&D"
            raw={Math.round(data.nih_annual_avg_usd / 1e6)}
            display={n => `$${n}M/yr`}
            accent="#93c5fd" sub="Research & development"
            meta={METRIC_META.nih_annual}
          />
        </div>
      </div>

      {/* ── GLOBAL CONTEXT STRIP ─────────────────────────────────── */}
      <div className="flex items-stretch divide-x divide-white/8 bg-[#081935] border-b border-white/10">
        {[
          { stat: "249M",  label: "Cases globally (2023)", note: "WHO WMR 2024" },
          { stat: "597K",  label: "Deaths annually",       note: "597,000 — mostly children" },
          { stat: "76%",   label: "Deaths in children",    note: "Under age 5" },
          { stat: "94%",   label: "Deaths in Africa",      note: "Sub-Saharan Africa" },
          { stat: "#1",    label: "US donor — 34% of aid", note: "More than next 3 combined" },
        ].map(({ stat, label, note }) => (
          <div key={label} className="flex-1 px-5 py-3 text-center">
            <p className="text-lg font-mono font-black text-white leading-none">{stat}</p>
            <p className="text-2xs font-mono text-white/50 mt-0.5">{label}</p>
            <p className="text-2xs font-mono text-white/30 mt-0.5">{note}</p>
          </div>
        ))}
      </div>

      {/* ── PMI TRACK RECORD + STATS ─────────────────────────────── */}
      <div className="px-8 py-4 border-b border-surface-3 bg-surface-1 flex items-center gap-4">
        <PMITrackRecord pmiAnnualUsd={data.years[data.years.length - 1].pmi} />
        <div className="flex-1 px-5 py-4 rounded-panel border border-surface-3 bg-white flex items-center gap-3">
          <div className="text-5xl font-mono font-black text-accent-navy leading-none">
            #{data.us_rank}
          </div>
          <div>
            <p className="text-sm font-bold text-txt-primary">Largest Global Health Donor</p>
            <p className="text-xs font-mono text-txt-muted mt-0.5">
              US contributes{" "}
              <strong className="text-accent-navy">{data.us_donor_share_pct}%</strong> of all OECD
              health ODA — more than the next 3 donors combined
            </p>
          </div>
        </div>
        <div className="px-5 py-4 rounded-panel border border-surface-3 bg-white text-center shrink-0">
          <p className="text-2xs font-mono text-txt-muted mb-1">Congressional Execution</p>
          <p className="text-3xl font-mono font-bold text-emerald-600 leading-none">{execRate}%</p>
          <p className="text-2xs font-mono text-txt-muted mt-1">of authorized funds deployed</p>
        </div>
      </div>

      {/* ── TIMELINE ─────────────────────────────────────────────── */}
      <section className="px-8 py-7 border-b border-surface-3">
        <SectionLabel
          eyebrow="The 15-Year Story"
          headline="Sustained Growth Across Three US Funding Streams"
          accent="#ED7238"
        />
        <StackedAreaChart years={data.years} milestones={data.milestones} />
      </section>

      {/* ── PEERS + PORTFOLIO ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 divide-x divide-surface-3 border-b border-surface-3">
        <section className="px-8 py-7">
          <PeerComparison donors={data.donors} />
        </section>
        <section className="px-8 py-7">
          <PortfolioSection split={data.disease_split} efficiency={data.disease_efficiency} />
        </section>
      </div>

      {/* ── MULTIPLIER + AUTH vs DEPLOYED ─────────────────────────── */}
      <div className="grid grid-cols-2 divide-x divide-surface-3 border-b border-surface-3">
        <section className="px-8 py-7">
          <MultiplierViz leverage={data.leverage} />
          <ChannelSplit channel={data.channel} />

          {/* GF investment callout */}
          <div className="mt-6 pt-5 border-t border-surface-3">
            <p className="text-2xs font-mono uppercase tracking-[0.12em] text-txt-muted mb-3">
              US → Global Fund Investment
            </p>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "US Total to GF",  value: `$${(data.gf_us_contribution_usd / 1e9).toFixed(1)}B`,  color: "#1d499e", meta: METRIC_META.gf_us_contribution },
                { label: "GF Malaria Disbursed", value: `$${(data.gf_malaria_disbursed_usd / 1e9).toFixed(1)}B`, color: "#19bdc3", meta: METRIC_META.gf_disbursed },
                { label: "US Share of GF", value: `${data.us_donor_share_pct}%`, color: "#ED7238", meta: METRIC_META.gf_us_contribution },
              ].map((item) => (
                <div key={item.label} className="bg-surface-1 rounded-panel p-3 border border-surface-3 text-center">
                  <p className="text-2xs font-mono text-txt-muted mb-1 leading-tight">{item.label}</p>
                  <div className="flex items-center justify-center">
                    <p className="text-base font-mono font-bold" style={{ color: item.color }}>{item.value}</p>
                    <InfoTooltip meta={item.meta} size={10} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="px-8 py-7">
          <AuthVsDeployed data={data.authorized_vs_deployed} />
        </section>
      </div>

      {/* ── GEOGRAPHIC SPEND ──────────────────────────────────────── */}
      <section className="px-8 py-7 border-b border-surface-3">
        <GeographicSpendSection geoSpend={geoSpend} />
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────── */}
      <div className="px-8 py-5 bg-surface-1 border-t border-surface-3">
        <p className="text-2xs font-mono text-txt-muted leading-relaxed">
          <strong>Sources:</strong> PMI Annual Reports FY2010–2024 · PEPFAR Congressional
          Appropriations · OECD DAC1 Health ODA Database · Global Fund Financial Report 2024 ·
          NIH RePORTER · WHO World Malaria Report 2024 · Lancet Infectious Diseases
          (cost-effectiveness estimates) · ForeignAssistance.gov
        </p>
      </div>
    </div>
  );
}
