import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { currentOutside, emptyHome, getPersona, OUTSIDE_KINDS, pinLabels, setPersona, SIZES, tapToFraction, withBuilding, withDefaultScan,
  withScan } from "./home";
import type { Home, Patient } from "./types";

const store: Record<string, string> = {};
beforeEach(() => {
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  for (const k of Object.keys(store)) delete store[k];
});

const home: Home = { patient_id: "demo-2", building_id: "23453", ok_without_h: 6, backup_plan: "", size: "microwave", size_cm: null,
  scan_id: "m1", note: "", outside: [{ kind: "park", x: 0.2, y: 0.2 }],
  inside: [{ kind: "machine", position: { x: 1, y: 1, z: 1 }, normal: { x: 0, y: 1, z: 0 } }], contacts: [], helpers: [],
  device_name: "oxygen concentrator", movable: true };

it("turns a tap into a fraction of the image, clamped", () => {
  const rect = { left: 100, top: 50, width: 200, height: 120 };
  expect(tapToFraction({ clientX: 150, clientY: 80 }, rect)).toEqual({ x: 0.25, y: 0.25 });
  expect(tapToFraction({ clientX: 50, clientY: 500 }, rect)).toEqual({ x: 0, y: 1 });
});
it("numbers route pins in order and names the rest", () => {
  expect(pinLabels([{ kind: "park" }, { kind: "route" }, { kind: "blocked" }, { kind: "route" }]))
    .toEqual(["Park here", "Route 1", "Blocked", "Route 2"]);
});
it("drops pins that belong to another building", () => {
  expect(withBuilding(home, "23453")).toBe(home);
  expect(withBuilding(home, "23347")).toMatchObject({ building_id: "23347", scan_id: null, outside: [], inside: [] });
});
it("drops inside pins that belong to another scan", () => {
  expect(withScan(home, "m1")).toBe(home);
  const next = withScan(home, null);
  expect(next.inside).toEqual([]); expect(next.scan_id).toBeNull(); expect(next.outside).toHaveLength(1);
});
it("keeps the persona in this browser", () => {
  expect(getPersona()).toBeNull();
  setPersona({ role: "resident", id: "demo-2" });
  expect(getPersona()).toEqual({ role: "resident", id: "demo-2" });
  setPersona(null); expect(getPersona()).toBeNull();
});
it("knows the carry-on size", () => expect(SIZES.carry_on.cm).toEqual([55, 35, 23]));

it("starts a new home with the device from the patient record, movable not yet answered", () => {
  const fresh = emptyHome({ patient_id: "demo-2", building_id: "23453", device: "oxygen", device_detail: "concentrator" } as Patient);
  expect(fresh.device_name).toBe("oxygen concentrator");
  expect(fresh.movable).toBeNull();
});
it("offers only parking and the entrance outside, and drops older blocked and route pins", () => {
  expect(OUTSIDE_KINDS).toEqual(["park", "entrance"]);
  expect(currentOutside([{ kind: "park", x: 0.1, y: 0.1 }, { kind: "route", x: 0.2, y: 0.2 }, { kind: "blocked", x: 0.3, y: 0.3 },
    { kind: "entrance", x: 0.4, y: 0.4 }]).map((p) => p.kind)).toEqual(["park", "entrance"]);
});
it("opens the home's scan without asking: keeps a saved one, else takes the building's first", () => {
  expect(withDefaultScan(home, ["m0", "m1"])).toBe(home);
  const picked = withDefaultScan({ ...home, scan_id: null, inside: [] }, ["m0", "m1"]);
  expect(picked.scan_id).toBe("m0");
  const gone = withDefaultScan(home, []); // the building has no scan
  expect(gone.scan_id).toBeNull(); expect(gone.inside).toEqual([]);
});
