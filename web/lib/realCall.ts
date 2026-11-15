// A real enrollment call, read into the shapes the simulation page draws: the captured fields, the resident the rest
// of the run follows, and the outage call and help request built from what the caller said.
import { EVENT_CALL, HELP_REQUEST, RESIDENT, type SimResident, type TranscriptLine } from "./simulation";

/** A call as GET /api/calls/{id} returns it. `answers` are home answers heard but not yet read back. */
export type CallDoc = {
  status: string;
  patient_id: string | null;
  facts: Record<string, unknown>;
  answers?: Record<string, unknown>;
  transcript: { role: string; text: string }[];
};

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export const ordinal = (n: number) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
const hours = (h: number) => `${h} hour${h === 1 ? "" : "s"}`;

/** Everything the call has heard so far, confirmed or waiting for its read-back. */
export const heard = (call: CallDoc) => ({ ...call.facts, ...(call.answers ?? {}) });

/** The fields the real call asks for, in the order it asks; null until it has heard the answer. */
export function callFields(f: Record<string, unknown>): { label: string; value: string | null }[] {
  const floor = num(f.floor);
  const unit = str(f.unit);
  return [
    { label: "Address", value: str(f.address) && `${f.address}${unit ? `, unit ${unit}` : ""}` },
    { label: "Device", value: str(f.device_words) && cap(str(f.device_words)!) },
    { label: "Battery backup", value: num(f.backup_hours) != null ? `About ${hours(num(f.backup_hours)!)}` : null },
    { label: "Floor", value: floor != null ? `${ordinal(floor)}${f.has_elevator === false ? ", no working elevator" : f.has_elevator === true ? ", elevator" : ""}` : null },
    { label: "Entrance", value: str(f.door) && cap(str(f.door)!) },
    { label: "Where the device is", value: str(f.room) && cap(str(f.room)!) },
  ];
}

/** The resident the rest of the run follows: the caller, as the call recorded them. */
export function residentFromCall(phone: string, f: Record<string, unknown>): SimResident {
  const door = str(f.door);
  const room = str(f.room);
  const fields = Object.fromEntries(callFields(f).map((x) => [x.label, x.value]));
  return {
    ...RESIDENT,
    id: "real-caller",
    name: "The caller",
    phone,
    device: fields.Device ?? "Medical device",
    backupHours: num(f.backup_hours) ?? 0,
    buildingLabel: fields.Address ?? "Address not given on the call",
    floor: num(f.floor) ?? 1,
    elevator: f.has_elevator === true,
    pins: door ? [{ kind: "entrance", note: cap(door) }] : [],
    insideNote: room ? `The device is in the ${room}.` : "",
  };
}

const doorOf = (r: SimResident) => r.pins.find((p) => p.kind === "entrance")?.note.toLowerCase() ?? "your door";

/** The outage call, saying back what this resident told the enrollment call. */
export function eventCallFor(r: SimResident): TranscriptLine[] {
  return EVENT_CALL.map((line, i) =>
    i === 0 ? { ...line, text: `This is Hearth calling for Harris County. This is a simulated call. The power is out in your area and it is expected to stay out tonight. You told us your ${r.device.toLowerCase()} runs about ${hours(r.backupHours)} on battery.` }
    : i === EVENT_CALL.length - 1 ? { ...line, text: `I've put that in front of a dispatcher now, with ${doorOf(r)} and the ${ordinal(r.floor)} floor. A person will decide and you will hear back on this number.` }
    : line);
}

/** The help request the dispatcher and the crew see, from this resident's record. */
export function helpRequestFor(r: SimResident): typeof HELP_REQUEST {
  const lift = r.elevator ? "elevator" : "no working lift";
  return {
    summary: `Assisted move — ${r.device.toLowerCase()}, ${lift}`,
    details: [
      { label: "Needs", value: `Van with power on board for the ${r.device.toLowerCase()}` },
      { label: "Backup", value: `About ${hours(r.backupHours)}, as said on the enrollment call` },
      { label: "Mobility", value: "Cannot manage stairs unaided (said on the outage call)" },
      { label: "Floor", value: `${ordinal(r.floor)}, ${lift}` },
      { label: "Entrance", value: r.pins.find((p) => p.kind === "entrance")?.note ?? "Not given on the call" },
    ],
  };
}
