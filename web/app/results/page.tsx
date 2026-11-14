"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import CrewsChart from "@/components/CrewsChart";
import SideBySide from "@/components/sim/SideBySide";
import { API, getJson } from "@/lib/api";
import { POLICY_LABELS, POLICY_ORDER, type PolicyId, type SweepRow } from "@/lib/types";

const ASSUMPTIONS = [
  "Simulated patients reply at configured rates.",
  "Crews accept jobs instantly.",
  "The indoor temperature model is a simple heuristic.",
  "Hearth assumes per-home outage data from the utility.",
  "Shelters, hospitals and refuge buildings take everyone (no capacity limit), which favors moving people; the gap from building data at high crew counts is an upper bound.",
  "Crews work around the clock.",
];

/** Everything p3 is shown against in the card. */
const COMPARISONS: PolicyId[] = ["p0", "p3__nobld", "p3__nomove", "p3__aid"];

const fmt = new Intl.NumberFormat("en-US");

/** Colour follows the policy, never its rank, so the card and the chart agree. */
function policyColor(policy: PolicyId): string {
  const slot = POLICY_ORDER.indexOf(policy);
  return `var(--series-${slot === -1 ? 1 : slot + 1})`;
}

export default function ResultsPage() {
  const [rows, setRows] = useState<SweepRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [crews, setCrews] = useState<number | null>(null);

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

  const crewTicks = useMemo(
    () => (rows ? [...new Set(rows.map((r) => r.crews))].sort((a, b) => a - b) : []),
    [rows],
  );

  // default to the middle crew count once the sweep lands, so the card is never empty
  useEffect(() => {
    if (crews == null && crewTicks.length > 0) {
      setCrews(crewTicks[Math.floor(crewTicks.length / 2)]);
    }
  }, [crews, crewTicks]);

  const at = (policy: string): number | null => {
    if (!rows || crews == null) return null;
    const row = rows.find((r) => r.policy === policy && r.crews === crews);
    return row ? row.median : null;
  };

  const hearth = at("p3");
  const bars = COMPARISONS.map((p) => ({ policy: p, value: at(p) }));
  const scaleMax = Math.max(hearth ?? 0, ...bars.map((b) => b.value ?? 0), 1);

  return (
    <div data-paper className="min-h-full">
      <div className="mx-auto max-w-[1400px] px-8 pb-24">
        {/* ---------- header ---------- */}
        <header
          className="mb-2 flex flex-wrap items-center gap-x-7 gap-y-3 border-b py-5"
          style={{ borderColor: "var(--border)" }}
        >
          <span className="display text-2xl">Hearth</span>
          <nav className="flex flex-1 gap-6">
            <Link href="/results" className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Results
            </Link>
            <Link href="/dispatch" className="text-sm" style={{ color: "var(--text-muted)" }}>
              Dispatch
            </Link>
            <Link href="/phone" className="text-sm" style={{ color: "var(--text-muted)" }}>
              Calls
            </Link>
          </nav>
          <Link
            href="/simulation"
            className="rounded-lg px-5 py-2.5 text-sm font-semibold"
            style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}
          >
            Run the simulation
          </Link>
        </header>

        {/* ---------- hero + card ---------- */}
        <div className="flex flex-wrap items-center gap-x-14 gap-y-10 py-12">
          <div className="min-w-0 flex-[999_1_480px]">
            <p
              className="mb-5 text-[11px] font-medium tracking-[0.18em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Hurricane Beryl, 2024 — Harris County
            </p>
            <h1 className="display max-w-[15ch] text-[64px] leading-[0.98] tracking-tight">
              How many crews would it have taken?
            </h1>
            <p
              className="mt-7 max-w-[44ch] text-[17px] leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              Set a crew count and something to compare against. Every number comes from replaying the
              storm over the same simulated patients.
            </p>
          </div>

          <section
            aria-label="Set up a comparison"
            className="flex-[1_1_380px] rounded-2xl border p-7"
            style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
          >
            <h2 className="mb-4 text-xl font-semibold">Run a comparison</h2>

            <p className="mb-2 text-sm font-medium" id="crews-label" style={{ color: "var(--text-muted)" }}>
              Delivery crews
            </p>
            <div
              role="group"
              aria-labelledby="crews-label"
              className="mb-6 inline-flex flex-wrap rounded-xl border p-1"
              style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}
            >
              {crewTicks.map((c) => {
                const on = c === crews;
                return (
                  <button
                    key={c}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setCrews(c)}
                    className="tnum rounded-lg px-4 text-sm font-semibold transition-colors"
                    style={{
                      minHeight: 44,
                      background: on ? "var(--text-primary)" : "transparent",
                      color: on ? "var(--surface-0)" : "var(--text-secondary)",
                    }}
                  >
                    {c}
                  </button>
                );
              })}
            </div>

            <div className="mb-5 border-t pt-5" style={{ borderColor: "var(--border)" }}>
              <p className="mb-1.5 text-[11px] tracking-[0.12em] uppercase" style={{ color: "var(--text-muted)" }}>
                Hearth, at {crews ?? "—"} crews
              </p>
              <p className="tnum display text-[52px] leading-[0.85]" style={{ color: "var(--accent)" }}>
                {hearth == null ? "—" : fmt.format(hearth)}
              </p>
            </div>

            {/* all four alternatives at once, rather than picking one */}
            <h3 className="mb-3 text-sm font-semibold">Against each alternative</h3>
            <ul className="m-0 list-none space-y-3 p-0">
              {bars.map(({ policy, value }) => {
                const pct = value == null ? 0 : (value / scaleMax) * 100;
                const hearthPct = hearth == null ? 0 : (hearth / scaleMax) * 100;
                const delta = value != null && hearth != null ? value - hearth : null;
                return (
                  <li key={policy}>
                    <div className="mb-1 flex items-baseline justify-between gap-3">
                      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                        {POLICY_LABELS[policy]}
                      </span>
                      <span className="tnum text-sm font-semibold">
                        {value == null ? "—" : fmt.format(value)}
                      </span>
                    </div>
                    <div
                      className="relative h-2.5 w-full overflow-hidden rounded-full"
                      style={{ background: "var(--border)" }}
                    >
                      <div
                        className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300"
                        style={{ width: `${pct}%`, background: policyColor(policy) }}
                      />
                      {/* where Hearth sits on the same scale */}
                      <div
                        className="absolute inset-y-0 w-0.5 transition-[left] duration-300"
                        style={{ left: `${hearthPct}%`, background: "var(--accent)" }}
                      />
                    </div>
                    {delta != null && (
                      <p className="tnum mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                        {delta >= 0
                          ? `${fmt.format(delta)} more patient-hours than Hearth`
                          : `${fmt.format(-delta)} fewer than Hearth`}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="mt-4 text-xs" style={{ color: "var(--text-muted)" }}>
              Median patient-hours at risk, risk-weighted. Lower is better; the upright mark is
              Hearth on the same scale.
            </p>
          </section>
        </div>

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

        {/* ---------- what the axes mean ---------- */}
        {rows != null && rows.length > 0 && (
          <section
            className="mb-7 border-t pt-9"
            style={{ borderColor: "var(--border)" }}
            aria-label="How to read this chart"
          >
            <h2 className="display mb-5 text-[32px] leading-tight">Every crew count, side by side</h2>

            <div className="grid gap-x-10 gap-y-5 md:grid-cols-3">
              <div>
                <h3 className="mb-1.5 text-sm font-semibold">Across — delivery crews</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  How many crews the county can field at once, from {crewTicks[0]} to{" "}
                  {crewTicks[crewTicks.length - 1]}. The spacing is logarithmic, so each step is a
                  doubling rather than a fixed number — doubling a small fleet matters far more than
                  adding the same crews to a large one. The counts come from the sweep config, not
                  from this page.
                </p>
              </div>
              <div>
                <h3 className="mb-1.5 text-sm font-semibold">Up — patient-hours at risk</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  Hours that simulated patients spend past the point where their device or their
                  indoor temperature is no longer safe, added up across the county. Lower is better.
                  The line is the median across random seeds and the tinted band is the 5th to 95th
                  percentile, so a narrow band means the result barely moved between runs.
                  Risk-weighted counts an hour for a frailer patient as more than an hour; the toggle
                  turns that off.
                </p>
              </div>
              <div>
                <h3 className="mb-1.5 text-sm font-semibold">Where it flatters Hearth</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  Refuges accept everyone with no capacity limit, crews accept instantly and work
                  around the clock, and per-home outage data is assumed to exist. Each one removes a
                  constraint that would bite Hearth harder than the phone tree, because Hearth is the
                  policy that moves people and dispatches crews. Read the gap as an upper bound on
                  what this approach buys, not a forecast.
                </p>
              </div>
            </div>
          </section>
        )}

        {rows != null && rows.length > 0 && (
          <CrewsChart rows={rows} selectedCrews={crews} />
        )}
        {rows != null && rows.length === 0 && (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            The sweep file has no rows yet.
          </p>
        )}

        {/* ---------- the live side-by-side ---------- */}
        {rows != null && rows.length > 0 && (
          <div className="mt-7">
            <SideBySide />
          </div>
        )}

        <section className="mt-10">
          <h2 className="display mb-4 text-2xl">Assumptions that flatter Hearth</h2>
          <ul
            className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            {ASSUMPTIONS.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </section>

        {API && (
          <p className="mt-7 text-sm" style={{ color: "var(--text-muted)" }}>
            A policy result on simulated patients. Every number traces to a command in the README.
          </p>
        )}
      </div>
    </div>
  );
}
