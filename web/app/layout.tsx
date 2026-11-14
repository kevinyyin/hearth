import type { Metadata } from "next";
import type { ReactNode } from "react";
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
        <div className="flex min-h-screen flex-col lg:flex-row">
          <main className="min-w-0 flex-1">{children}</main>
          {/* Slot for the manager lane: building panel, agent trace, proposal card. */}
          <aside
            id="panel-slot"
            aria-label="Detail panel"
            className="hidden w-[360px] shrink-0 border-l xl:block"
            style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
          />
        </div>
        <SimulatedBadge />
      </body>
    </html>
  );
}
