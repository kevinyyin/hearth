import { describe, expect, it } from "vitest";
import { ENROLMENT_CALL, ENROLMENT_FIELDS } from "./simulation";

describe("the simulated enrollment call", () => {
  it("fills each field in from something the resident said, in the order it was said", () => {
    const after = ENROLMENT_FIELDS.map((f) => f.after);
    expect(after.every((i) => ENROLMENT_CALL[i]?.from === "resident")).toBe(true);
    expect(after).toEqual([...after].sort((a, b) => a - b));
  });

  it("asks where the device is and whether it can be moved", () => {
    const asked = ENROLMENT_CALL.filter((l) => l.from === "hearth").map((l) => l.text).join(" ");
    expect(asked).toMatch(/Where in your home/);
    expect(asked).toMatch(/Can it be moved/);
    expect(ENROLMENT_CALL.map((l) => l.at)).toEqual([...ENROLMENT_CALL.map((l) => l.at)].sort((a, b) => a - b));
  });
});
