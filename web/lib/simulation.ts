// A scripted, self-contained demo of the two moments Hearth is for: enrolling a
// household before a storm, and reaching them during one.
//
// Nothing here calls the API or the voice agent. Every line is a fixed string in
// this file, so the simulation runs with the backend down and nothing it shows
// can be mistaken for a measured result. The real enrolment call, the real
// transcript and the real resident record are the voice-registration lane's; when
// that lands, the shapes below are what gets swapped out. Keep them in that
// lane's vocabulary (offered, accepted, at_door, riding, dropped_off) so the two
// meet without a translation layer.

export type Speaker = "hearth" | "resident";

/** One line of a call transcript. `at` is milliseconds from the start of the call. */
export type TranscriptLine = {
  at: number;
  from: Speaker;
  text: string;
};

/** Placeholder household. Replaced by the real resident record once registration lands. */
export type SimResident = {
  id: string;
  name: string;
  synthetic: true;
  phone: string;
  device: string;
  backupHours: number;
  buildingLabel: string;
  floor: number;
  elevator: boolean;
  /** What the resident marked on their own building, in the home-markup vocabulary. */
  pins: { kind: "park" | "entrance" | "blocked" | "route"; note: string }[];
  /** Inside the unit. The scan is one the resident said is laid out like their home. */
  insideNote: string;
};

export const RESIDENT: SimResident = {
  id: "sim-resident-1",
  name: "R. Alvarez",
  synthetic: true,
  phone: "(713) 555-0147",
  device: "Oxygen concentrator",
  backupHours: 4,
  buildingLabel: "Simulated mid-rise, Harris County",
  floor: 3,
  elevator: false,
  pins: [
    { kind: "park", note: "Service bay on the north side, room for a van" },
    { kind: "entrance", note: "North door is step-free; the main lobby steps are not" },
    { kind: "blocked", note: "Front kerb blocked by downed limbs since the storm" },
    { kind: "route", note: "North door, left past the mailboxes, stairwell B" },
  ],
  insideNote: "Concentrator is in the back bedroom, left of the window.",
};

// --- Stage 1: enrolment, before any event -----------------------------------

/**
 * Placeholder enrolment call. The real script, and the rule that no sentence
 * promising help is ever model-written, belong to the messaging lane.
 */
export const ENROLMENT_CALL: TranscriptLine[] = [
  { at: 400, from: "hearth", text: "Hello, this is Hearth, calling for Harris County Emergency Management. This is a recorded, simulated call. Am I speaking with the person who uses an oxygen concentrator at this address?" },
  { at: 3200, from: "resident", text: "Yes, that's me." },
  { at: 4600, from: "hearth", text: "Your equipment supplier told the county you have a device that needs mains power. I'd like to add you to the outage list, so a dispatcher can see you if the power goes out. It takes about a minute. Is now alright?" },
  { at: 9200, from: "resident", text: "That's fine." },
  { at: 10400, from: "hearth", text: "Thank you. First, how many hours does your device run on its battery once the power stops?" },
  { at: 14200, from: "resident", text: "About four, if it's charged." },
  { at: 16000, from: "hearth", text: "Four hours, noted. Is there anyone else in the home who would need help leaving?" },
  { at: 20100, from: "resident", text: "No, just me. I use a walker though." },
  { at: 22600, from: "hearth", text: "Noted, a walker. Last one: if a crew came to your door, which entrance should they use?" },
  { at: 27300, from: "resident", text: "The north door. The front has three steps and the lift has been out since July." },
  { at: 31000, from: "hearth", text: "North door, no lift, third floor. You're on the list. Nothing changes for you today, and no one is coming now. If the power goes out in your area, a dispatcher will see your name and this call. You can change any of this yourself from the link we're sending to this number." },
  { at: 38500, from: "resident", text: "Alright. Thank you." },
];

export const ENROLMENT_FIELDS: { label: string; value: string }[] = [
  { label: "Device", value: "Oxygen concentrator" },
  { label: "Battery backup", value: "About 4 hours" },
  { label: "Household", value: "Lives alone; uses a walker" },
  { label: "Entrance", value: "North door, step-free" },
  { label: "Floor", value: "3rd, no working lift" },
];

// --- Stage 2: during the event ----------------------------------------------

export type EventPhase =
  | "calm"
  | "warning"
  | "calling"
  | "requested"
  | "offered"
  | "accepted"
  | "enroute"
  | "arrived";

/** Who takes the step out of a phase. The button is drawn in that side's column. */
export type Actor = "operator" | "resident" | "responder";

/**
 * The order the phases run in. Nothing advances on a timer: each phase names the
 * one step out of it and who takes it, so whoever is driving the demo has to
 * click through the decisions rather than watch them happen. The last phase has
 * no step, which is how the run ends.
 */
export const EVENT_PHASES: {
  phase: EventPhase;
  clock: string;
  /** `auto` is the one step Hearth takes by itself: it does not wait to be told to dial. */
  next?: { label: string; by: Actor; hint: string; auto?: true };
}[] = [
  {
    phase: "calm",
    clock: "19:40",
    next: { label: "Start the outage", by: "operator", hint: "The power is still on." },
  },
  {
    phase: "warning",
    clock: "19:42",
    next: {
      label: "Calling the household…",
      by: "operator",
      hint: "Hearth dials on its own: that is the point of the registry.",
      auto: true,
    },
  },
  {
    phase: "calling",
    clock: "19:44",
    next: {
      label: "Request help",
      by: "resident",
      hint: "The resident can ask on the call or from the app.",
    },
  },
  {
    phase: "requested",
    clock: "19:51",
    next: {
      label: "Routing it to a crew…",
      by: "operator",
      hint: "The request goes out on its own; the crew still chooses whether to take it.",
      auto: true,
    },
  },
  {
    phase: "offered",
    clock: "19:52",
    next: { label: "Accept", by: "responder", hint: "The crew chooses to take it." },
  },
  {
    phase: "accepted",
    clock: "19:52",
    next: {
      label: "Crew rolling…",
      by: "responder",
      hint: "Access details are on the job.",
      auto: true,
    },
  },
  {
    phase: "enroute",
    clock: "20:03",
    next: { label: "Driving…", by: "responder", hint: "Eleven minutes out.", auto: true },
  },
  { phase: "arrived", clock: "20:19" },
];

/** Placeholder outage call. Real copy is the messaging lane's. */
/**
 * The line where the resident asks for help on the call. Once it has been said,
 * the request exists and the button on their screen is no longer the way it gets
 * made — most people ask the person they are already talking to.
 */
export const EVENT_CALL_ASK_LINE = 3;

export const EVENT_CALL: TranscriptLine[] = [
  { at: 400, from: "hearth", text: "This is Hearth calling for Harris County. This is a simulated call. The power is out in your area and it is expected to stay out tonight. You told us your concentrator runs about four hours on battery." },
  { at: 5600, from: "resident", text: "It's been off maybe an hour already." },
  { at: 7600, from: "hearth", text: "Understood. Would you like a dispatcher to look at getting you somewhere with power, or would you rather stay and have supplies brought to you?" },
  { at: 12400, from: "resident", text: "I'd rather go somewhere. I don't think I can manage the stairs on my own though." },
  { at: 16200, from: "hearth", text: "I've put that in front of a dispatcher now, with the north door and the third floor. A person will decide and you will hear back on this number." },
];

export type RequestDetail = { label: string; value: string };

export const HELP_REQUEST: { summary: string; details: RequestDetail[] } = {
  summary: "Assisted move — oxygen, no working lift",
  details: [
    { label: "Needs", value: "Wheelchair van, oxygen on board" },
    { label: "Backup left", value: "About 2 h 40 m at the time of the call" },
    { label: "Mobility", value: "Walker; cannot manage stairs unaided" },
    { label: "Floor", value: "3rd, lift out since July" },
    { label: "Entrance", value: "North door, step-free" },
    { label: "Access note", value: "Front kerb blocked by downed limbs" },
  ],
};

// --- The corner coverage map -------------------------------------------------

export type Covered = "helped" | "waiting" | "unreached";

export type CoveragePoint = {
  x: number; // 0-100 within the map box
  y: number;
  withHearth: Covered;
  without: Covered;
};

/**
 * An illustration of coverage, not a replay. The shape of it — most households
 * reached either way at low demand, the difference showing up in the tail — is
 * what the sweep reports; these particular dots are drawn, not measured.
 */
export const COVERAGE: CoveragePoint[] = [
  { x: 12, y: 18, withHearth: "helped", without: "helped" },
  { x: 26, y: 11, withHearth: "helped", without: "waiting" },
  { x: 41, y: 22, withHearth: "helped", without: "helped" },
  { x: 58, y: 14, withHearth: "helped", without: "unreached" },
  { x: 72, y: 26, withHearth: "helped", without: "waiting" },
  { x: 86, y: 17, withHearth: "waiting", without: "unreached" },
  { x: 16, y: 38, withHearth: "helped", without: "waiting" },
  { x: 33, y: 44, withHearth: "helped", without: "helped" },
  { x: 49, y: 36, withHearth: "helped", without: "unreached" },
  { x: 64, y: 47, withHearth: "helped", without: "waiting" },
  { x: 79, y: 41, withHearth: "waiting", without: "unreached" },
  { x: 91, y: 52, withHearth: "helped", without: "unreached" },
  { x: 21, y: 61, withHearth: "helped", without: "unreached" },
  { x: 37, y: 69, withHearth: "helped", without: "waiting" },
  { x: 52, y: 58, withHearth: "helped", without: "helped" },
  { x: 68, y: 66, withHearth: "waiting", without: "unreached" },
  { x: 83, y: 73, withHearth: "helped", without: "unreached" },
  { x: 14, y: 81, withHearth: "helped", without: "waiting" },
  { x: 30, y: 88, withHearth: "helped", without: "unreached" },
  { x: 46, y: 79, withHearth: "waiting", without: "unreached" },
  { x: 61, y: 86, withHearth: "helped", without: "waiting" },
  { x: 76, y: 92, withHearth: "helped", without: "unreached" },
  { x: 89, y: 84, withHearth: "waiting", without: "unreached" },
  { x: 5, y: 52, withHearth: "helped", without: "helped" },
];

export const COVERED_LABEL: Record<Covered, string> = {
  helped: "Reached",
  waiting: "Waiting",
  unreached: "Not reached",
};

// --- The side-by-side panel under the chart ---------------------------------
//
// The crew model below is a model: it takes a set of households and works out who
// a fleet reaches, under two dispatch regimes. Where those households come from is
// decided elsewhere, in lib/simSource.ts — the real replay when an API is reachable,
// a drawn fixture when it is not. Nothing here knows which it got, which is the
// point: the same model runs on the teammate's machine with the CoStar kit, on
// Vercel with the keys, and on a laptop with neither.

export const RUN_HOURS = 12;

/** Fallback centre: Harris County, the ground Beryl crossed in July 2024. */
export const COUNTY_CENTER: [number, number] = [-95.37, 29.76]; // lon, lat — Houston
export const COUNTY_ZOOM = 8.6;

/** Crews roll out from depots spread across the county, not from one yard. */
export const STATIONS: { name: string; at: [number, number] }[] = [
  { name: "North", at: [-95.39, 29.95] },
  { name: "East", at: [-95.14, 29.78] },
  { name: "South", at: [-95.33, 29.59] },
  { name: "West", at: [-95.63, 29.77] },
  { name: "Central", at: [-95.37, 29.76] },
];

const CREWS_PER_STATION = 3;
/** Both sides field exactly this many crews: the comparison is about how they are used. */
export const CREW_COUNT = STATIONS.length * CREWS_PER_STATION;

// --- The three numbers that are identical on both sides ---------------------
/** Degrees of ground covered per hour. Same vans, same roads, same speed. */
const CRUISE = 0.34;
/** Hours spent at a door. Same job either way. */
const SERVICE_H = 0.2;
/** How finely the dispatcher reconsiders. */
const DT = 0.25;

// --- The two numbers that differ, and why -----------------------------------
/**
 * Stops a crew takes before heading back. Hearth can plan a round because it
 * already knows who needs help; today a crew is sent to the one address that
 * just came through, and goes home after it.
 */
const CAPACITY = { hearthAt: 4, todayAt: 1 } as const;
/**
 * Households that become visible per hour. Hearth has the registry, so everyone
 * is visible the moment their power goes. Today a household is only visible once
 * its call has worked to the front of the queue, which is what throttles how many
 * crews can be out at all. This rate is an assumption, not a measurement, and
 * almost the whole gap between the two maps rests on it.
 */
const DISCOVERY = { hearthAt: Infinity, todayAt: 1.5 } as const;

export type Household = {
  lon: number;
  lat: number;
  /** Hour this household needs help. From real backup hours when the API is reachable. */
  needsAt: number;
};
export type HouseholdState = "unaffected" | "waiting" | "reached";
export type SideKey = "hearthAt" | "todayAt";

/**
 * Deterministic, so the drawn fixture sits in the same places on every render and
 * every reload — a demo that reshuffles itself is impossible to talk over.
 */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The stand-in population, used only when no API answered. */
export function drawHouseholds(n = 140, seed = 20240708): Household[] {
  const rnd = mulberry32(seed);
  const out: Household[] = [];
  // radial rather than uniform, so the middle of the county is denser, the way a
  // city is; sqrt keeps density even per unit area instead of piling up on the centre
  const SPREAD_LON = 0.44;
  const SPREAD_LAT = 0.31;

  for (let i = 0; i < n; i++) {
    const angle = rnd() * Math.PI * 2;
    const radius = Math.sqrt(rnd());
    out.push({
      lon: COUNTY_CENTER[0] + Math.cos(angle) * radius * SPREAD_LON,
      lat: COUNTY_CENTER[1] + Math.sin(angle) * radius * SPREAD_LAT,
      needsAt: Math.floor(rnd() * rnd() * 7),
    });
  }
  return out;
}

/** One stretch of a crew's trip, in continuous hours. */
export type Leg = {
  from: [number, number];
  to: [number, number];
  t0: number;
  t1: number;
  /** True for the leg that leaves a station: one deployment. */
  departure: boolean;
};

export type SideSim = {
  reachAt: (number | null)[];
  legs: Leg[][];
  station: number[];
  tours: number;
  stops: number;
};

const dist = (a: [number, number], b: [number, number]) =>
  Math.hypot(a[0] - b[0], a[1] - b[1]);

/**
 * One pass over the twelve hours, at the same cruising speed and the same time at
 * the door on both sides. Everything that differs comes from one thing: whether
 * the dispatcher already knows who needs help.
 */
function runSide(households: Household[], which: SideKey): SideSim {
  const capacity = CAPACITY[which];
  const perHour = DISCOVERY[which];

  const reachAt: (number | null)[] = households.map(() => null);
  const taken = households.map(() => false);
  const known = households.map(() => false);
  let discoveredThisHour = 0;
  let hourMark = 0;

  const station: number[] = [];
  const legs: Leg[][] = [];
  const freeAt: number[] = [];
  for (let c = 0; c < CREW_COUNT; c++) {
    station.push(c % STATIONS.length);
    legs.push([]);
    freeAt.push(0);
  }

  let tours = 0;
  let stops = 0;

  for (let t = 0; t <= RUN_HOURS; t += DT) {
    if (Math.floor(t) !== hourMark) {
      hourMark = Math.floor(t);
      discoveredThisHour = 0;
    }

    for (let i = 0; i < households.length; i++) {
      if (known[i] || households[i].needsAt > t) continue;
      if (discoveredThisHour >= perHour) break;
      known[i] = true;
      if (perHour !== Infinity) discoveredThisHour += 1;
    }

    for (let c = 0; c < CREW_COUNT; c++) {
      if (freeAt[c] > t) continue;

      const base = STATIONS[station[c]].at;

      // nearest-neighbour chain from the station: the round a crew would actually drive
      const route: number[] = [];
      let at: [number, number] = base;
      while (route.length < capacity) {
        let best = -1;
        let bestD = Infinity;
        for (let i = 0; i < households.length; i++) {
          if (taken[i] || !known[i] || route.includes(i)) continue;
          const d = dist(at, [households[i].lon, households[i].lat]);
          if (d < bestD) {
            bestD = d;
            best = i;
          }
        }
        if (best === -1) break;
        route.push(best);
        at = [households[best].lon, households[best].lat];
      }

      if (route.length === 0) continue;

      let clock = t;
      let from: [number, number] = base;

      route.forEach((i, k) => {
        const to: [number, number] = [households[i].lon, households[i].lat];
        const travel = dist(from, to) / CRUISE;
        legs[c].push({ from, to, t0: clock, t1: clock + travel, departure: k === 0 });
        clock += travel;

        taken[i] = true;
        reachAt[i] = Math.min(RUN_HOURS, Math.ceil(clock));
        stops += 1;

        clock += SERVICE_H;
        from = to;
      });

      const home = dist(from, base) / CRUISE;
      legs[c].push({ from, to: base, t0: clock, t1: clock + home, departure: false });
      clock += home;

      freeAt[c] = clock;
      tours += 1;
    }
  }

  return { reachAt, legs, station, tours, stops };
}

/** A population plus the two runs over it, and the readings the panel needs. */
export type CountySim = {
  households: Household[];
  sides: Record<SideKey, SideSim>;
  stateAt(i: number, hour: number, which: SideKey): HouseholdState;
  tallyAt(hour: number, which: SideKey): Record<HouseholdState, number>;
  vehiclesAt(time: number, which: SideKey): [number, number][];
  toursBy(time: number, which: SideKey): number;
  outNow(time: number, which: SideKey): number;
};

export function buildCounty(households: Household[]): CountySim {
  const sides: Record<SideKey, SideSim> = {
    hearthAt: runSide(households, "hearthAt"),
    todayAt: runSide(households, "todayAt"),
  };

  const stateAt = (i: number, hour: number, which: SideKey): HouseholdState => {
    if (hour < households[i].needsAt) return "unaffected";
    const at = sides[which].reachAt[i];
    return at != null && hour >= at ? "reached" : "waiting";
  };

  const vehiclesAt = (time: number, which: SideKey): [number, number][] => {
    const out: [number, number][] = [];
    for (let c = 0; c < CREW_COUNT; c++) {
      const leg = sides[which].legs[c].find((l) => time >= l.t0 && time <= l.t1);
      if (!leg) continue;
      const span = Math.max(leg.t1 - leg.t0, 1e-6);
      const p = (time - leg.t0) / span;
      out.push([
        leg.from[0] + (leg.to[0] - leg.from[0]) * p,
        leg.from[1] + (leg.to[1] - leg.from[1]) * p,
      ]);
    }
    return out;
  };

  return {
    households,
    sides,
    stateAt,
    vehiclesAt,
    tallyAt(hour, which) {
      const t: Record<HouseholdState, number> = { unaffected: 0, waiting: 0, reached: 0 };
      for (let i = 0; i < households.length; i++) t[stateAt(i, hour, which)] += 1;
      return t;
    },
    toursBy(time, which) {
      let n = 0;
      for (let c = 0; c < CREW_COUNT; c++) {
        n += sides[which].legs[c].filter((l) => l.departure && l.t0 <= time).length;
      }
      return n;
    },
    outNow(time, which) {
      return vehiclesAt(time, which).length;
    },
  };
}

/** What the panel shows before any fetch resolves, and if none ever does. */
export const FIXTURE_COUNTY: CountySim = buildCounty(drawHouseholds());

/** Formats a count the same way everywhere in the simulation. */
export const count = new Intl.NumberFormat("en-US");
