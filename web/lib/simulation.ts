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

export const RUN_HOURS = 12;

/** Where the replay is set: Harris County, the ground Beryl crossed in July 2024. */
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
/** A tour is one trip out and back, whatever it manages to do in between. */
const TOUR_HOURS = 2;
/** Stops a crew can carry material for before it has to come back and restock. */
const CAPACITY = { hearthAt: 4, todayAt: 2 } as const;
/** Today a household is only known once its call has worked through the queue. */
const KNOWN_LAG = { hearthAt: 0, todayAt: 2 } as const;

export type Household = { lon: number; lat: number; needsAt: number };
export type HouseholdState = "unaffected" | "waiting" | "reached";
export type SideKey = "hearthAt" | "todayAt";

/**
 * Deterministic, so the dots sit in the same places on every render and every
 * reload — a demo that reshuffles itself is impossible to talk over.
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

function makeHouseholds(n: number, seed: number): Household[] {
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

export const HOUSEHOLDS: Household[] = makeHouseholds(140, 20240708);

/** One stretch of a crew's trip, in continuous hours. */
export type Leg = { from: [number, number]; to: [number, number]; t0: number; t1: number };

export type SideSim = {
  /** Hour each household was reached, or null if the run ended first. */
  reachAt: (number | null)[];
  legs: Leg[][]; // per crew, in order
  station: number[]; // per crew
  tours: number;
  stops: number;
};

const dist2 = (a: [number, number], b: [number, number]) =>
  (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2;

/**
 * One pass over the twelve hours. Both sides get the same crews, the same
 * stations and the same two hours per tour; the only differences are how many
 * stops a crew can serve before restocking, and how late a household becomes
 * known. That is the whole claim: same deployments, more people reached, because
 * knowing who needs help lets a crew plan a round instead of chasing one call.
 */
function runSide(which: SideKey): SideSim {
  const capacity = CAPACITY[which];
  const lag = KNOWN_LAG[which];

  const reachAt: (number | null)[] = HOUSEHOLDS.map(() => null);
  const taken = HOUSEHOLDS.map(() => false);

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

  for (let h = 0; h < RUN_HOURS; h++) {
    for (let c = 0; c < CREW_COUNT; c++) {
      if (freeAt[c] > h) continue;

      const base = STATIONS[station[c]].at;
      const open = HOUSEHOLDS.map((hh, i) => ({ hh, i }))
        .filter(({ hh, i }) => !taken[i] && hh.needsAt + lag <= h)
        .sort((a, b) => dist2(base, [a.hh.lon, a.hh.lat]) - dist2(base, [b.hh.lon, b.hh.lat]))
        .slice(0, capacity);

      if (open.length === 0) continue;

      // out to each stop in turn, then back to the station to restock
      const points: [number, number][] = [base, ...open.map(({ hh }) => [hh.lon, hh.lat] as [number, number]), base];
      const span = TOUR_HOURS / (points.length - 1);

      for (let k = 0; k < points.length - 1; k++) {
        legs[c].push({
          from: points[k],
          to: points[k + 1],
          t0: h + k * span,
          t1: h + (k + 1) * span,
        });
      }

      open.forEach(({ i }, k) => {
        taken[i] = true;
        reachAt[i] = Math.min(RUN_HOURS, Math.ceil(h + (k + 1) * span));
        stops += 1;
      });

      freeAt[c] = h + TOUR_HOURS;
      tours += 1;
    }
  }

  return { reachAt, legs, station, tours, stops };
}

export const SIDES: Record<SideKey, SideSim> = {
  hearthAt: runSide("hearthAt"),
  todayAt: runSide("todayAt"),
};

/** What a household looks like at a given hour, under one approach. */
export function stateAt(i: number, hour: number, which: SideKey): HouseholdState {
  if (hour < HOUSEHOLDS[i].needsAt) return "unaffected";
  const at = SIDES[which].reachAt[i];
  return at != null && hour >= at ? "reached" : "waiting";
}

export function tallyAt(hour: number, which: SideKey): Record<HouseholdState, number> {
  const t: Record<HouseholdState, number> = { unaffected: 0, waiting: 0, reached: 0 };
  for (let i = 0; i < HOUSEHOLDS.length; i++) t[stateAt(i, hour, which)] += 1;
  return t;
}

/** Every crew's position at a continuous time, or parked at its station. */
export function vehiclesAt(time: number, which: SideKey): [number, number][] {
  const sim = SIDES[which];
  const out: [number, number][] = [];

  for (let c = 0; c < CREW_COUNT; c++) {
    const leg = sim.legs[c].find((l) => time >= l.t0 && time <= l.t1);
    if (!leg) continue; // parked: drawn only when it is actually out
    const p = (time - leg.t0) / Math.max(leg.t1 - leg.t0, 1e-6);
    out.push([leg.from[0] + (leg.to[0] - leg.from[0]) * p, leg.from[1] + (leg.to[1] - leg.from[1]) * p]);
  }
  return out;
}

/** Deployments run so far, for the counter beside the map. */
export function toursBy(hour: number, which: SideKey): number {
  const sim = SIDES[which];
  let n = 0;
  for (let c = 0; c < CREW_COUNT; c++) {
    n += sim.legs[c].filter((l) => l.from === STATIONS[sim.station[c]].at && l.t0 < hour).length;
  }
  return n;
}

/** Formats a count the same way everywhere in the simulation. */
export const count = new Intl.NumberFormat("en-US");
