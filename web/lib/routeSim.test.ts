import { expect, it } from "vitest";
import { cumulative, LEGS, legsTo, pointAt } from "./routeSim";

const path: [number, number][] = [[0, 0], [0, 1], [1, 1]];

it("starts at the first point, ends at the last, and stops there past 1", () => {
  const cum = cumulative(path);
  expect(pointAt(path, cum, 0).at).toEqual([0, 0]);
  expect(pointAt(path, cum, 1).at).toEqual([1, 1]);
  expect(pointAt(path, cum, 1.5).at).toEqual([1, 1]);
});

it("goes by distance: a quarter of the way is halfway up the first side, heading north", () => {
  const cum = cumulative(path);
  const { at, bearing } = pointAt(path, cum, 0.25);
  expect(at[0]).toBeCloseTo(0);
  expect(at[1]).toBeCloseTo(0.5);
  expect(bearing).toBeCloseTo(0);
});

it("chains the legs: each starts where the last one ended, with every obstacle on its own road", () => {
  for (let i = 1; i < LEGS.length; i++) {
    const end = LEGS[i - 1].path.at(-1)!;
    expect(Math.hypot(LEGS[i].path[0][0] - end[0], LEGS[i].path[0][1] - end[1])).toBeLessThan(0.0005);
  }
  for (const l of LEGS) for (const o of l.obstacles) expect(l.path.some(([x, y]) => x === o.at[0] && y === o.at[1])).toBe(true);
});

it("re-drives the loop through the enrolled household, falling back to a straight line", async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = (() => Promise.reject(new Error("offline"))) as typeof fetch;
  try {
    const { legs, road } = await legsTo({ lon: -95.38, lat: 29.743, job: "The caller · assisted move", task: "Down the stairs" });
    expect(road).toBe(false);
    expect(legs[0].path).toEqual([LEGS[0].path[0], [-95.38, 29.743]]);
    expect(legs[1].path[0]).toEqual([-95.38, 29.743]);
    expect(legs[1].path.at(-1)).toEqual(LEGS[1].path.at(-1));
    expect(legs[2]).toBe(LEGS[2]);
    expect(legs[0].km).toBeGreaterThan(7);
    expect(legs[0].obstacles).toEqual([]);
  } finally {
    globalThis.fetch = realFetch;
  }
});
