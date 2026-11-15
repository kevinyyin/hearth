// A small copy of the planner's score, pairing and route search (hearth/routing.py, hearth/alns.py), for the diagrams
// on /algorithm. Same formulas and settings, toy-sized inputs. Positions are in km.
import type { Spot } from "./scanRoute";

export const HORIZON_H = 6; // planner.lookahead_h
export const EARLY = 0.1; // planner.early_weight
const SERVICE_H = 10 / 60; // building.service_base_min
const REMOVE_SHARE = 0.15; // planner.alns_remove_share

export type Point = { x: number; y: number };
export type Need = Point & { id: string; device: string; weight: number; hoursLeft: number };
export type Van = Point & { id: string };
export type Routes = Record<string, Need[]>; // van id -> its stops, in order

/** `routing._cost`: weighted hours past the deadline, plus a small pull toward reaching everyone sooner. */
export const cost = (weight: number, hoursLeft: number, waitH: number) =>
  weight * Math.max(0, waitH - hoursLeft) + ((EARLY * weight) / Math.max(hoursLeft, 0.1)) * waitH;

/** `planner.travel_h`: straight-line km times the detour factor, at 40 km/h. */
export const travelH = (a: Point, b: Point) => (Math.hypot(a.x - b.x, a.y - b.y) * 1.4) / 40;

/** The hour each stop on a route is reached. */
export function reachTimes(van: Van, route: Need[]): number[] {
  let t = 0;
  let at: Point = van;
  return route.map((n) => {
    t += travelH(at, n);
    const reached = t;
    t += SERVICE_H;
    at = n;
    return reached;
  });
}

const routeCost = (van: Van, route: Need[]) => reachTimes(van, route).reduce((sum, t, i) => sum + cost(route[i].weight, route[i].hoursLeft, t), 0);
const leftOut = (n: Need) => cost(n.weight, n.hoursLeft, HORIZON_H);

/** `alns.plan_cost`: every routed need at the hour it is reached, every other need as if it waited the whole window. */
export function planCost(routes: Routes, needs: Need[], vans: Van[]): number {
  const routed = new Set(Object.values(routes).flat().map((n) => n.id));
  return vans.reduce((sum, v) => sum + routeCost(v, routes[v.id] ?? []), 0) + needs.filter((n) => !routed.has(n.id)).reduce((sum, n) => sum + leftOut(n), 0);
}

/** `planner.assign`: the highest weight per hour left goes first, to the nearest van still free. */
export function nearestFirst(needs: Need[], vans: Van[]): Routes {
  const free = [...vans];
  const out: Routes = {};
  for (const n of [...needs].sort((a, b) => b.weight / Math.max(b.hoursLeft, 0.1) - a.weight / Math.max(a.hoursLeft, 0.1))) {
    if (!free.length) break;
    const v = free.reduce((best, c) => (travelH(c, n) < travelH(best, n) ? c : best));
    free.splice(free.indexOf(v), 1);
    out[v.id] = [n];
  }
  return out;
}

/** `routing.value`: the drop in the score from sending this van now rather than not at all, per crew-hour spent. */
const value = (n: Need, v: Van) => Math.max((leftOut(n) - cost(n.weight, n.hoursLeft, travelH(v, n))) / (travelH(v, n) + SERVICE_H), 0);

/** `routing.pair`: one need per van, the largest total value.
 *  shortcut: tries every pairing instead of the Hungarian method; fine for a handful of vans, never for a county. */
export function bestPairing(needs: Need[], vans: Van[]): Routes {
  let best: { total: number; picks: (Need | null)[] } = { total: -1, picks: [] };
  const go = (i: number, picks: (Need | null)[], total: number) => {
    if (i === vans.length) {
      if (total > best.total) best = { total, picks };
      return;
    }
    go(i + 1, [...picks, null], total);
    for (const n of needs) if (!picks.includes(n)) go(i + 1, [...picks, n], total + value(n, vans[i]));
  };
  go(0, [], 0);
  return Object.fromEntries(vans.flatMap((v, i) => (best.picks[i] ? [[v.id, [best.picks[i]!]]] : [])));
}

/** One picture of the route search: the plan, the stops just taken out of it, and the score. */
export type Frame = {
  routes: Routes;
  out: string[];
  how: "start" | "random" | "worst" | "related" | "best";
  score: number;
  best: number;
  /** After a put-back: was the new plan kept? null on the other frames. */
  kept: boolean | null;
};

function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** `alns.search`, recorded round by round. Two frames a round: stops taken out, then put back.
 *  shortcut: puts stops back cheapest-place-first only (no regret order) and picks the removal at random, unweighted. */
export function searchTrace(needs: Need[], vans: Van[], rounds: number, seed = 1): Frame[] {
  const rng = mulberry32(seed);
  const copy = (r: Routes): Routes => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, [...v]]));
  const score = (r: Routes) => planCost(r, needs, vans);
  const byUrgency = (list: Need[]) => [...list].sort((a, b) => leftOut(b) - leftOut(a));

  /** Insert at the place that lowers the score most, if any place does. */
  const put = (r: Routes, n: Need) => {
    let best = { delta: 0, van: "", at: 0 };
    for (const v of vans) {
      const route = r[v.id] ?? [];
      const before = routeCost(v, route) + leftOut(n);
      for (let i = 0; i <= route.length; i++) {
        const delta = routeCost(v, [...route.slice(0, i), n, ...route.slice(i)]) - before;
        if (delta < best.delta) best = { delta, van: v.id, at: i };
      }
    }
    if (best.van) (r[best.van] ??= []).splice(best.at, 0, n);
  };

  let current = bestPairing(needs, vans);
  const paired = new Set(Object.values(current).flat());
  for (const n of byUrgency(needs.filter((n) => !paired.has(n)))) put(current, n);
  let currentScore = score(current);
  let best = copy(current);
  let bestScore = currentScore;
  let temperature = 0.05 * currentScore || 1;
  const frames: Frame[] = [{ routes: copy(current), out: [], how: "start", score: currentScore, best: bestScore, kept: null }];

  for (let round = 0; round < rounds; round++) {
    const inside = Object.entries(current).flatMap(([van, r]) => r.map((n) => ({ van, n })));
    if (!inside.length) break;
    const q = Math.max(1, Math.round(REMOVE_SHARE * inside.length));
    const how = (["random", "worst", "related"] as const)[Math.floor(rng() * 3)];
    let out: Need[];
    if (how === "random") {
      out = [...inside].sort(() => rng() - 0.5).slice(0, q).map((s) => s.n);
    } else if (how === "worst") {
      const paid = vans.flatMap((v) => reachTimes(v, current[v.id] ?? []).map((t, i) => ({ n: current[v.id][i], paid: cost(current[v.id][i].weight, current[v.id][i].hoursLeft, t) })));
      out = paid.sort((a, b) => b.paid - a.paid).slice(0, q).map((s) => s.n);
    } else {
      const from = inside[Math.floor(rng() * inside.length)].n;
      out = inside.map((s) => s.n).sort((a, b) => Math.hypot(a.x - from.x, a.y - from.y) - Math.hypot(b.x - from.x, b.y - from.y)).slice(0, q);
    }
    const trial = copy(current);
    for (const id of Object.keys(trial)) trial[id] = trial[id].filter((n) => !out.includes(n));
    frames.push({ routes: copy(trial), out: out.map((n) => n.id), how, score: score(trial), best: bestScore, kept: null });

    for (const n of byUrgency(out)) put(trial, n);
    const trialScore = score(trial);
    const kept = trialScore < currentScore || rng() < Math.exp((currentScore - trialScore) / temperature);
    if (trialScore < bestScore - 1e-12) [best, bestScore] = [copy(trial), trialScore];
    frames.push({ routes: copy(trial), out: [], how, score: trialScore, best: bestScore, kept });
    if (kept) [current, currentScore] = [trial, trialScore];
    temperature *= 0.95;
  }
  frames.push({ routes: best, out: [], how: "best", score: bestScore, best: bestScore, kept: null });
  return frames;
}

// ---- what the diagrams draw ----

const need = (id: string, x: number, y: number, device: string, weight: number, hoursLeft: number): Need => ({ id, x, y, device, weight, hoursLeft });

/** Three vans, three calls: the nearest-van rule spends the only close van on the wrong door. */
export const PAIR_VANS: Van[] = [{ id: "A", x: 9, y: 13 }, { id: "B", x: 33, y: 16 }, { id: "C", x: 23, y: 3 }];
export const PAIR_NEEDS: Need[] = [
  need("1", 18, 14, "Ventilator", 5, 0.6),
  need("2", 4, 20, "Oxygen", 3, 0.5),
  need("3", 35, 9, "Feeding pump", 1, 4),
];

/** Three vans, eleven stops, for the route search: picked so the search visibly untangles the start. */
export const SEARCH_VANS: Van[] = [{ id: "A", x: 8, y: 12 }, { id: "B", x: 32, y: 6 }, { id: "C", x: 24, y: 19 }];
export const SEARCH_NEEDS: Need[] = [
  need("1", 15, 4, "Oxygen", 3, 2.2), need("2", 16, 20, "Feeding pump", 1, 0.8), need("3", 23, 8, "Ventilator", 5, 0.5),
  need("4", 4, 4, "Oxygen", 3, 2.4), need("5", 6, 8, "Ventilator", 5, 2), need("6", 19, 4, "Oxygen", 3, 1.6),
  need("7", 6, 19, "Ventilator", 5, 2.6), need("8", 13, 7, "Oxygen", 3, 0.5), need("9", 4, 13, "Feeding pump", 1, 0.8),
  need("10", 29, 11, "Feeding pump", 1, 2.2), need("11", 20, 14, "Feeding pump", 1, 1.7),
];

/** A scanned unit as `scanRoute` reads one: spots where the camera stood, and the spots each can see. Metres, as a plan. */
export const UNIT_ROOMS = [
  { id: "hall", name: "Hall", x: 0, y: 2.2, w: 2.6, h: 2.8 },
  { id: "living", name: "Living room", x: 2.6, y: 0.8, w: 4.8, h: 4.2 },
  { id: "kitchen", name: "Kitchen", x: 7.4, y: 0.8, w: 4.6, h: 2.2 },
  { id: "bath", name: "Bath", x: 7.4, y: 3, w: 2.2, h: 2 },
  { id: "closet", name: "Closet", x: 9.6, y: 3, w: 2.4, h: 2 },
  { id: "bedroom", name: "Bedroom", x: 4, y: 5, w: 8, h: 2.2 },
];
const SPOT_AT: Record<string, [number, number, string]> = {
  h1: [0.6, 3.6, "hall"], h2: [2, 3.6, "hall"],
  l1: [3.4, 3.6, "living"], l2: [5, 3, "living"], l3: [6.4, 1.8, "living"], l4: [5.8, 4.2, "living"],
  k1: [8.4, 1.8, "kitchen"], k2: [10.4, 1.8, "kitchen"],
  b1: [8.5, 4, "bath"], c1: [10.8, 4, "closet"],
  d1: [5.8, 6, "bedroom"], d2: [8.2, 6.1, "bedroom"], d3: [10.6, 6.1, "bedroom"],
};
export const UNIT_SIGHT: [string, string][] = [
  ["h1", "h2"], ["h2", "l1"], ["l1", "l2"], ["l2", "l3"], ["l2", "l4"], ["l1", "l4"], ["l3", "k1"], ["k1", "k2"],
  ["l4", "b1"], ["l4", "d1"], ["d1", "d2"], ["d2", "d3"], ["d3", "c1"],
];
export const UNIT_ENTRANCE = "h1";
export const UNIT_SPOTS: Record<string, Spot> = Object.fromEntries(
  Object.entries(SPOT_AT).map(([id, [x, z, room]]) => [id, {
    position: { x, y: 0, z },
    roomInfo: { id: room },
    neighbors: UNIT_SIGHT.flatMap(([a, b]) => (a === id ? [b] : b === id ? [a] : [])),
  }]),
);
