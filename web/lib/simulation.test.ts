import { describe, expect, it } from "vitest";
import { DT, OPERATORS, RUN_HOURS, buildCounty, drawHouseholds, type SideSim } from "./simulation";

const steps = () => Array.from({ length: Math.floor(RUN_HOURS / DT) + 1 }, (_, k) => k * DT);

/** Orders the dispatcher had at `t` and had not sent a van for, once that step's dispatch was done. */
const waitingAfter = (side: SideSim, t: number) =>
  side.jobs.filter(
    (j) => j.knownAt !== null && j.knownAt <= t && j.dueAt <= t && (j.sentAt === null || j.sentAt > t),
  );

/** Vans at their station at `t`: each round runs from its departure to the end of its drive home. */
const freeVans = (side: SideSim, t: number) =>
  side.legs.filter((legs) => {
    const rounds: [number, number][] = [];
    for (const l of legs) {
      if (l.departure) rounds.push([l.t0, l.t1]);
      else rounds[rounds.length - 1][1] = l.t1;
    }
    return !rounds.some(([a, b]) => a <= t && t < b);
  }).length;

describe("today's phone queue", () => {
  const county = buildCounty(drawHouseholds());
  const calls = county.sides.todayAt.calls;

  it("answers calls in the order they rang", () => {
    for (let k = 1; k < calls.length; k++) {
      expect(calls[k].at).toBeGreaterThanOrEqual(calls[k - 1].at);
      if (calls[k].answeredAt !== null) {
        expect(calls[k].answeredAt!).toBeGreaterThanOrEqual(calls[k - 1].answeredAt!);
      }
    }
    for (const c of calls) if (c.answeredAt !== null) expect(c.answeredAt).toBeGreaterThanOrEqual(c.at);
  });

  it("starts empty, lets the first callers straight through, then builds", () => {
    expect(county.queueAt(0, "todayAt")).toBe(0);
    for (const c of calls.slice(0, OPERATORS)) expect(c.answeredAt).toBe(c.at);
    expect(calls[OPERATORS].answeredAt!).toBeGreaterThan(calls[OPERATORS].at);
    expect(county.queueAt(1, "todayAt")).toBeGreaterThan(0);
    expect(county.queueAt(4, "todayAt")).toBeGreaterThan(county.queueAt(1, "todayAt"));
  });

  it("has no queue with the registry", () => {
    expect(county.sides.hearthAt.calls).toHaveLength(0);
    for (const t of steps()) expect(county.queueAt(t, "hearthAt")).toBe(0);
  });
});

describe("what the map shows", () => {
  const households = drawHouseholds();
  const county = buildCounty(households);

  it("sends households into need one at a time, not in hourly batches", () => {
    expect(new Set(households.map((h) => h.needsAt)).size).toBe(households.length);
  });

  it("changes a household's colour when the van pulls away, and shows the van parked until then", () => {
    const side = county.sides.hearthAt;
    const job = side.jobs.find((j) => j.servedAt !== null && !j.refill)!;
    const legs = side.legs.find((ls) => ls.some((l) => l.from === l.to && l.t1 === job.servedAt))!;
    const parked = legs.find((l) => l.from === l.to && l.t1 === job.servedAt)!;
    const mid = (parked.t0 + parked.t1) / 2;

    expect(county.stateAt(job.h, mid, "hearthAt")).toBe("waiting");
    expect(county.stateAt(job.h, job.servedAt!, "hearthAt")).toBe("reached");
    expect(
      county.vehiclesAt(mid, "hearthAt").some((v) => v.lon === parked.to[0] && v.lat === parked.to[1]),
    ).toBe(true);
  });
});

describe("dispatch", () => {
  // the fixture, and a population built so orders outnumber vans while restocks
  // are due: 20 households helped early whose deliveries run down around hour 10,
  // just as 80 households need help for the first time
  const crowded = drawHouseholds(100, 7).map((h, i) =>
    i < 20 ? { ...h, needsAt: 0, repeats: true } : { ...h, needsAt: 10, repeats: false },
  );
  const counties = { fixture: buildCounty(drawHouseholds()), crowded: buildCounty(crowded) };

  for (const [name, county] of Object.entries(counties)) {
    for (const which of ["hearthAt", "todayAt"] as const) {
      const side = county.sides[which];

      it(`never leaves a van at its station while an order waits (${name}, ${which})`, () => {
        for (const t of steps()) {
          if (waitingAfter(side, t).length) expect(freeVans(side, t)).toBe(0);
        }
      });

      it(`sends no restock while a first delivery is left waiting (${name}, ${which})`, () => {
        for (const t of steps()) {
          const restockSent = side.jobs.some((j) => j.refill && j.sentAt === t);
          if (restockSent) expect(waitingAfter(side, t).filter((j) => !j.refill)).toHaveLength(0);
        }
      });
    }
  }

  it("is tested where it matters: first deliveries and restocks queue for vans together", () => {
    const side = counties.crowded.sides.hearthAt;
    const contended = steps().some((t) => {
      const w = waitingAfter(side, t);
      return w.some((j) => j.refill) && w.some((j) => !j.refill);
    });
    expect(contended).toBe(true);
    expect(side.refills).toBeGreaterThan(0);
  });
});
