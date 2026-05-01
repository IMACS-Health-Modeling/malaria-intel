"use client";

import type { ReactNode } from "react";
import { TopNav } from "./TopNav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col h-screen">
      <TopNav />
      <main className="flex-1 min-h-0 overflow-y-auto">{children}</main>
    </div>
  );
}
