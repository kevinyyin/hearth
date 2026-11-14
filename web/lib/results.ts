import { POLICY_ORDER, policyLabel, type SweepRow } from "./types";

export type SeriesPoint = { crews: number; y: number; lo?: number; hi?: number };

export type Series = {
  policy: string;
  label: string;
  points: SeriesPoint[];
};

/**
 * Groups sweep rows into one series per policy, points sorted by crew count.
 * Weighted mode plots `median` with the p5..p95 band; unweighted plots
 * `unweighted_median` with no band.
 */
export function toSeries(rows: SweepRow[], weighted: boolean): Series[] {
  const byPolicy = new Map<string, SeriesPoint[]>();

  for (const row of rows) {
    const point: SeriesPoint = weighted
      ? { crews: row.crews, y: row.median, lo: row.p5, hi: row.p95 }
      : { crews: row.crews, y: row.unweighted_median };

    const points = byPolicy.get(row.policy);
    if (points) {
      points.push(point);
    } else {
      byPolicy.set(row.policy, [point]);
    }
  }

  const rank = (policy: string) => {
    const i = POLICY_ORDER.indexOf(policy as (typeof POLICY_ORDER)[number]);
    return i === -1 ? POLICY_ORDER.length : i;
  };

  return [...byPolicy.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]))
    .map(([policy, points]) => ({
      policy,
      label: policyLabel(policy),
      points: points.sort((a, b) => a.crews - b.crews),
    }));
}

/** Recharts wants one row per x value, so each policy becomes its own keys. */
export function toChartRows(series: Series[]): Record<string, number | null>[] {
  const crewCounts = [...new Set(series.flatMap((s) => s.points.map((p) => p.crews)))].sort(
    (a, b) => a - b,
  );

  return crewCounts.map((crews) => {
    const row: Record<string, number | null> = { crews };
    for (const s of series) {
      const point = s.points.find((p) => p.crews === crews);
      row[s.policy] = point ? point.y : null;
      if (point?.lo !== undefined && point.hi !== undefined) {
        // Recharts draws a band as a stacked area: the floor, then the height above it.
        row[`${s.policy}__lo`] = point.lo;
        row[`${s.policy}__span`] = point.hi - point.lo;
      }
    }
    return row;
  });
}

/**
 * Patient-hours run from a few thousand on the sample file to a few million on a
 * real county sweep, so one fixed format cannot serve both. Fractions are dropped
 * — a risk weight makes them non-integer, and nobody reads a quarter of an hour at
 * this scale — and anything past a million is compacted so a headline number does
 * not run off its card.
 */
export function formatHours(v: number): string {
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(2).replace(/\.?0+$/, "")}M`;
  if (abs >= 10_000) return `${(v / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);
}
