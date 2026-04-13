"use client";

import dynamic from "next/dynamic";
import type { USEcosystemData } from "@/lib/data";

const EcosystemCanvas = dynamic<{ data: USEcosystemData }>(
  () => import("./EcosystemCanvas").then((m) => ({ default: m.EcosystemCanvas })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-surface-1">
        <p className="font-mono text-sm text-txt-muted animate-pulse">Loading map…</p>
      </div>
    ),
  }
);

export function EcosystemCanvasClient({ data }: { data: USEcosystemData }) {
  return <EcosystemCanvas data={data} />;
}
