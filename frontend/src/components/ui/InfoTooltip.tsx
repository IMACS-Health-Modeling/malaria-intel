"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { cn } from "@/lib/cn";

type Props = {
  title: string;
  body: string;
  /** Which side the tooltip panel opens toward. Default: "right" */
  side?: "left" | "right";
  className?: string;
};

const PANEL_WIDTH = 288;
const MARGIN = 8;

export function InfoTooltip({ title, body, side = "right", className }: Props) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const computeCoords = useCallback(() => {
    if (!btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = r.bottom + MARGIN;
    if (top + 160 > vh) top = r.top - 160 - MARGIN;
    top = Math.max(MARGIN, top);

    let left = side === "right" ? r.left : r.right - PANEL_WIDTH;
    left = Math.min(left, vw - PANEL_WIDTH - MARGIN);
    left = Math.max(MARGIN, left);

    setCoords({ top, left });
  }, [side]);

  const show = useCallback(() => { computeCoords(); setOpen(true); }, [computeCoords]);
  const hide = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  return (
    <div ref={containerRef} className={cn("relative inline-flex items-center shrink-0", className)}>
      <button
        ref={btnRef}
        type="button"
        onMouseEnter={show}
        onMouseLeave={hide}
        onClick={() => (open ? hide() : show())}
        className="w-4 h-4 rounded-full flex items-center justify-center text-txt-muted hover:text-signal-climate hover:bg-blue-50 transition-colors focus:outline-none"
        aria-label={`About: ${title}`}
      >
        <Info size={12} strokeWidth={2} />
      </button>

      {open && typeof window !== "undefined" && createPortal(
        <div
          className="fixed z-[9999] w-72 bg-white border border-surface-3 rounded-badge shadow-xl p-3.5 pointer-events-none"
          style={{ top: coords.top, left: coords.left }}
        >
          <p className="text-xs font-semibold text-txt-primary mb-1.5 leading-snug">{title}</p>
          <p className="text-2xs text-txt-muted leading-relaxed">{body}</p>
        </div>,
        document.body,
      )}
    </div>
  );
}
