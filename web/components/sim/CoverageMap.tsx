"use client";

import HouseholdMap from "@/components/sim/HouseholdMap";
import { HOUSEHOLDS, count, tallyAt, type HouseholdState } from "@/lib/simulation";

const SWATCH: Record<HouseholdState, { fill: string; ring: boolean }> = {
  reached: { fill: "#0e7a54", ring: false },
  waiting: { fill: "#c4461a", ring: true },
  unaffected: { fill: "#b8b1a4", ring: false },
};

const STATE_LABEL: Record<HouseholdState, string> = {
  reached: "Reached",
  waiting: "Waiting",
  unaffected: "Not yet",
};

function Panel({
  which,
  title,
  hour,
}: {
  which: import("@/lib/simulation").SideKey;
  title: string;
  hour: number;
}) {
  const t = tallyAt(hour, which);
  return (
    <figure className="m-0">
      <figcaption
        className="mb-1.5 text-[11px] font-semibold tracking-wide uppercase"
        style={{ color: "var(--text-secondary)" }}
      >
        {title}
      </figcaption>
      <HouseholdMap
        which={which}
        hour={hour}
        interactive={false}
        height={150}
        ariaLabel={`${title} at hour ${hour}: ${t.reached} of ${HOUSEHOLDS.length} households reached, ${t.waiting} waiting.`}
      />
      <p className="tnum mt-1.5 text-xs" style={{ color: "var(--text-secondary)" }}>
        <span style={{ color: "#0e7a54", fontWeight: 600 }}>{count.format(t.reached)} reached</span>
        {" · "}
        {count.format(t.waiting)} waiting
      </p>
    </figure>
  );
}

/**
 * The same county comparison as the results page, following the run on this page
 * instead of its own clock, and with the controls off: it is a panel to glance at,
 * not a map to drive.
 */
export default function CoverageMap({ hour = 0 }: { hour?: number }) {
  return (
    <section
      className="rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}
      aria-label="Coverage across the simulated county"
    >
      <h3 className="mb-3 text-sm font-semibold">Across the county</h3>

      <div className="grid grid-cols-2 gap-3">
        <Panel which="hearthAt" title="With Hearth" hour={hour} />
        <Panel which="todayAt" title="Today" hour={hour} />
      </div>

      <ul
        className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs"
        style={{ color: "var(--text-secondary)" }}
      >
        {(Object.keys(STATE_LABEL) as HouseholdState[]).map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true">
              {SWATCH[k].ring ? (
                <circle r={4} fill="none" stroke={SWATCH[k].fill} strokeWidth={1.8} />
              ) : (
                <circle r={k === "unaffected" ? 2.4 : 4} fill={SWATCH[k].fill} />
              )}
            </svg>
            {STATE_LABEL[k]}
          </li>
        ))}
      </ul>

      <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Real county, drawn households. It follows the steps you click through, not a replay.
      </p>
    </section>
  );
}
