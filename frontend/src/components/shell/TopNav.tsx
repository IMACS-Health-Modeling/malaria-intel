"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Info, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { CHAPTERS } from "@/lib/tokens";

const DATA_SOURCES = [
  { name: "PMI (President's Malaria Initiative)", version: "FY2024", coverage: "Country allocations, impact metrics & annual results", note: "Congressional Budget Justification FY2010–2024" },
  { name: "WHO Global Health Observatory API", version: "2024 release", coverage: "Country-level malaria cases & deaths 2010–2024", note: "MALARIA_EST_CASES, MALARIA_EST_DEATHS, ITN coverage indicators" },
  { name: "WHO World Malaria Report", version: "2024 edition", coverage: "Global burden, funding gap & elimination targets", note: "Lag of 1 year is standard — 2024 report covers 2023 data" },
  { name: "Global Fund Data Explorer API", version: "2024 release", coverage: "382 malaria grants, country allocations, donor pledges", note: "US total to GF: $28.2B; GF malaria disbursed: $21.15B" },
  { name: "USAspending.gov", version: "Through FY2024", coverage: "USAID contract/grant awards by recipient geography", note: "API v2 /spending_by_geography/ — keyword: malaria" },
  { name: "NIH RePORTER", version: "Through 2025", coverage: "US institutional malaria R&D grants by state", note: "Queried by keyword: malaria, antimalarial, plasmodium" },
  { name: "ClinicalTrials.gov", version: "Through 2025", coverage: "Malaria clinical trials with US sponsors", note: "Filtered by condition + US sponsor country" },
  { name: "OECD DAC", version: "2023 data", coverage: "US and peer-donor health ODA comparisons", note: "DAC1 table — cumulative bilateral & multilateral health ODA" },
  { name: "ForeignAssistance.gov", version: "Through FY2023", coverage: "US bilateral aid by country & sector", note: "" },
];

export function TopNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <header className="h-16 flex items-center px-6 gap-10 border-b border-surface-3 bg-white z-50 shrink-0">
      {/* Logo + Branding */}
      <Link href="/command" className="flex items-center gap-3 shrink-0">
        <Image
          src="/mnm-logo.webp"
          alt="Malaria No More logo"
          width={56}
          height={56}
          className="h-12 w-12 object-contain"
          priority
        />
        <div className="flex flex-col leading-none">
          <span
            className="font-gothic text-xl tracking-wide text-txt-primary uppercase"
            style={{ fontSynthesis: "none" }}
          >
            Malaria Intel
          </span>
          <span className="text-[9px] tracking-[0.08em] text-txt-muted uppercase font-mono mt-0.5">
            US Global Health Investment
          </span>
        </div>
      </Link>

      {/* Chapter nav */}
      <nav className="flex items-center gap-1">
        {CHAPTERS.map(({ href, label }) => {
          const isActive = pathname === href || pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn("nav-link px-4 py-2 text-[15px]", isActive && "nav-link-active")}
            >
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Right — data sources */}
      <div className="ml-auto flex items-center gap-3" ref={ref}>
        <span className="text-2xs text-txt-muted font-mono hidden sm:block">
          9 sources · Apr 2026
        </span>
        <button
          onClick={() => setOpen(!open)}
          aria-label="Data sources"
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 rounded-badge text-2xs font-medium border transition-colors",
            open
              ? "bg-signal-climate/10 border-signal-climate/30 text-signal-climate"
              : "bg-surface-2 border-surface-3 text-txt-secondary hover:border-txt-muted hover:text-txt-primary"
          )}
        >
          <Info size={13} />
          Sources
        </button>

        {open && (
          <div className="absolute top-[68px] right-4 w-[500px] bg-white border border-surface-3 rounded-panel shadow-overlay z-[100]">
            <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-surface-3">
              <div>
                <p className="text-sm font-semibold text-txt-primary">Data Sources & Vintage</p>
                <p className="text-2xs text-txt-muted mt-0.5">
                  All figures use the latest published data from each authoritative source.
                  Global health bodies typically report with a 1-year lag — this is standard practice.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="ml-3 text-txt-muted hover:text-txt-primary shrink-0 mt-0.5"
              >
                <X size={15} />
              </button>
            </div>

            <div className="px-5 py-3 space-y-2.5 max-h-[420px] overflow-y-auto">
              {DATA_SOURCES.map((src) => (
                <div key={src.name} className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="text-xs font-medium text-txt-primary">{src.name}</span>
                      <span className="text-2xs font-mono text-signal-climate bg-signal-climate/8 px-1.5 py-0.5 rounded-badge shrink-0">
                        {src.version}
                      </span>
                    </div>
                    <p className="text-2xs text-txt-muted mt-0.5">
                      {src.coverage}
                      {src.note && <span className="text-txt-muted/70"> · {src.note}</span>}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <div className="px-5 py-3 border-t border-surface-3 bg-surface-1 rounded-b-panel">
              <p className="text-2xs text-txt-muted">
                Pipeline: <span className="font-mono text-txt-secondary">L0 ingest → L1 transform → L2 serve</span>.
                Raw data stored in <span className="font-mono text-txt-secondary">cdah-malaria-intel-dev</span> S3.
              </p>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
