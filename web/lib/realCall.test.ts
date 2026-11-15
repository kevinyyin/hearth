import { describe, expect, it } from "vitest";
import { callFields, eventCallFor, heard, helpRequestFor, ordinal, residentFromCall } from "./realCall";

const call = {
  status: "active",
  patient_id: null,
  facts: { device_words: "oxygen concentrator", backup_hours: 6, address: "3210 Louisiana St, Houston", building_id: "7768847" },
  answers: { floor: 3, has_elevator: false, door: "the north door", room: "back bedroom" },
  transcript: [],
};

describe("a real enrollment call", () => {
  it("fills each field once the call has heard it, pending read-backs included", () => {
    const f = Object.fromEntries(callFields(heard(call)).map((x) => [x.label, x.value]));
    expect(f).toEqual({
      Address: "3210 Louisiana St, Houston", Device: "Oxygen concentrator", "Battery backup": "About 6 hours",
      Floor: "3rd, no working elevator", Entrance: "The north door", "Where the device is": "Back bedroom",
    });
    expect(callFields({}).every((x) => x.value === null)).toBe(true);
  });

  it("carries the caller into the outage call and the help request", () => {
    const r = residentFromCall("+19495126068", heard(call));
    expect(r).toMatchObject({ phone: "+19495126068", device: "Oxygen concentrator", backupHours: 6, floor: 3, elevator: false });
    expect(eventCallFor(r)[0].text).toContain("oxygen concentrator runs about 6 hours");
    expect(eventCallFor(r).at(-1)!.text).toContain("the north door and the 3rd floor");
    expect(helpRequestFor(r).summary).toBe("Assisted move — oxygen concentrator, no working lift");
  });

  it("writes ordinals", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 103].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "103rd"]);
  });
});
