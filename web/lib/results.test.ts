import { describe, expect, it } from "vitest";
import { toChartRows, toSeries } from "./results";
import type { SweepRow } from "./types";

const row = (policy: string, crews: number, over: Partial<SweepRow> = {}): SweepRow => ({
  policy,
  crews,
  median: crews * 10,
  p5: crews * 8,
  p95: crews * 13,
  unweighted_median: crews * 5,
  ...over,
});

describe("toSeries", () => {
  it("groups rows by policy", () => {
    const series = toSeries([row("p0", 5), row("p3", 5), row("p0", 10)], true);

    expect(series.map((s) => s.policy)).toEqual(["p0", "p3"]);
    expect(series[0].points).toHaveLength(2);
    expect(series[1].points).toHaveLength(1);
  });

  it("sorts points by crew count", () => {
    const series = toSeries([row("p3", 40), row("p3", 5), row("p3", 20), row("p3", 10)], true);

    expect(series[0].points.map((p) => p.crews)).toEqual([5, 10, 20, 40]);
  });

  it("uses median with the p5..p95 band when weighted", () => {
    const series = toSeries([row("p3", 20, { median: 900, p5: 700, p95: 1300 })], true);

    expect(series[0].points[0]).toEqual({ crews: 20, y: 900, lo: 700, hi: 1300 });
  });

  it("uses the unweighted median and no band when unweighted", () => {
    const series = toSeries([row("p3", 20, { unweighted_median: 410 })], false);

    expect(series[0].points[0]).toEqual({ crews: 20, y: 410 });
    expect(series[0].points[0].lo).toBeUndefined();
    expect(series[0].points[0].hi).toBeUndefined();
  });

  it("maps each policy to its label", () => {
    const series = toSeries(
      [row("p0", 5), row("p3", 5), row("p3__nobld", 5), row("p3__nomove", 5), row("p3__aid", 5)],
      true,
    );

    expect(series.map((s) => s.label)).toEqual([
      "Phone tree (today)",
      "Hearth",
      "Hearth without building data",
      "Hearth without moves",
      "Hearth with supplier mutual aid",
    ]);
  });

  it("falls back to the policy id for an unknown policy and puts it last", () => {
    const series = toSeries([row("p9__new", 5), row("p3", 5)], true);

    expect(series.map((s) => s.policy)).toEqual(["p3", "p9__new"]);
    expect(series[1].label).toBe("p9__new");
  });

  it("returns no series for no rows", () => {
    expect(toSeries([], true)).toEqual([]);
  });
});

describe("toChartRows", () => {
  it("puts one row per crew count with a key per policy", () => {
    const rows = toChartRows(toSeries([row("p0", 5), row("p3", 5), row("p3", 10)], true));

    expect(rows).toHaveLength(2);
    expect(rows[0].crews).toBe(5);
    expect(rows[0].p0).toBe(50);
    expect(rows[0].p3).toBe(50);
    // p0 has no point at 10 crews, so its line breaks rather than interpolating.
    expect(rows[1].p0).toBeNull();
    expect(rows[1].p3).toBe(100);
  });

  it("carries the band as a floor and a span when weighted", () => {
    const rows = toChartRows(toSeries([row("p3", 20, { p5: 700, p95: 1300 })], true));

    expect(rows[0].p3__lo).toBe(700);
    expect(rows[0].p3__span).toBe(600);
  });

  it("carries no band when unweighted", () => {
    const rows = toChartRows(toSeries([row("p3", 20)], false));

    expect(rows[0].p3__lo).toBeUndefined();
    expect(rows[0].p3__span).toBeUndefined();
  });
});

describe("the central planner lines", () => {
  it("come last and are labelled; the pairing line is not on the page, the route search is a toggle", async () => {
    const { DEFAULT_POLICIES, OPTIONAL_POLICIES, POLICY_ORDER, policyLabel } = await import("./types");
    expect(POLICY_ORDER.slice(-2)).toEqual(["p3__paired", "p3__alns"]);
    expect(policyLabel("p3__paired")).toBe("Hearth, best pairing");
    expect(policyLabel("p3__alns")).toBe("Hearth, pairing and route search");
    expect(DEFAULT_POLICIES).not.toContain("p3__paired");
    expect(OPTIONAL_POLICIES).toContain("p3__alns");
  });
});
