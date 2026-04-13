import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Malaria Intelligence — US Global Health Investment Platform",
  description:
    "Tracking where US malaria funding goes, who does the work, and what it achieves.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen overflow-x-hidden">{children}</body>
    </html>
  );
}
