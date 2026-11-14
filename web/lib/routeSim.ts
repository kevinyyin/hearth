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
  { job: "Oxygen restock · Kempwood Dr", task: "Swap two cylinders" },
  { job: "Wellness check · Sonneville Dr", task: "Check on a CPAP user, leave a power bank" },
];

/** Road paths from the public OSRM router (OpenStreetMap), fetched once and saved, so the demo needs no router. */
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
