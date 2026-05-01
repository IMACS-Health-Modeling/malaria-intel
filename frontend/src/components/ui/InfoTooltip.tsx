"use client";

import { useState, useEffect, useRef } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/cn";
import type { MetricMeta } from "@/lib/metric-metadata";

export type { MetricMeta };

const CONFIDENCE_CONFIG = {
  high: {
    label: "High confidence",
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    dot: "bg-emerald-500",
  },
  medium: {
    label: "Medium confidence",
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    dot: "bg-amber-500",
  },
  low: {
    label: "Low confidence",
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    dot: "bg-red-500",
  },
};

type Props = {
  meta: MetricMeta;
  className?: string;
  size?: number;
};

export function InfoTooltip({ meta, className, size = 11 }: Props) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const conf = CONFIDENCE_CONFIG[meta.confidence];

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  return (
    <span
      ref={wrapperRef}
      style={{ position: "relative", display: "inline-flex", alignItems: "center" }}
      className={className}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "ml-1 w-3.5 h-3.5 rounded-full inline-flex items-center justify-center",
          "text-txt-muted hover:text-signal-climate transition-colors focus:outline-none",
        )}
        aria-label={`About: ${meta.title}`}
        aria-expanded={open}
      >
        <Info size={size} strokeWidth={2} />
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2",
            "w-[280px] bg-white border border-surface-3 rounded-[14px] shadow-overlay p-4",
          )}
          role="tooltip"
        >
          {/* Title */}
          <p className="font-semibold text-sm text-txt-primary leading-snug">
            {meta.title}
          </p>

          {/* Methodology */}
          <p className="text-xs text-txt-secondary leading-relaxed mt-2">
            {meta.methodology}
          </p>

          <hr className="border-surface-3 my-3" />

          {/* Source row */}
          <div className="flex items-start gap-1 text-xs text-txt-muted mb-2">
            <span className="font-medium text-txt-secondary shrink-0">Source:</span>
            <span className="leading-snug">{meta.source}</span>
            {meta.sourceYear && (
              <span className="ml-auto shrink-0 text-[10px] font-mono bg-surface-2 px-1.5 py-0.5 rounded">
                {meta.sourceYear}
              </span>
            )}
          </div>

          {/* Confidence badge */}
          <div
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium",
              conf.bg,
              conf.border,
              conf.color,
            )}
          >
            <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", conf.dot)} />
            {conf.label}
          </div>

          {/* Confidence reason */}
          <p className="text-[10px] text-txt-muted mt-1 leading-relaxed">
            {meta.confidenceReason}
          </p>

          {/* Notes */}
          {meta.notes && (
            <p className="text-[10px] text-txt-muted italic mt-2 leading-relaxed border-t border-surface-3 pt-2">
              {meta.notes}
            </p>
          )}
        </div>
      )}
    </span>
  );
}
