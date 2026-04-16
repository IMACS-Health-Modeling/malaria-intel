"use client";

import Link from "next/link";
import { cn } from "@/lib/cn";
import { AlertBadge } from "@/components/ui/AlertBadge";
import type { CommandCountrySummary } from "@/lib/data";

type Props = {
  countries: CommandCountrySummary[];
  className?: string;
};

function getTrajectory(c: CommandCountrySummary): { label: string; color: string } {
  if (c.elimination_phase && c.elimination_phase !== "endemic" && c.elimination_phase !== "high_burden") {
    return { label: "Elim. track", color: "#22c55e" };
  }
  if (c.cases_change_yoy == null) return { label: "No data", color: "#9ca3af" };
  if (c.cases_change_yoy < -0.05) return { label: "Declining ↓", color: "#22c55e" };
  if (c.cases_change_yoy < 0)     return { label: "Improving",   color: "#86efac" };
  if (c.cases_change_yoy < 0.03)  return { label: "Stable →",    color: "#9ca3af" };
  return { label: "Rising ↑", color: "#f97316" };
}

export function BurdenTable({ countries, className }: Props) {
  return (
    <div className={cn("overflow-auto", className)}>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-txt-muted text-2xs uppercase tracking-wider border-b border-surface-3">
            <th className="text-left py-2 px-3 font-medium">Country</th>
            <th className="text-right py-2 px-3 font-medium">Cases</th>
            <th className="text-right py-2 px-3 font-medium">Inc/1K</th>
            <th className="text-right py-2 px-3 font-medium">YoY</th>
            <th className="text-right py-2 px-3 font-medium">Trend</th>
            <th className="text-center py-2 px-3 font-medium">Alert</th>
          </tr>
        </thead>
        <tbody>
          {countries.map((c) => (
            <tr
              key={c.iso3}
              className="border-b border-surface-2 hover:bg-surface-3/40 transition-colors"
            >
              <td className="py-2 px-3">
                <Link
                  href={`/country/${c.iso3}`}
                  className="text-txt-primary hover:text-signal-malaria transition-colors font-medium"
                >
                  {c.name}
                </Link>
              </td>
              <td className="text-right py-2 px-3 tabular-nums text-txt-secondary">
                {(c.cases / 1e6).toFixed(1)}M
              </td>
              <td className="text-right py-2 px-3 tabular-nums text-txt-secondary">
                {c.incidence_per_1000.toFixed(1)}
              </td>
              <td className="text-right py-2 px-3 tabular-nums">
                <span
                  className={cn(
                    "font-mono text-2xs",
                    c.cases_change_yoy != null && c.cases_change_yoy > 0.03 ? "text-uncertainty-high" :
                    c.cases_change_yoy != null && c.cases_change_yoy < -0.01 ? "text-uncertainty-low" :
                    "text-txt-muted"
                  )}
                >
                  {c.cases_change_yoy != null
                    ? `${c.cases_change_yoy > 0 ? "+" : ""}${(c.cases_change_yoy * 100).toFixed(1)}%`
                    : "N/A"}
                </span>
              </td>
              <td className="text-right py-2 px-3">
                {(() => {
                  const t = getTrajectory(c);
                  return (
                    <span className="text-2xs font-medium font-mono" style={{ color: t.color }}>
                      {t.label}
                    </span>
                  );
                })()}
              </td>
              <td className="text-center py-2 px-3">
                <AlertBadge level={c.alert_level} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
