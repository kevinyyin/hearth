import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import { DAY_CONSTANTS, buildCounty, drawHouseholds, weightedWait } from "./simulation";

// The reference the Python planner's day is held against (tests/test_day.py): the stand-in households, the page's
// constants, and what the browser's own greedy routes cost. Regenerate with WRITE_SIM_FIXTURE=1 npm test -- simDayFixture
const FILE = join(__dirname, "../../tests/fixtures/sim_day.json");

describe("the day fixture the Python planner is measured against", () => {
  const households = drawHouseholds();
  const side = buildCounty(households).sides.hearthAt;
  const built = JSON.parse(
    JSON.stringify({
      households,
      constants: DAY_CONSTANTS,
      greedy: { weightedWait: weightedWait(side), stops: side.stops, tours: side.tours },
    }),
  );

  it("matches what the page computes today", () => {
    if (process.env.WRITE_SIM_FIXTURE) {
      mkdirSync(dirname(FILE), { recursive: true });
      writeFileSync(FILE, JSON.stringify(built, null, 1) + "\n");
    }
    expect(existsSync(FILE)).toBe(true);
    expect(JSON.parse(readFileSync(FILE, "utf8"))).toEqual(built);
  });
});
