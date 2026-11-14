// Home markup: what a resident persona says about their own home. Mirrors Home in hearth/contracts.py.
import type { Home, InsideKind, OutsideKind, Patient, SizeId } from "./types";

/** Everyday items standing in for a tape measure: width, depth, height in cm. */
export const SIZES: Record<Exclude<SizeId, "custom">, { label: string; cm: [number, number, number] }> = {
  shoebox: { label: "Shoebox", cm: [35, 20, 13] },
  microwave: { label: "Microwave", cm: [50, 40, 30] },
  carry_on: { label: "Carry-on suitcase", cm: [55, 35, 23] },
  mini_fridge: { label: "Mini fridge", cm: [50, 50, 85] },
};

export const PIN_LABEL: Record<OutsideKind | InsideKind, string> = {
  park: "Park here", entrance: "Entrance", blocked: "Blocked", route: "Route", machine: "Machine",
};

export const PIN_COLOR: Record<OutsideKind | InsideKind, string> = {
  park: "#2a78d6", entrance: "#1baf7a", blocked: "#d03b3b", route: "#eda100", machine: "#8a4fd6",
};

/** One label per pin; route pins are numbered in the order they were placed. */
export function pinLabels(pins: { kind: string }[]): string[] {
  let step = 0;
  return pins.map((p) => (p.kind === "route" ? `Route ${++step}` : PIN_LABEL[p.kind as OutsideKind | InsideKind] ?? p.kind));
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));

export function tapToFraction(
  tap: { clientX: number; clientY: number },
  rect: { left: number; top: number; width: number; height: number },
): { x: number; y: number } {
  return { x: clamp((tap.clientX - rect.left) / rect.width), y: clamp((tap.clientY - rect.top) / rect.height) };
}

export function emptyHome(patient: Patient): Home {
  return { patient_id: patient.patient_id, building_id: patient.building_id ?? "", ok_without_h: 0, backup_plan: "", size: "microwave",
    size_cm: null, scan_id: null, note: "", outside: [], inside: [], contacts: [] };
}

/** Pins belong to the building they were placed on, so a new building starts with none. */
export function withBuilding(home: Home, buildingId: string): Home {
  return home.building_id === buildingId ? home : { ...home, building_id: buildingId, scan_id: null, outside: [], inside: [] };
}

/** Inside pins belong to the scan they were placed in. */
export function withScan(home: Home, scanId: string | null): Home {
  return home.scan_id === scanId ? home : { ...home, scan_id: scanId, inside: [] };
}

export type Persona = { role: "resident" | "responder"; id: string };

const KEY = "hearth-persona";

/** A demo persona, kept in this browser only. Not a login. */
export function getPersona(): Persona | null {
  if (typeof localStorage === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "null") as Persona | null;
  } catch {
    return null;
  }
}

export function setPersona(p: Persona | null): void {
  if (p) localStorage.setItem(KEY, JSON.stringify(p));
  else localStorage.removeItem(KEY);
}
