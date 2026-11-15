import { describe, expect, it } from "vitest";
import { households, need, pin, stepSeconds, street } from "./dispatch";
import type { AgentRun, DispatchView, HelpRequest, Patient, Registrations } from "./types";

const patient = { patient_id: "R-1", lat: 29.76, lon: -95.37, backup_hours_on_hand: 4, device: "oxygen" } as Patient;
const home = { building_id: "B-1", ok_without_h: 2 } as Registrations["registered"][number]["home"];
const req = (over: Partial<HelpRequest> = {}) => ({ patient_id: "R-1", state: "waiting", blocked: "", job: null, ...over }) as HelpRequest;
const view = (over: Partial<DispatchView> = {}): DispatchView => ({ requests: [], crews: [], agents: [], to_start: [], proposals: [], storm: { placed: {}, last: null }, ...over });
const regs: Registrations = { registered: [{ patient, home, address: "900 Bagby St, Houston, TX", call_id: null, call_status: null }], needs_person: [] };
const run = (over: Partial<AgentRun> = {}) => ({ run_id: "refuge-R-1", kind: "refuge", status: "done", result: {}, started_at: 100, steps: [], ...over }) as AgentRun;

describe("households", () => {
  it("merges a registration and its request, keeping the registration's home", () => {
    const v = view({ requests: [{ request: req(), patient, home: null, device: "oxygen", mobility: "walks", address: "900 Bagby St", building_id: "B-1", lat: 1, lon: 2 }] });
    const [h] = households(v, regs);
    expect(households(v, regs)).toHaveLength(1);
    expect([h.home?.ok_without_h, h.request?.state, h.lat]).toEqual([2, "waiting", 1]);
  });
  it("names a household by its street", () => expect(street("900 Bagby St, Houston, TX")).toBe("900 Bagby St"));
});

describe("need and pin", () => {
  const h = (r: HelpRequest | null) => ({ ...households(undefined, regs)[0], request: r });
  const noRefuge = req({ blocked: "no refuge within 15 km passes the access check" });

  it("a blocked request waits for its refuge agent before it needs a person", () => {
    expect(need(h(noRefuge), view())).toBeNull();
    expect(need(h(noRefuge), view({ agents: [run({ status: "running" })] }))).toBeNull();
    expect(need(h(noRefuge), view({ agents: [run({ result: { shelter_sites: [{} as never, {} as never] } })] }))).toEqual({ kind: "blocked", noRefuge: true, leads: 2 });
  });
  it("a request no crew can carry needs a person at once, shown as hours of backup", () => {
    const r = req({ blocked: "no crew on duty can carry this resident" });
    expect(need(h(r), view())?.kind).toBe("blocked");
    expect(pin(h(r), view())).toEqual({ state: "needs", note: "2 h backup" });
  });
  it("a pending proposal needs a person", () => {
    expect(need(h(null), view({ proposals: [{ patient_id: "R-1" } as never] }))?.kind).toBe("proposal");
  });
  it("pins say what is happening without claiming more", () => {
    expect(pin(h(null), view())).toEqual({ state: "waiting", note: "registered" });
    expect(pin(h(null), view({ agents: [run({ run_id: "survey-B-1", kind: "survey", building_id: "B-1", status: "running" })] })).note).toBe("agents researching");
    expect(pin(h(req({ state: "offered", job: { org_id: "A" } as never })), view())).toEqual({ state: "waiting", note: "A asked" });
    const eta = new Date(1_000_000 + 14 * 60000).toISOString();
    expect(pin(h(req({ state: "accepted", job: { org_id: "A", eta } as never })), view(), 1_000_000)).toEqual({ state: "moving", note: "A, 14 min" });
    expect(pin(h(req({ state: "handled" })), view()).state).toBe("over");
  });
});

describe("stepSeconds", () => {
  it("counts a finished step's length, and a live one's so far", () => {
    const r = run();
    expect(stepSeconds({ text: "", t0: 1, t1: 4 }, r)).toBe(3);
    expect(stepSeconds({ text: "", t0: 1, t1: null }, r, 123_000)).toBe(22);
  });
});
