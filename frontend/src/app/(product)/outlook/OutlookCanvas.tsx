"use client";

import { useEffect, useRef, useState } from "react";
import type { OutlookData } from "@/lib/data";
import { ChapterHero } from "@/components/ui/ChapterHero";
import { SectionHeader } from "@/components/ui/SectionHeader";

// ── Hooks ─────────────────────────────────────────────────────────────────────

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

function useCountUp(target: number, duration = 1400, started = true): number {
  const [value, setValue] = useState(0);
  const raf = useRef<number>(0);
  useEffect(() => {
    if (!started) { setValue(0); return; }
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf.current = requestAnimationFrame(step);
      else setValue(target);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration, started]);
  return value;
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtB(n: number): string {
  return `$${(n / 1e9).toFixed(1)}B`;
}

function fmtM(n: number): string {
  return `${(n / 1e6).toFixed(0)}M`;
}

function fmtWhole(n: number): string {
  return n.toLocaleString();
}

// ── Section B — Funding Gap ───────────────────────────────────────────────────

function FundingGapSection({ data }: { data: OutlookData }) {
  const { ref, inView } = useInView(0.15);
  const funded     = data.current_funded_usd;
  const target     = data.who_target_usd;
  const gap        = data.funding_gap_usd;
  const fundedPct  = (funded / target) * 100;

  return (
    <section className="px-8 py-6" ref={ref}>
      <SectionHeader
        step="Global Funding"
        title="The Funding Gap"
        subtitle="WHO recommends $8.3B/year to control and eliminate malaria. Current global funding covers less than half."
        accentColor="#dc2626"
      />
      <div className="glass-panel p-6">
        {/* Animated stacked bar */}
        <div className="relative w-full h-14 rounded-panel overflow-hidden flex mb-2">
          <div
            className="h-full flex items-center justify-center relative flex-shrink-0"
            style={{
              width: inView ? `${fundedPct}%` : "0%",
              background: "#19bdc3",
              transition: "width 1.4s cubic-bezier(0.4,0,0.2,1)",
              minWidth: inView ? 100 : 0,
            }}
          >
            <span className="text-xs font-mono font-semibold text-white px-2 whitespace-nowrap"
              style={{ opacity: inView ? 1 : 0, transition: "opacity 0.4s 1s" }}>
              Funded {fmtB(funded)}
            </span>
          </div>
          <div
            className="h-full flex items-center justify-center flex-1 relative"
            style={{ background: "rgba(220,38,38,0.06)", border: "2px dashed #dc2626" }}
          >
            <span className="text-xs font-mono font-semibold text-red-600 px-2 whitespace-nowrap"
              style={{ opacity: inView ? 1 : 0, transition: "opacity 0.4s 1.4s" }}>
              Gap {fmtB(gap)}
            </span>
          </div>
        </div>
        <div className="flex justify-between mb-5">
          <span className="text-2xs font-mono text-txt-muted">$0</span>
          <span className="text-2xs font-mono text-txt-muted">{fmtB(target)} WHO Target</span>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="bg-surface-1 rounded-panel p-4 text-center border border-surface-3">
            <p className="text-2xs text-txt-muted mb-1">Current Funded</p>
            <p className="text-xl font-mono font-bold" style={{ color: "#19bdc3" }}>{fmtB(funded)}</p>
          </div>
          <div className="bg-surface-1 rounded-panel p-4 text-center border border-surface-3">
            <p className="text-2xs text-txt-muted mb-1">Annual Gap</p>
            <p className="text-xl font-mono font-bold text-red-600">{fmtB(gap)}</p>
          </div>
          <div className="bg-surface-1 rounded-panel p-4 text-center border border-surface-3">
            <p className="text-2xs text-txt-muted mb-1">US Share of Global Funding</p>
            <p className="text-xl font-mono font-bold text-txt-primary">~17%</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Section C — Country Dependency ────────────────────────────────────────────

function CountryDependencySection({
  countries,
}: {
  countries: OutlookData["high_dependency_countries"];
}) {
  return (
    <section className="px-8 py-4">
      <SectionHeader
        step="Dependency Index"
        title="Countries Most Dependent on US Funding"
        subtitle="If US malaria funding were reduced, these countries would face immediate program collapse. They have no alternative donor base of equivalent scale."
        accentColor="#dc2626"
      />

      {/* Warning banner */}
      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-3 mb-4 rounded-r-panel">
        <p className="text-sm text-yellow-800">
          A full US withdrawal from malaria funding would immediately jeopardize over 680,000 lives
          annually and cause an estimated 68 million case rebound.
        </p>
      </div>

      <div className="glass-panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              <th className="text-left text-2xs font-mono text-txt-muted px-4 py-3 uppercase tracking-wider">
                Country
              </th>
              <th className="text-left text-2xs font-mono text-txt-muted px-4 py-3 uppercase tracking-wider w-48">
                US % of Budget
              </th>
              <th className="text-left text-2xs font-mono text-txt-muted px-4 py-3 uppercase tracking-wider">
                At-Risk Programs
              </th>
              <th className="text-left text-2xs font-mono text-txt-muted px-4 py-3 uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {countries.map((c, i) => {
              const isCritical = c.us_pct_of_budget > 70;
              return (
                <tr
                  key={c.iso3}
                  className={`border-b border-surface-3 ${i % 2 === 0 ? "bg-white" : "bg-surface-1"}`}
                >
                  <td className="px-4 py-3 text-sm font-medium text-txt-primary">{c.name}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-4 bg-surface-2 rounded-micro overflow-hidden">
                        <div
                          className="h-full rounded-micro"
                          style={{
                            width: `${c.us_pct_of_budget}%`,
                            background: "#dc2626",
                            opacity: 0.75,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-txt-primary w-8 flex-shrink-0 text-right">
                        {c.us_pct_of_budget}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-2xs px-2 py-0.5 rounded-pill bg-uncertainty-high/10 text-uncertainty-high">
                      {c.at_risk_programs} programs
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {isCritical ? (
                      <span className="text-2xs px-2 py-0.5 rounded-badge bg-red-100 text-red-700 font-medium">
                        Critical dependency
                      </span>
                    ) : (
                      <span className="text-2xs px-2 py-0.5 rounded-badge bg-orange-100 text-orange-700 font-medium">
                        High dependency
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── Section D — Scenarios ─────────────────────────────────────────────────────

function ScenarioBar({ scenario, maxLives, index, inView }: {
  scenario: OutlookData["scenarios"][0];
  maxLives: number;
  index: number;
  inView: boolean;
}) {
  const livesCounted  = useCountUp(scenario.lives_at_risk,  1200, inView);
  const casesCounted  = useCountUp(scenario.cases_rebound,  1200, inView);
  const isSafe        = scenario.lives_at_risk === 0;
  const pct           = isSafe ? 0 : (scenario.lives_at_risk / maxLives) * 100;

  const bgColor = isSafe
    ? "rgba(22,163,74,0.08)"
    : index === 1 ? "rgba(251,191,36,0.08)"
    : index === 2 ? "rgba(234,88,12,0.08)"
    : "rgba(220,38,38,0.1)";

  const barColor = isSafe ? "#16a34a"
    : index === 1 ? "#d97706"
    : index === 2 ? "#ea580c"
    : "#dc2626";

  return (
    <div
      className="rounded-panel border p-5"
      style={{
        background: bgColor,
        borderColor: isSafe ? "#bbf7d0" : `${barColor}40`,
        opacity: inView ? 1 : 0,
        transform: inView ? "none" : "translateY(12px)",
        transition: `opacity 0.5s ${index * 100}ms, transform 0.5s ${index * 100}ms`,
      }}
    >
      <p className="text-xs font-mono font-semibold mb-3" style={{ color: barColor }}>
        {scenario.label}
      </p>

      {isSafe ? (
        <div className="flex items-center gap-2">
          <span className="text-2xl">✓</span>
          <p className="text-sm font-medium text-green-700">No additional lives at risk</p>
        </div>
      ) : (
        <>
          {/* Animated lives bar */}
          <div className="mb-3">
            <div className="flex justify-between mb-1">
              <span className="text-2xs font-mono text-txt-muted">Lives at additional risk</span>
              <span className="text-sm font-mono font-bold tabular-nums" style={{ color: barColor }}>
                {livesCounted.toLocaleString()}
              </span>
            </div>
            <div className="h-3 w-full bg-surface-2 rounded-pill overflow-hidden">
              <div
                className="h-full rounded-pill"
                style={{
                  width: inView ? `${pct}%` : "0%",
                  background: barColor,
                  transition: `width 1.2s cubic-bezier(0.4,0,0.2,1) ${index * 100 + 300}ms`,
                }}
              />
            </div>
          </div>

          {/* Case rebound */}
          <div className="flex items-center justify-between">
            <span className="text-2xs font-mono text-txt-muted">Case rebound</span>
            <span className="text-xs font-mono tabular-nums" style={{ color: barColor }}>
              +{fmtM(casesCounted)} cases/yr
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function ScenariosSection({ scenarios }: { scenarios: OutlookData["scenarios"] }) {
  const { ref, inView } = useInView(0.1);
  const maxLives = Math.max(...scenarios.map((s) => s.lives_at_risk), 1);

  return (
    <section className="px-8 py-4" ref={ref}>
      <SectionHeader
        step="Scenarios"
        title="What Happens If US Funding Changes?"
        subtitle="Modeled impact on mortality and case load under four budget scenarios. Based on WHO WMR 2024 attribution analysis."
        accentColor="#dc2626"
      />
      <div className="grid grid-cols-2 gap-4">
        {scenarios.map((s, i) => (
          <ScenarioBar
            key={s.label}
            scenario={s}
            maxLives={maxLives}
            index={i}
            inView={inView}
          />
        ))}
      </div>
    </section>
  );
}

// ── Section E — Drug Resistance ───────────────────────────────────────────────

const SEV_CONFIG = {
  high:     { color: "#dc2626", bg: "rgba(220,38,38,0.08)",  border: "rgba(220,38,38,0.25)",  label: "Confirmed",       dots: 3 },
  moderate: { color: "#ea580c", bg: "rgba(234,88,12,0.08)",  border: "rgba(234,88,12,0.25)",  label: "Emerging",        dots: 2 },
  low:      { color: "#2563eb", bg: "rgba(37,99,235,0.06)",  border: "rgba(37,99,235,0.20)",  label: "Early signals",   dots: 1 },
};

function ResistanceSection({
  hotspots,
}: {
  hotspots: OutlookData["resistance_hotspots"];
}) {
  const { ref, inView } = useInView(0.1);

  return (
    <section className="px-8 py-4" ref={ref}>
      <SectionHeader
        step="Resistance Threat"
        title="Drug Resistance Hotspots"
        subtitle="Artemisinin resistance confirmed in Southeast Asia, with early signals in East/West Africa. If resistance spreads to Africa — where 95% of deaths occur — current treatment protocols would fail within years."
        accentColor="#dc2626"
      />

      {/* Warning banner */}
      <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-panel px-4 py-3 mb-5">
        <span className="text-lg shrink-0">⚠️</span>
        <p className="text-xs font-mono text-red-800 leading-relaxed">
          <strong>Mekong Delta → Africa pipeline:</strong> Artemisinin-resistant P. falciparum
          first emerged in Cambodia (2008) and has since spread across Southeast Asia.
          US-funded surveillance networks are the primary early-warning system tracking spread into Africa.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {hotspots.map((h, i) => {
          const cfg = SEV_CONFIG[h.severity];
          return (
            <div
              key={h.iso3}
              className="rounded-panel border p-4"
              style={{
                background: cfg.bg,
                borderColor: cfg.border,
                opacity: inView ? 1 : 0,
                transform: inView ? "none" : "translateY(8px)",
                transition: `opacity 0.4s ${i * 60}ms, transform 0.4s ${i * 60}ms`,
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className="text-sm font-semibold text-txt-primary">{h.name}</p>
                  <p className="text-2xs font-mono text-txt-muted">{h.drug}</p>
                </div>
                <div className="flex items-center gap-1 mt-0.5">
                  {[...Array(3)].map((_, di) => (
                    <span
                      key={di}
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: di < cfg.dots ? cfg.color : "#e5e7eb",
                      }}
                    />
                  ))}
                </div>
              </div>
              <span
                className="text-2xs font-mono font-semibold px-2 py-0.5 rounded-badge"
                style={{ background: `${cfg.color}18`, color: cfg.color }}
              >
                {cfg.label}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ── Section F — Economic Argument ─────────────────────────────────────────────

function EconomicSection({ cost }: { cost: number }) {
  return (
    <section className="px-8 py-4 pb-8">
      <div className="bg-accent-navy text-white rounded-panel p-6">
        <h2 className="text-xl font-bold text-white mb-3">
          Malaria Costs US Trade Partners $12B Annually
        </h2>
        <p className="text-sm text-white/80 leading-relaxed mb-5 max-w-2xl">
          Sub-Saharan Africa represents a growing market for US exports and investment. Malaria
          reduces worker productivity, increases healthcare costs, and suppresses economic growth in
          countries where US companies and interests are active. Controlling malaria is not
          charity — it is strategic economic investment.
        </p>
        <p className="font-gothic display-gothic text-3xl text-white/90 mb-2">
          {fmtB(cost)} in lost productivity annually across high-burden countries
        </p>
        <p className="text-2xs text-white/60">
          Sources: WHO World Malaria Report 2024, Global Fund Financial Report 2024, PMI FY2024
          Report
        </p>
      </div>
    </section>
  );
}

// ── Main Canvas ───────────────────────────────────────────────────────────────

export function OutlookCanvas({ data }: { data: OutlookData }) {
  return (
    <div className="h-full overflow-y-auto bg-surface-1">
      {/* Section A — Hero */}
      <ChapterHero
        eyebrow="Chapter 05 — The Outlook"
        headline="THE GAP, THE RISK, THE STAKES"
        subheadline="Global malaria funding falls $4.3 billion short of the WHO target annually. Eight countries depend on the US for over 60% of their malaria budgets. Drug resistance is spreading. Here's what's at stake."
        accentColor="#dc2626"
      />

      <div className="space-y-6 py-2">
        {/* Section B — Funding Gap */}
        <FundingGapSection data={data} />

        {/* Section C — Country Dependency */}
        <CountryDependencySection countries={data.high_dependency_countries} />

        {/* Section D — Scenarios */}
        <ScenariosSection scenarios={data.scenarios} />

        {/* Section E — Drug Resistance */}
        <ResistanceSection hotspots={data.resistance_hotspots} />

        {/* Section F — Economic Argument */}
        <EconomicSection cost={data.economic_cost_trade_partners_usd} />
      </div>
    </div>
  );
}
