import type { PlanState, Snapshot } from "./types";

/** Legend order: the states a dispatcher must act on first, the settled ones last. */
export const PLAN_STATES: PlanState[] = [
  "URGENT",
  "UNREACHABLE",
  "MOVE",
  "MOVED",
  "RESUPPLY",
  "OWN_BACKUP",
  "RESTORED",
  "NOT_AFFECTED",
];

/**
 * One hex per state. These are real hex values, not CSS variables, because MapLibre
 * paint properties cannot resolve custom properties — and the basemap stays light in
 * both themes, so one set validated against a light surface is the right target.
 *
 * Eight hues cannot clear the all-pairs colour-separation gate, so hue never carries
 * the meaning alone here: radius tiers it, the legend labels and counts every state,
 * hovering a legend row isolates it, and the patient panel names the state in text.
 */
const STATE_COLORS: Record<PlanState, string> = {
  URGENT: "#d03b3b",
  UNREACHABLE: "#e87ba4",
  MOVE: "#eda100",
  MOVED: "#6250d6",
  RESUPPLY: "#1baf7a",
  OWN_BACKUP: "#2a78d6",
  RESTORED: "#0ca30c",
  NOT_AFFECTED: "#b8b6ad",
};

export function stateColor(state: PlanState): string {
  return STATE_COLORS[state] ?? STATE_COLORS.NOT_AFFECTED;
}

/** Radius in pixels — the second channel, so URGENT reads before any colour does. */
export function stateRadius(state: PlanState): number {
  if (state === "URGENT") return 9;
  if (state === "UNREACHABLE" || state === "MOVE") return 7;
  if (state === "NOT_AFFECTED" || state === "RESTORED") return 4.5;
  return 6;
}

export function countByState(snap: Snapshot): Record<PlanState, number> {
  const counts = Object.fromEntries(PLAN_STATES.map((s) => [s, 0])) as Record<PlanState, number>;
  for (const p of snap.patients) {
    counts[p.state] = (counts[p.state] ?? 0) + 1;
  }
  return counts;
}

const CENTRAL = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

/** Ticks arrive as UTC instants; a Houston dispatcher reads them in US Central. */
export function formatTick(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : CENTRAL.format(d);
}
