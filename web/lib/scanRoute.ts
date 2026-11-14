// A walking route through a 3D scan. The scan's own spots are places the camera stood, and each lists the spots it
// can see, so a chain of them is a way a person can actually walk: no floor polygon needed.
import type { Vec3 } from "./types";

export type Spot = { position: Vec3; neighbors?: string[]; enabled?: boolean; roomInfo?: { id: string } };

const gap = (a: Vec3, b: Vec3) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

/** The spot closest to a point, e.g. to the resident's machine pin. */
export function nearestSpot(spots: Record<string, Spot>, p: Vec3): string | null {
  let best: string | null = null;
  for (const [id, s] of Object.entries(spots)) {
    if (s.enabled !== false && (best === null || gap(s.position, p) < gap(spots[best].position, p))) best = id;
  }
  return best;
}

/** The shortest walk from `from` to `to`, as spot ids. With no `to`, the walk to the farthest spot in a room scanned
 *  from more than one spot: where the simulation puts a machine nobody has pinned. A room scanned from a single spot
 *  is a closet or a bathroom, so it is passed over while a bigger room can be reached. Empty when there is no way through. */
export function scanRoute(spots: Record<string, Spot>, from: string, to?: string | null): string[] {
  if (!spots[from]) return [];
  const dist: Record<string, number> = { [from]: 0 };
  const prev: Record<string, string> = {};
  const done = new Set<string>();
  for (;;) {
    // shortcut: picks the next spot by scanning them all; fine for the few hundred a scan has
    let at: string | null = null;
    for (const id in dist) if (!done.has(id) && (at === null || dist[id] < dist[at])) at = id;
    if (at === null) break;
    done.add(at);
    for (const n of spots[at].neighbors ?? []) {
      if (!spots[n] || spots[n].enabled === false) continue;
      const d = dist[at] + gap(spots[at].position, spots[n].position);
      if (d < (dist[n] ?? Infinity)) [dist[n], prev[n]] = [d, at];
    }
  }
  let end = to ?? from;
  if (!to) {
    const inRoom: Record<string, number> = {};
    for (const s of Object.values(spots)) if (s.roomInfo) inRoom[s.roomInfo.id] = (inRoom[s.roomInfo.id] ?? 0) + 1;
    const roomy = Object.keys(dist).filter((id) => id !== from && inRoom[spots[id].roomInfo?.id ?? ""] > 1);
    for (const id of roomy.length ? roomy : Object.keys(dist)) if (dist[id] > dist[end]) end = id;
  }
  if (!(end in dist)) return [];
  const path = [end];
  while (path[0] !== from) path.unshift(prev[path[0]]);
  return path;
}
