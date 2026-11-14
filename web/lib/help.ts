// The help loop: labels and small helpers for the resident tracker, the crew's job and the dispatch board.
import type { Equipment, HelpState, Vehicle } from "./types";

export const VEHICLES: Record<Vehicle, string> = { car: "Car", van: "Van", wheelchair_van: "Wheelchair van", ambulance: "Ambulance" };

export const EQUIPMENT: Record<Equipment, string> = {
  oxygen: "Oxygen", power: "Portable power", wheelchair_lift: "Wheelchair lift", stretcher: "Stretcher",
};

/** The one step a crew can take next, by the job's state. An offer has two (accept, decline), so it is not here. */
export const NEXT_ACTION: Partial<Record<HelpState, { action: string; label: string }>> = {
  accepted: { action: "arrived", label: "Arrived" },
  at_door: { action: "picked_up", label: "Picked up" },
  riding: { action: "dropped_off", label: "Dropped off" },
};

export const clock = (iso: string): string =>
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).toLowerCase();

/** The API sends its fixed arrival line with a {window} slot, so the times read in this browser's time zone. */
export function fillWindow(text: string, window: [string, string] | null, fmt: (iso: string) => string = clock): string {
  return window ? text.replace("{window}", `${fmt(window[0])} and ${fmt(window[1])}`) : text;
}
