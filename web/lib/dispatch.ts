import type { AgentRun, DispatchView, HelpRequest, Home, Patient, RefugeProposal, Registrations } from "./types";

/** Everyone Hearth knows on the dispatch map: a phone registration, a help request, or both. */
export type Household = {
  id: string;
  patient: Patient;
  home: Home | null;
  address: string | null;
  buildingId: string | null;
  lat: number;
  lon: number;
  request: HelpRequest | null;
};

export type PinState = "needs" | "waiting" | "moving" | "safe" | "over";
export const PIN_COLORS: Record<PinState, string> = { needs: "#c4461a", waiting: "#a87400", moving: "#2a78d6", safe: "#0e7a54", over: "#6b6457" };
export const SIMULATED_COLOR = "#a39c8c";

/** The street line of a CoStar address: "900 Bagby St, Houston, TX 77002" -> "900 Bagby St". */
export const street = (address: string | null): string => address?.split(",")[0] ?? "Address not on record";
export const words = (s: string): string => s.replace(/_/g, " ");
export const hoursOf = (h: Household): number => h.home?.ok_without_h ?? h.patient.backup_hours_on_hand;
export const clock = (at: string | number): string =>
  new Date(typeof at === "number" ? at * 1000 : at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/** Registrations and requests merged by patient; a request's position and record win. */
export function households(view: DispatchView | undefined, regs: Registrations | undefined): Household[] {
  const out = new Map<string, Household>();
  for (const { patient, home, address } of regs?.registered ?? []) {
    out.set(patient.patient_id, { id: patient.patient_id, patient, home, address, buildingId: home.building_id, lat: patient.lat, lon: patient.lon, request: null });
  }
  for (const row of view?.requests ?? []) {
    const id = row.request.patient_id;
    out.set(id, { ...out.get(id), id, patient: row.patient, home: row.home ?? out.get(id)?.home ?? null, address: row.address,
      buildingId: row.building_id, lat: row.lat, lon: row.lon, request: row.request });
  }
  return [...out.values()];
}

export const refugeRun = (view: DispatchView, id: string): AgentRun | undefined => view.agents.find((a) => a.run_id === `refuge-${id}`);

export type Need = { kind: "proposal"; proposal: RefugeProposal } | { kind: "blocked"; noRefuge: boolean; leads: number } | null;

/** Whether a person is needed, once per household. While the refuge agent works on a request it is not, yet. */
export function need(h: Household, view: DispatchView): Need {
  const proposal = view.proposals.find((p) => p.patient_id === h.id);
  if (proposal) return { kind: "proposal", proposal };
  const r = h.request;
  if (!r || r.state !== "waiting" || !r.blocked) return null;
  const noRefuge = r.blocked.startsWith("no refuge");
  const run = refugeRun(view, h.id);
  if (noRefuge && (!run || ["running", "stopped"].includes(run.status) || view.to_start.some((s) => s.run_id === run.run_id))) return null;
  return { kind: "blocked", noRefuge, leads: run?.result.shelter_sites?.length ?? 0 };
}

/** The pin's colour and its short status, also the request's chip on the rail. */
export function pin(h: Household, view: DispatchView, now = Date.now()): { state: PinState; note: string } {
  const r = h.request;
  if (need(h, view)) return { state: "needs", note: `${hoursOf(h)} h backup` };
  const researching = view.agents.some((a) => a.status === "running" && (a.kind === "refuge" ? a.patient_id === h.id : a.building_id === h.buildingId));
  const crew = r?.job?.org_id ?? "a crew";
  switch (r?.state) {
    case undefined:
    case "waiting":
      return { state: "waiting", note: researching ? "agents researching" : r ? "waiting for a crew" : "registered" };
    case "offered":
      return { state: "waiting", note: `${crew} asked` };
    case "accepted": {
      const eta = r.job?.eta ? Math.max(0, Math.round((Date.parse(r.job.eta) - now) / 60000)) : null;
      return { state: "moving", note: eta === null ? `${crew} on the way` : `${crew}, ${eta} min` };
    }
    case "at_door":
      return { state: "moving", note: `${crew} at the door` };
    case "riding":
      return { state: "moving", note: `riding with ${crew}` };
    case "dropped_off":
      return { state: "safe", note: "dropped off" };
    case "safe":
      return { state: "safe", note: "safe" };
    case "handled":
      return { state: "over", note: "taken over" };
  }
}

/** Seconds a step took, or has taken so far. */
export const stepSeconds = (step: AgentRun["steps"][number], run: AgentRun, now = Date.now()): number =>
  Math.max(0, Math.round((step.t1 ?? now / 1000 - run.started_at) - step.t0));
