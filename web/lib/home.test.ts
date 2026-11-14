import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getPersona, pinLabels, setPersona, SIZES, tapToFraction, withBuilding, withScan } from "./home";
import type { Home } from "./types";

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
  inside: [{ kind: "machine", position: { x: 1, y: 1, z: 1 }, normal: { x: 0, y: 1, z: 0 } }], contacts: [] };

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
