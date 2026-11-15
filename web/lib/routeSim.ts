import legs from "./routeSim.json";

export type ObstacleKind = "debris" | "water" | "wire" | "signal";
export type Obstacle = { at: [number, number]; street: string; kind: ObstacleKind; note: string };
export type Leg = {
  /** Who the crew is going to, and what they do on arrival. Households are synthetic. */
  job: string;
  task: string;
  km: number;
  path: [number, number][];
  /** shortcut: hand-written labels until the obstacle algorithm lands; swap in its output, same shape. */
  obstacles: Obstacle[];
};

/** The crew on the simulation's responder side. Height is what low wires and branches are checked against. */
export const CREW_VEHICLE = { label: "Large van", lengthM: 6.0, widthM: 2.1, heightM: 2.8, lift: "rear lift, 1 wheelchair" };

const JOBS: Pick<Leg, "job" | "task">[] = [
  { job: "R. Alvarez · assisted move, oxygen", task: "Down stairwell B with the concentrator" },
  { job: "Oxygen restock · Valkeith Dr", task: "Swap two cylinders" },
  { job: "Wellness check · Willowbend Blvd", task: "Check on a CPAP user, leave a power bank" },
];

/**
 * Road paths from the public OSRM router (OpenStreetMap), fetched once and saved, so the demo needs no router.
 * shortcut: the first leg ends at the demo resident's building (CoStar 23453, 4620 N Braeswood Blvd); if the
 * resident picks another building the map still drives there, so route at runtime once the planner serves paths.
 */
export const LEGS: Leg[] = (legs as Omit<Leg, "job" | "task">[]).map((l, i) => ({ ...l, ...JOBS[i] }));

export const OBSTACLE_STYLE: Record<ObstacleKind, { label: string; color: string }> = {
  debris: { label: "Debris", color: "#7a4a12" },
  water: { label: "Water", color: "#2a6fd6" },
  wire: { label: "Wire down", color: "#c4461a" },
  signal: { label: "Signal out", color: "#8a6d00" },
};

/** Cumulative distance along a path in degrees-ish units, good enough to pace a van at street scale. */
export function cumulative(path: [number, number][]): number[] {
  const out = [0];
  for (let i = 1; i < path.length; i++) {
    const [ax, ay] = path[i - 1];
    const [bx, by] = path[i];
    out.push(out[i - 1] + Math.hypot((bx - ax) * Math.cos((ay * Math.PI) / 180), by - ay));
  }
  return out;
}

/** Where the van is at fraction p of the path, its bearing, and how many path points it has passed. */
export function pointAt(path: [number, number][], cum: number[], p: number) {
  const d = Math.min(Math.max(p, 0), 1) * cum[cum.length - 1];
  let i = 1;
  while (i < cum.length - 1 && cum[i] < d) i++;
  const [ax, ay] = path[i - 1];
  const [bx, by] = path[i];
  const seg = cum[i] - cum[i - 1] || 1;
  const t = Math.min((d - cum[i - 1]) / seg, 1);
  const at: [number, number] = [ax + (bx - ax) * t, ay + (by - ay) * t];
  const bearing = (Math.atan2((bx - ax) * Math.cos((ay * Math.PI) / 180), by - ay) * 180) / Math.PI;
  return { at, bearing, passed: i };
}

/** Where a crew going to a household the call just enrolled is sent: the household, and what to do there. */
export type Destination = { lon: number; lat: number; job: string; task: string };

const kmBetween = ([ax, ay]: [number, number], [bx, by]: [number, number]) =>
  Math.hypot((bx - ax) * Math.cos((ay * Math.PI) / 180), by - ay) * 111.32;

/**
 * A road path from the public OSRM router (OpenStreetMap), the router the saved legs came from.
 * shortcut: a straight line, its length × 1.4, when the public router does not answer; route on the API once it has roads.
 */
export async function roadPath(from: [number, number], to: [number, number], signal?: AbortSignal): Promise<{ path: [number, number][]; km: number; road: boolean }> {
  try {
    const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${from.join(",")};${to.join(",")}?overview=full&geometries=geojson`, { signal });
    const route = r.ok ? (await r.json()).routes?.[0] : null;
    if (!route?.geometry?.coordinates?.length) throw new Error("no route");
    return { path: route.geometry.coordinates, km: Math.round(route.distance / 100) / 10, road: true };
  } catch (e) {
    if (signal?.aborted) throw e;
    return { path: [from, to], km: Math.round(kmBetween(from, to) * 1.4 * 10) / 10, road: false };
  }
}

/** The saved loop, re-driven through the enrolled household: station -> household -> the next job, then the last leg as saved. */
export async function legsTo(dest: Destination, signal?: AbortSignal): Promise<{ legs: Leg[]; road: boolean }> {
  const home: [number, number] = [dest.lon, dest.lat];
  const next = LEGS[1].path[LEGS[1].path.length - 1];
  const [a, b] = await Promise.all([roadPath(LEGS[0].path[0], home, signal), roadPath(home, next, signal)]);
  // the saved obstacle labels sit on the saved roads, so the new roads carry none
  return {
    legs: [{ ...dest, km: a.km, path: a.path, obstacles: [] }, { ...LEGS[1], km: b.km, path: b.path, obstacles: [] }, LEGS[2]],
    road: a.road && b.road,
  };
}
