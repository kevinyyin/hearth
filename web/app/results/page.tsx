"use client";

import { useEffect, useState } from "react";
import CrewsChart from "@/components/CrewsChart";
import { getJson } from "@/lib/api";
import type { SweepRow } from "@/lib/types";

const ASSUMPTIONS = [
  "Simulated patients reply at configured rates.",
  "Crews accept jobs instantly.",
  "The indoor temperature model is a simple heuristic.",
  "Hearth assumes per-home outage data from the utility.",
];

export default function ResultsPage() {
  const [rows, setRows] = useState<SweepRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<SweepRow[]>("/api/results")
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 pb-20">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Patient-hours at risk by crew count</h1>
        <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--text-secondary)" }}>
          Each line is one dispatch policy replayed over Hurricane Beryl (2024) against simulated
          Harris County patients on power-dependent home medical devices. Lower is better.
        </p>
      </header>

      {error && (
        <div
          className="rounded-xl border p-5 text-sm"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          <p className="font-medium" style={{ color: "var(--text-primary)" }}>
            Could not load the sweep.
          </p>
          <p className="mt-1">{error}</p>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            With no <code>NEXT_PUBLIC_API</code> set the page reads{" "}
            <code>public/dev/api/results.json</code>.
          </p>
        </div>
      )}

      {!error && rows == null && (
        <div
          className="h-[420px] animate-pulse rounded-xl border"
          style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
          aria-label="Loading the sweep"
        />
      )}

      {rows != null && <CrewsChart rows={rows} />}

      <section className="mt-8">
        <h2 className="text-sm font-semibold">Assumptions that flatter Hearth</h2>
        <ul
          className="mt-2 list-disc space-y-1 pl-5 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {ASSUMPTIONS.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </section>

      <p className="mt-6 text-sm" style={{ color: "var(--text-muted)" }}>
        A policy result on simulated patients. Every number traces to a command in the README.
      </p>
    </div>
  );
}
