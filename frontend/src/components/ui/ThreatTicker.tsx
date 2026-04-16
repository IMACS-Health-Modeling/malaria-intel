"use client";

import { cn } from "@/lib/cn";
import { EVENT_COLORS } from "@/lib/tokens";
import type { ThreatEvent } from "@/lib/data";

type Props = {
  events: ThreatEvent[];
  className?: string;
};

export function ThreatTicker({ events, className }: Props) {
  const items = [...events, ...events]; // duplicate for seamless loop

  return (
    <div
      className={cn(
        "overflow-hidden border-y border-surface-3 bg-surface-1",
        className
      )}
    >
      <div className="flex items-center animate-ticker-scroll whitespace-nowrap py-1.5">
        {items.map((e, i) => (
          <div
            key={`${e.event_id}-${i}`}
            className="flex items-center gap-2 px-4 text-2xs shrink-0"
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: EVENT_COLORS[e.event_type] ?? "#90a7bf" }}
            />
            <span className="text-txt-muted">
              <span className="font-medium text-txt-secondary">{e.disease}</span>
              {" "}{e.country_name} · {e.admin1}
              {e.dci_score !== null && (
                <span className="ml-1.5 text-signal-arbovirus font-mono">
                  DCI {e.dci_score.toFixed(2)}
                </span>
              )}
            </span>
            <span className="text-txt-muted/40">|</span>
          </div>
        ))}
      </div>
    </div>
  );
}
