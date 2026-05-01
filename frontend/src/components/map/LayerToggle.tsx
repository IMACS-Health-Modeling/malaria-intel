"use client";

import { useIntelStore, type MapLayer } from "@/lib/store";
import { cn } from "@/lib/cn";

const LAYERS: { id: MapLayer; label: string; color: string; icon: string }[] = [
  { id: "burden",    label: "Burden",    color: "#ED7238", icon: "◉" },
  { id: "outbreaks", label: "Outbreaks", color: "#dc2626", icon: "⚡" },
  { id: "climate",   label: "Climate",   color: "#5B8FF4", icon: "🌡" },
];

export function LayerToggle() {
  const { activeLayers, toggleLayer } = useIntelStore();

  return (
    <div className="flex flex-col gap-1.5 p-2 bg-white/85 backdrop-blur-md border border-white/90 rounded-[14px] shadow-overlay">
      <p className="text-[9px] font-mono text-txt-muted uppercase tracking-[0.1em] px-1 mb-0.5">
        Layers
      </p>
      {LAYERS.map(({ id, label, color, icon }) => {
        const active = activeLayers.includes(id);
        return (
          <button
            key={id}
            onClick={() => toggleLayer(id)}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-[10px] text-xs font-medium transition-all duration-150 cursor-pointer",
              active
                ? "bg-white shadow-card border border-white text-txt-primary"
                : "text-txt-muted hover:text-txt-primary hover:bg-white/50"
            )}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0 transition-opacity"
              style={{ backgroundColor: color, opacity: active ? 1 : 0.3 }}
            />
            <span>{icon}</span>
            <span className="font-sans">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
