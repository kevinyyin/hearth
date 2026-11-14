import type { Metadata } from "next";
import type { ReactNode } from "react";
import { API } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hearth",
  description:
    "Dispatcher tool for people on power-dependent home medical devices during a multi-day outage. All patients are simulated.",
};

/** Fixed on every page, per the brief. Never phrase a result as lives saved. */
function SimulatedBadge() {
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 -translate-x-1/2">
      <span
        className="rounded-full border px-3 py-1 text-xs font-medium tracking-wide uppercase shadow-sm"
        style={{
          background: "var(--surface-1)",
          borderColor: "var(--border)",
          color: "var(--text-secondary)",
        }}
      >
        Simulated patients
      </span>
    </div>
  );
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        {/* one screen tall: the banner takes its row, pages fill the rest (the map) or scroll inside it (results) */}
        <div className="flex h-screen flex-col">
          {!API && (
            <div role="status" className="shrink-0 px-4 py-1.5 text-center text-xs font-medium" style={{ background: "#fdf0c4", color: "#5c4300" }}>
              Sample data, not results: these pages are reading hand-made dev files. Set NEXT_PUBLIC_API to the Hearth API to see the simulation.
            </div>
          )}
          <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
        </div>
        <SimulatedBadge />
      </body>
    </html>
  );
}
