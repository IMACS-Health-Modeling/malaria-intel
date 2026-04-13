"use client";

import dynamic from "next/dynamic";
import type { InvestmentOverview, GeographicSpendData } from "@/lib/data";

const InvestmentCanvas = dynamic<{ data: InvestmentOverview; geoSpend: GeographicSpendData }>(
  () => import("./InvestmentCanvas").then((m) => ({ default: m.InvestmentCanvas })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-surface-1">
        <p className="font-mono text-sm text-txt-muted animate-pulse">Loading…</p>
      </div>
    ),
  }
);

export function InvestmentCanvasClient({ data, geoSpend }: { data: InvestmentOverview; geoSpend: GeographicSpendData }) {
  return <InvestmentCanvas data={data} geoSpend={geoSpend} />;
}
