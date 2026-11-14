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
  // A real Harris County address, so the aerial tile and the scan have somewhere
  // to point. The resident living at it is synthetic, as every patient here is.
  buildingLabel: "1720 Crestdale Dr, Houston, TX 77080",
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
  { at: 16000, from: "hearth", text: "Four hours, noted. Where in your home is the concentrator kept?" },
  { at: 20200, from: "resident", text: "In the back bedroom, to the left of the window." },
  { at: 22400, from: "hearth", text: "Back bedroom, left of the window. Can it be moved, so that it could leave with you if a crew came?" },
  { at: 27000, from: "resident", text: "It's on wheels, so it rolls, but it's too heavy for me to carry down the stairs. And it only runs plugged in." },
  { at: 31500, from: "hearth", text: "Noted: it rolls, it cannot be carried down by you, and it needs mains power. Is there anyone else in the home who would need help leaving?" },
  { at: 36200, from: "resident", text: "No, just me. I use a walker though." },
  { at: 38700, from: "hearth", text: "Noted, a walker. Last one: if a crew came to your door, which entrance should they use?" },
  { at: 43400, from: "resident", text: "The north door. The front has three steps and the lift has been out since July." },
  { at: 47100, from: "hearth", text: "North door, no lift, third floor. You're on the list. Nothing changes for you today, and no one is coming now. If the power goes out in your area, a dispatcher will see your name and this call. You can change any of this yourself from the link we're sending to this number." },
  { at: 54600, from: "resident", text: "Alright. Thank you." },
];

/** What the call captures. `after` is the line of ENROLMENT_CALL whose answer fills the field in. */
export const ENROLMENT_FIELDS: { label: string; value: string; after: number }[] = [
  { label: "Device", value: "Oxygen concentrator", after: 1 },
  { label: "Battery backup", value: "About 4 hours", after: 5 },
  { label: "Where the device is", value: "Back bedroom, left of the window", after: 7 },
  { label: "Can it be moved", value: "Rolls on wheels; too heavy to carry downstairs; mains only", after: 9 },
  { label: "Household", value: "Lives alone; uses a walker", after: 11 },
  { label: "Entrance", value: "North door, step-free", after: 13 },
  { label: "Floor", value: "3rd, no working lift", after: 13 },
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

// --- The county model behind the side-by-side and the full run --------------
//
// Takes a set of households and works out who a fleet reaches over a day, under
// two dispatch regimes. Where the households come from is decided in simSource.ts
// — the real replay when an API answers, a drawn fixture when none does.

/** A full day. An outage that ends in twelve hours is not the one Hearth is for. */
export const RUN_HOURS = 24;

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

// --- Identical on both sides ------------------------------------------------
/** Degrees of ground covered per hour. Same vans, same roads, same speed. */
const CRUISE = 0.34;
/** Hours spent at a door. Same job either way. */
const SERVICE_H = 0.2;
/** How finely the dispatcher reconsiders. */
export const DT = 0.25;
/**
 * Hours of running a single delivery buys. Past this a household that was helped
 * needs helping again — which is the thing a one-visit-per-person picture misses.
 */
const REFILL_H = 9;

// --- Different, and why -----------------------------------------------------
const CAPACITY = { hearthAt: 4, todayAt: 3 } as const;
/** How far a crew will go for the next stop on a round it is already out on. */
const CHAIN_RADIUS = { hearthAt: Infinity, todayAt: 0.18 } as const;
/**
 * Today's phone tree. Hearth has the registry, so everyone is visible the moment
 * their power goes. Today a household is visible once its call has been answered:
 * calls wait in one queue and are taken in the order they rang, by a few operators
 * who each take one call at a time — the details, then writing up the order. Three
 * lines at half an hour a call is about six households an hour. An assumption, not
 * a measurement.
 */
export const OPERATORS = 3;
const CALL_H = 0.5;
/**
 * The share of households that ever reach the dispatcher on their own. Hearth has
 * the registry, so all of them. Without it the people most likely never to call
 * are the ones this is for: too unwell to hold, no phone charge, no idea the
 * county would come. That gap, not idle crews, is where the difference lives —
 * and it is an assumption, like the queue rate.
 */
const CALLS_IN = { hearthAt: 1, todayAt: 0.7 } as const;

/** Stable per-household, so the same households are unreachable on every run. */
const callsIn = (i: number, share: number): boolean =>
  share >= 1 || ((Math.imul(i + 1, 2654435761) >>> 8) % 1000) / 1000 < share;

/**
 * Everything the central planner needs to plan the Hearth side's day (POST /api/sim/day).
 * The page sends these with its households, so the API keeps no copy that could drift.
 */
export const DAY_CONSTANTS = {
  stations: STATIONS,
  crewsPerStation: CREWS_PER_STATION,
  cruise: CRUISE,
  serviceH: SERVICE_H,
  dt: DT,
  runHours: RUN_HOURS,
  refillH: REFILL_H,
  capacity: CAPACITY.hearthAt,
};

export type Household = {
  lon: number;
  lat: number;
  /** Hour this household first needs help. From real backup hours where available. */
  needsAt: number;
  /** True for households whose need comes back once a delivery runs down. */
  repeats: boolean;
};

export type HouseholdState = "unaffected" | "waiting" | "resupply" | "reached" | "restocked";
export type SideKey = "hearthAt" | "todayAt";

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
  const SPREAD_LON = 0.44;
  const SPREAD_LAT = 0.31;

  for (let i = 0; i < n; i++) {
    const angle = rnd() * Math.PI * 2;
    const radius = Math.sqrt(rnd());
    out.push({
      lon: COUNTY_CENTER[0] + Math.cos(angle) * radius * SPREAD_LON,
      lat: COUNTY_CENTER[1] + Math.sin(angle) * radius * SPREAD_LAT,
      needsAt: rnd() * rnd() * 10,
      repeats: rnd() < 0.45,
    });
  }
  return out;
}

export type Leg = {
  from: [number, number];
  to: [number, number];
  t0: number;
  t1: number;
  departure: boolean;
};

/** A van in flight: where it is, and which way it is pointing. */
export type Vehicle = { lon: number; lat: number; bearing: number };

export type SimEvent = {
  t: number;
  kind: "call" | "dispatch" | "arrive" | "restock";
  text: string;
  stops?: number;
};

/** One visit a household needs. A repeat household generates another once served. */
type Job = {
  h: number;
  dueAt: number;
  /** When the dispatcher has the order: at once with the registry, after the call today. */
  knownAt: number | null;
  /** When a van was sent for it. */
  sentAt: number | null;
  servedAt: number | null;
  refill: boolean;
};

/** One call into today's queue. `answeredAt` is when an operator picked it up. */
type Call = { job: Job; at: number; answeredAt: number | null };

export type SideSim = {
  jobs: Job[];
  calls: Call[];
  legs: Leg[][];
  station: number[];
  tours: number;
  stops: number;
  refills: number;
  events: SimEvent[];
};

/**
 * Hours households spent waiting on one side, a first delivery counting twice a
 * restock, and a visit that never came counted to the end of the day. The number
 * the planner's routes are held against the browser's own.
 */
export function weightedWait(side: SideSim): number {
  return side.jobs.reduce((sum, j) => sum + (j.refill ? 1 : 2) * ((j.servedAt ?? RUN_HOURS) - j.dueAt), 0);
}

const dist = (a: [number, number], b: [number, number]) =>
  Math.hypot(a[0] - b[0], a[1] - b[1]);

const bearingOf = (from: [number, number], to: [number, number]) =>
  (Math.atan2(to[0] - from[0], to[1] - from[1]) * 180) / Math.PI;

/**
 * One pass over the day, at the same cruising speed and the same time at the door
 * on both sides. What differs is whether the dispatcher already knows who needs
 * help — and, once a delivery runs down, whether anyone notices it has.
 */
function runSide(households: Household[], which: SideKey): SideSim {
  const capacity = CAPACITY[which];
  const chainRadius = CHAIN_RADIUS[which];
  const outbound = which === "hearthAt";

  const jobs: Job[] = [];
  const calls: Call[] = [];
  const events: SimEvent[] = [];
  const lineFree: number[] = Array(OPERATORS).fill(0);
  let nextCall = 0; // calls[] stays in ringing order, and is answered strictly in it

  const pos = (j: Job): [number, number] => [households[j.h].lon, households[j.h].lat];

  /** A need starts. Hearth hears at once; today hears when the call is answered, if one comes. */
  const addJob = (h: number, dueAt: number, refill: boolean) => {
    const job: Job = { h, dueAt, knownAt: null, sentAt: null, servedAt: null, refill };
    jobs.push(job);
    if (outbound) {
      job.knownAt = dueAt;
      events.push({ t: dueAt, kind: "call", text: `Called household ${h + 1} — on the registry, device down` });
    } else if (callsIn(h, CALLS_IN.todayAt)) {
      // people ring some time in the hour after their device runs out, not the moment it does
      const at = dueAt + mulberry32(jobs.length)();
      let k = calls.length;
      while (k > nextCall && calls[k - 1].at > at) k -= 1;
      calls.splice(k, 0, { job, at, answeredAt: null });
    }
  };
  households.forEach((h, i) => addJob(i, h.needsAt, false));

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
  let refills = 0;

  for (let t = 0; t <= RUN_HOURS; t += DT) {
    // today's operators work the queue in the order it rang, one call each at a time
    while (nextCall < calls.length) {
      const call = calls[nextCall];
      const line = lineFree.indexOf(Math.min(...lineFree));
      const answeredAt = Math.max(call.at, lineFree[line]);
      if (answeredAt > t) break;
      call.answeredAt = answeredAt;
      lineFree[line] = answeredAt + CALL_H;
      call.job.knownAt = answeredAt + CALL_H; // the order exists once the call is written up
      const held = answeredAt - call.at;
      events.push({
        t: answeredAt,
        kind: "call",
        text:
          held < 1 / 60
            ? `Household ${call.job.h + 1} got through — no wait`
            : `Household ${call.job.h + 1} got through — after ${held < 1 ? `${Math.round(held * 60)} min` : `${held.toFixed(1)} h`} on hold`,
      });
      nextCall += 1;
    }

    const waiting = jobs.filter(
      (j) => j.sentAt === null && j.dueAt <= t && j.knownAt !== null && j.knownAt <= t,
    );
    const free = freeAt.flatMap((f, c) => (f <= t ? [c] : []));

    // Every free van goes before any round takes a second stop, so none sits at
    // its station while an order waits. Someone still waiting on a first delivery
    // goes ahead of a restock — a household that has had nothing yet is the worse
    // problem, whichever side is dispatching — and within that, the closest
    // van-and-order pair goes first.
    const rounds: { c: number; route: Job[] }[] = [];
    while (waiting.length && free.length) {
      const firstsLeft = waiting.some((j) => !j.refill);
      let pick = { w: -1, f: -1, d: Infinity };
      waiting.forEach((j, w) => {
        if (firstsLeft && j.refill) return;
        free.forEach((c, f) => {
          const d = dist(STATIONS[station[c]].at, pos(j));
          if (d < pick.d) pick = { w, f, d };
        });
      });
      rounds.push({ c: free.splice(pick.f, 1)[0], route: waiting.splice(pick.w, 1) });
    }

    // More orders than vans: a round chains what is genuinely on its way, first
    // deliveries still ahead of restocks.
    for (const { route } of rounds) {
      while (route.length < capacity && waiting.length) {
        const at = pos(route[route.length - 1]);
        const near = waiting
          .map((j, k) => ({ k, j, d: dist(at, pos(j)) }))
          .filter((n) => n.d <= chainRadius)
          .sort((a, b) => Number(a.j.refill) - Number(b.j.refill) || a.d - b.d);
        if (!near.length) break;
        route.push(waiting.splice(near[0].k, 1)[0]);
      }
    }

    for (const { c, route } of rounds) {
      const base = STATIONS[station[c]].at;
      for (const j of route) j.sentAt = t;

      events.push({
        t,
        kind: "dispatch",
        stops: route.length,
        text:
          route.length > 1
            ? `Crew ${c + 1} out of ${STATIONS[station[c]].name} — ${route.length} stops chained`
            : `Crew ${c + 1} out of ${STATIONS[station[c]].name} — 1 stop, then back`,
      });

      let clock = t;
      let from: [number, number] = base;

      for (let k = 0; k < route.length; k++) {
        const j = route[k];
        const to = pos(j);
        const travel = dist(from, to) / CRUISE;
        legs[c].push({ from, to, t0: clock, t1: clock + travel, departure: k === 0 });
        clock += travel;
        // parked at the door; the household changes colour when the van pulls away
        legs[c].push({ from: to, to, t0: clock, t1: clock + SERVICE_H, departure: false });
        clock += SERVICE_H;

        j.servedAt = clock;
        stops += 1;
        if (j.refill) refills += 1;
        events.push({
          t: clock,
          kind: j.refill ? "restock" : "arrive",
          text: j.refill
            ? `Crew ${c + 1} restocked household ${j.h + 1}`
            : `Crew ${c + 1} helped household ${j.h + 1}`,
        });

        // a delivery runs down: a repeat household needs another visit later, and
        // today has to hear about it all over again
        if (households[j.h].repeats && clock + REFILL_H <= RUN_HOURS) {
          addJob(j.h, clock + REFILL_H, true);
        }

        from = to;
      }

      const home = dist(from, base) / CRUISE;
      legs[c].push({ from, to: base, t0: clock, t1: clock + home, departure: false });
      clock += home;

      freeAt[c] = clock;
      tours += 1;
    }
  }

  events.sort((a, b) => a.t - b.t);
  return { jobs, calls, legs, station, tours, stops, refills, events };
}

export type CountySim = {
  households: Household[];
  sides: Record<SideKey, SideSim>;
  stateAt(i: number, hour: number, which: SideKey): HouseholdState;
  tallyAt(hour: number, which: SideKey): Record<HouseholdState, number>;
  vehiclesAt(time: number, which: SideKey): Vehicle[];
  toursBy(time: number, which: SideKey): number;
  outNow(time: number, which: SideKey): number;
  logAt(time: number, which: SideKey, n?: number, kinds?: SimEvent["kind"][]): SimEvent[];
  backlogAt(time: number, which: SideKey): number;
  /** Calls that have rung and are still on hold: always none with the registry. */
  queueAt(time: number, which: SideKey): number;
  chainedShare(which: SideKey): number;
  restocksBy(time: number, which: SideKey): number;
};

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const point = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && num(v[0]) && num(v[1]);
const hourOrNone = (v: unknown) => v === null || num(v);

/**
 * A Hearth side planned by the API (POST /api/sim/day), checked before the page
 * draws it. Anything that is not the shape `runSide` produces is refused, and the
 * caller falls back to the browser's own routes: a bad answer must not blank a map.
 */
export function parseSide(raw: unknown, households: number): SideSim | null {
  if (typeof raw !== "object" || raw === null) return null;
  const s = raw as Record<string, unknown>;
  const { jobs, calls, legs, station, events } = s;
  if (![jobs, calls, legs, station, events].every(Array.isArray)) return null;
  if (![s.tours, s.stops, s.refills].every(num)) return null;
  const okLeg = (l: Record<string, unknown>) =>
    l && point(l.from) && point(l.to) && num(l.t0) && num(l.t1) && typeof l.departure === "boolean";
  const okJob = (j: Record<string, unknown>) =>
    j && Number.isInteger(j.h) && (j.h as number) >= 0 && (j.h as number) < households && num(j.dueAt) &&
    hourOrNone(j.knownAt) && hourOrNone(j.sentAt) && hourOrNone(j.servedAt) && typeof j.refill === "boolean";
  const okEvent = (e: Record<string, unknown>) =>
    e && num(e.t) && typeof e.text === "string" && ["call", "dispatch", "arrive", "restock"].includes(e.kind as string);
  const L = legs as unknown[];
  if (L.length !== CREW_COUNT || (station as unknown[]).length !== CREW_COUNT) return null;
  if (!L.every((van) => Array.isArray(van) && van.every(okLeg))) return null;
  if (!(jobs as Record<string, unknown>[]).every(okJob) || !(events as Record<string, unknown>[]).every(okEvent)) return null;
  return raw as SideSim;
}

/** `hearthSide` is the central planner's day when the API answered with one; without it the browser routes both sides. */
export function buildCounty(households: Household[], hearthSide?: SideSim): CountySim {
  const sides: Record<SideKey, SideSim> = {
    hearthAt: hearthSide ?? runSide(households, "hearthAt"),
    todayAt: runSide(households, "todayAt"),
  };

  // Jobs grouped by household once, rather than filtering the whole list per dot:
  // the dots are now recomputed continuously, so this runs a few hundred times a
  // second and the scan would have been the cost.
  const byHousehold: Record<SideKey, Job[][]> = {
    hearthAt: households.map(() => []),
    todayAt: households.map(() => []),
  };
  for (const key of ["hearthAt", "todayAt"] as SideKey[]) {
    for (const j of sides[key].jobs) byHousehold[key][j.h].push(j);
  }

  /**
   * Each map is its dispatcher's view: a need shows once the dispatcher has the
   * order. With the registry that is the moment the device goes down; today it is
   * once the call has been answered and written up, so a household still on hold,
   * or one that never calls, stays grey. `time` is continuous: a household turns
   * green the moment its van pulls away.
   */
  const stateAt = (i: number, time: number, which: SideKey): HouseholdState => {
    const mine = byHousehold[which][i];

    let anyDue = false;
    let openNow = false;
    let servedBefore = false;
    let refillDone = false;

    for (const j of mine) {
      if (j.knownAt === null || j.knownAt > time) continue;
      anyDue = true;
      if (j.servedAt === null || j.servedAt > time) {
        openNow = true;
      } else {
        servedBefore = true;
        if (j.refill) refillDone = true;
      }
    }

    if (!anyDue) return "unaffected";
    // settled: purple if a second delivery has actually been made, green if the
    // first one is still holding
    if (!openNow) return refillDone ? "restocked" : "reached";
    // blue once they have been helped before: this is a resupply, not a first call
    return servedBefore ? "resupply" : "waiting";
  };

  const vehiclesAt = (time: number, which: SideKey): Vehicle[] => {
    const out: Vehicle[] = [];
    for (let c = 0; c < CREW_COUNT; c++) {
      const legs = sides[which].legs[c];
      const k = legs.findIndex((l) => time >= l.t0 && time <= l.t1);
      if (k < 0) continue;
      const leg = legs[k];
      // parked at a door: keep facing the way it drove in
      // by value: a side from the API has its own array for every point
      const parked = leg.from[0] === leg.to[0] && leg.from[1] === leg.to[1];
      const aim = parked && k > 0 ? legs[k - 1] : leg;
      const p = (time - leg.t0) / Math.max(leg.t1 - leg.t0, 1e-6);
      out.push({
        lon: leg.from[0] + (leg.to[0] - leg.from[0]) * p,
        lat: leg.from[1] + (leg.to[1] - leg.from[1]) * p,
        bearing: bearingOf(aim.from, aim.to),
      });
    }
    return out;
  };

  return {
    households,
    sides,
    stateAt,
    vehiclesAt,
    tallyAt(hour, which) {
      const t: Record<HouseholdState, number> = {
        unaffected: 0,
        waiting: 0,
        resupply: 0,
        reached: 0,
        restocked: 0,
      };
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
    logAt(time, which, n = 7, kinds) {
      const upto = sides[which].events.filter(
        (e) => e.t <= time && (!kinds || kinds.includes(e.kind)),
      );
      return upto.slice(Math.max(0, upto.length - n));
    },
    backlogAt(time, which) {
      let n = 0;
      for (const j of sides[which].jobs) {
        if (j.knownAt === null || j.knownAt > time) continue;
        if (j.servedAt === null || j.servedAt > time) n += 1;
      }
      return n;
    },
    queueAt(time, which) {
      return sides[which].calls.filter(
        (c) => c.at <= time && (c.answeredAt === null || c.answeredAt > time),
      ).length;
    },
    chainedShare(which) {
      const rounds = sides[which].events.filter((e) => e.kind === "dispatch");
      if (!rounds.length) return 0;
      return rounds.filter((e) => (e.stops ?? 1) > 1).length / rounds.length;
    },
    restocksBy(time, which) {
      return sides[which].events.filter((e) => e.kind === "restock" && e.t <= time).length;
    },
  };
}

/** What a panel shows before any fetch resolves, and if none ever does. */
export const FIXTURE_COUNTY: CountySim = buildCounty(drawHouseholds());

/** Formats a count the same way everywhere in the simulation. */
export const count = new Intl.NumberFormat("en-US");
