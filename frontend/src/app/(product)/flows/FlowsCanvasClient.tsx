"use client";

import dynamic from "next/dynamic";
import type { WorldMapData } from "@/lib/data";

const FlowsCanvas = dynamic<{ data: WorldMapData }>(
  () => import("./FlowsCanvas").then((m) => ({ default: m.FlowsCanvas })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-surface-1">
        <p className="font-mono text-sm text-txt-muted animate-pulse">Loading map…</p>
      </div>
    ),
  }
);

export function FlowsCanvasClient({ data }: { data: WorldMapData }) {
  return <FlowsCanvas data={data} />;
}
