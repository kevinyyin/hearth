import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { countByState, formatTick, PLAN_STATES, stateColor, stateRadius } from "./snapshots";
import type { PlanState, Snapshot } from "./types";

const sample = JSON.parse(
  readFileSync(
    join(__dirname, "../public/dev/api/runs/sample__p3__c20__s1/snapshots/0.json"),
    "utf8",
  ),
) as Snapshot;

describe("stateColor", () => {
  it("gives eight distinct colors", () => {
    const colors = PLAN_STATES.map(stateColor);

    expect(colors).toHaveLength(8);
    expect(new Set(colors).size).toBe(8);
  });

  it("returns a hex value, not a CSS variable, so MapLibre paint can use it", () => {
    for (const state of PLAN_STATES) {
      expect(stateColor(state)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("covers every state in the PlanState union", () => {
    const union: PlanState[] = [
      "NOT_AFFECTED",
      "OWN_BACKUP",
      "RESUPPLY",
      "MOVE",
      "MOVED",
      "URGENT",
      "UNREACHABLE",
      "RESTORED",
    ];

    expect([...PLAN_STATES].sort()).toEqual([...union].sort());
  });
});

describe("stateRadius", () => {
  it("makes URGENT the largest mark, so it reads before colour does", () => {
    const urgent = stateRadius("URGENT");
    const others = PLAN_STATES.filter((s) => s !== "URGENT").map(stateRadius);

    expect(Math.max(...others)).toBeLessThan(urgent);
  });

  it("keeps the settled states recessive", () => {
    expect(stateRadius("NOT_AFFECTED")).toBeLessThan(stateRadius("RESUPPLY"));
    expect(stateRadius("RESTORED")).toBeLessThan(stateRadius("RESUPPLY"));
  });
});

describe("countByState", () => {
  it("sums to the number of patients on the sample snapshot", () => {
    const counts = countByState(sample);
    const total = Object.values(counts).reduce((a, b) => a + b, 0);

    expect(sample.patients.length).toBeGreaterThan(0);
    expect(total).toBe(sample.patients.length);
  });

  it("has a key for every state, zero included", () => {
    const counts = countByState(sample);

    expect(Object.keys(counts).sort()).toEqual([...PLAN_STATES].sort());
    for (const state of PLAN_STATES) {
      expect(counts[state]).toBeGreaterThanOrEqual(0);
    }
  });

  it("counts the sample's two URGENT patients", () => {
    expect(countByState(sample).URGENT).toBe(2);
  });

  it("counts an empty snapshot as all zeros", () => {
    const empty: Snapshot = { t: "2024-07-08T12:00:00Z", patients: [], crews: [], depots: [] };
    const counts = countByState(empty);

    expect(Object.values(counts).every((n) => n === 0)).toBe(true);
  });
});

describe("formatTick", () => {
  it("renders a UTC instant in US Central", () => {
    // 12:00Z on 8 July 2024 is 07:00 CDT.
    expect(formatTick("2024-07-08T12:00:00Z")).toContain("7:00");
    expect(formatTick("2024-07-08T12:00:00Z")).toContain("CDT");
  });

  it("passes an unparseable tick straight through", () => {
    expect(formatTick("not-a-time")).toBe("not-a-time");
  });
});
