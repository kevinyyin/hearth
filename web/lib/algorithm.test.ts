import { describe, expect, it } from "vitest";
import { PAIR_NEEDS, PAIR_VANS, SEARCH_NEEDS, SEARCH_VANS, UNIT_ENTRANCE, UNIT_SPOTS, bestPairing, cost, nearestFirst, planCost, reachTimes, searchTrace, type Routes, type Van } from "./algorithm";
import { scanRoute } from "./scanRoute";

const lateIn = (vans: Van[], routes: Routes) => vans.flatMap((v) => (routes[v.id] ?? []).filter((n, i) => reachTimes(v, routes[v.id])[i] > n.hoursLeft)).length;

describe("the algorithm page's small planner", () => {
  it("scores a wait as routing._cost does", () => {
    expect(cost(3, 2, 4)).toBeCloseTo(3 * 2 + ((0.1 * 3) / 2) * 4);
    expect(cost(5, 2, 1)).toBeCloseTo(((0.1 * 5) / 2) * 1); // not late yet: only the small term
  });

  it("the pairing diagram shows what it claims: nearest-first is late for someone the best pairing reaches in time", () => {
    const greedy = nearestFirst(PAIR_NEEDS, PAIR_VANS);
    const best = bestPairing(PAIR_NEEDS, PAIR_VANS);
    expect(lateIn(PAIR_VANS, greedy)).toBe(1);
    expect(lateIn(PAIR_VANS, best)).toBe(0);
    expect(planCost(best, PAIR_NEEDS, PAIR_VANS)).toBeLessThan(planCost(greedy, PAIR_NEEDS, PAIR_VANS));
  });

  it("the route search never ends worse than it started, and finds something better here", () => {
    const frames = searchTrace(SEARCH_NEEDS, SEARCH_VANS, 30);
    for (let i = 1; i < frames.length; i++) expect(frames[i].best).toBeLessThanOrEqual(frames[i - 1].best);
    const last = frames[frames.length - 1];
    expect(last.score).toBeLessThan(frames[0].score);
    expect(lateIn(SEARCH_VANS, frames[0].routes)).toBe(3);
    expect(lateIn(SEARCH_VANS, last.routes)).toBe(0);
    expect(Object.values(last.routes).flat().map((n) => n.id).sort()).toEqual(SEARCH_NEEDS.map((n) => n.id).sort());
    expect(searchTrace(SEARCH_NEEDS, SEARCH_VANS, 30)).toEqual(frames); // same inputs, same routes
  });

  it("the scanned unit sends an unpinned machine to the far bedroom corner, past the closet", () => {
    expect(scanRoute(UNIT_SPOTS, UNIT_ENTRANCE).at(-1)).toBe("d3");
    expect(scanRoute(UNIT_SPOTS, UNIT_ENTRANCE, "k2")).toEqual(["h1", "h2", "l1", "l2", "l3", "k1", "k2"]);
  });
});
