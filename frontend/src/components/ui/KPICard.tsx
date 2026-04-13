"use client";

import { cn } from "@/lib/cn";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

type Props = {
  label: string;
  value: string;
  subvalue?: string;
  change?: number;
  changeLabel?: string;
  glowColor?: string;
  className?: string;
  accent?: string;
};

export function KPICard({ label, value, subvalue, change, changeLabel, glowColor, className, accent }: Props) {
  const trend = change === undefined || change === 0 ? "flat" : change > 0 ? "up" : "down";

  return (
    <div
      className={cn("glass-panel px-5 py-4 kpi-glow", className)}
      style={{
        ...(glowColor ? { "--glow-color": glowColor } as React.CSSProperties : {}),
        ...(accent ? { borderTopColor: accent, borderTopWidth: "2px" } : {}),
      }}
    >
      <p className="text-2xs text-txt-muted font-mono uppercase tracking-widest mb-2">{label}</p>
      <p className="text-xl font-semibold text-txt-primary tabular-nums leading-snug tracking-tight">{value}</p>
      <div className="flex items-center gap-2 mt-2">
        {subvalue && <span className="text-2xs text-txt-muted">{subvalue}</span>}
        {change !== undefined && (
          <span className={cn(
            "flex items-center gap-0.5 text-2xs font-medium",
            trend === "up"   && "text-uncertainty-high",
            trend === "down" && "text-uncertainty-low",
            trend === "flat" && "text-txt-muted",
          )}>
            {trend === "up"   && <TrendingUp size={11} />}
            {trend === "down" && <TrendingDown size={11} />}
            {trend === "flat" && <Minus size={11} />}
            {change > 0 ? "+" : ""}{(change * 100).toFixed(1)}%
            {changeLabel && <span className="text-txt-muted ml-0.5">{changeLabel}</span>}
          </span>
        )}
      </div>
    </div>
  );
}
