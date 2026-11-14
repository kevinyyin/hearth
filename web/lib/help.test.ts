import { describe, expect, it } from "vitest";
import { fillWindow, NEXT_ACTION } from "./help";

describe("the help loop's helpers", () => {
  it("fills the arrival window into the fixed line, in the reader's own clock", () => {
    const line = "They expect to arrive between {window}.";
    expect(fillWindow(line, ["a", "b"], (s) => s.toUpperCase())).toBe("They expect to arrive between A and B.");
    expect(fillWindow("At your door", ["a", "b"], (s) => s)).toBe("At your door");
  });

  it("leaves a line alone when there is no window to show", () => {
    expect(fillWindow("A crew accepts", null)).toBe("A crew accepts");
  });

  it("offers a crew only the next step of the job", () => {
    expect(NEXT_ACTION.offered).toBeUndefined();
    expect(NEXT_ACTION.accepted?.action).toBe("arrived");
    expect(NEXT_ACTION.riding).toEqual({ action: "dropped_off", label: "Dropped off" });
  });
});
