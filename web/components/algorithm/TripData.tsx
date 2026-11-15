"use client";

import { useState } from "react";
import Choice from "@/components/Choice";

const SOURCES = {
  costar: { name: "CoStar", color: "var(--series-1)", what: "Property records: 3,339 in the kit, 1,758 in the Houston market." },
  matterport: { name: "Matterport", color: "var(--series-2)", what: "3D scans of the buildings CoStar lists: 1,732 of the Houston 1,758 have one. A scan shows a unit type or a lobby, never a resident's own rooms." },
  vexcel: { name: "Vexcel", color: "var(--series-3)", what: "Aerial imagery of the same properties, 2023 to 2026 captures over Houston." },
} as const;
type Source = keyof typeof SOURCES;
type Field = [Source, string, string]; // source, field, what it does to the path

// shortcut: the numbers in these lines are copied from config/assumptions.yaml; serve them from the API if they start changing
const LEGS: { name: string; plans: string; fields: Field[] }[] = [
  {
    name: "The home", plans: "How long this person has: the deadline in the score.",
    fields: [
      ["costar", "Year built and construction material", "How fast the home heats up once the power is out. Older and lighter buildings turn unsafe sooner."],
      ["vexcel", "Roof material and tree cover", "A dark, unshaded roof shortens the hours a heat-sensitive patient has left."],
      ["vexcel", "The aerial tile, read by a vision model", "Roof tone, where the roof material alone does not say."],
    ],
  },
  {
    name: "Staging lot", plans: "Where the crews gather before they roll.",
    fields: [
      ["costar", "Surface parking spaces and lot size", "A lot needs at least 100 surface spaces and must not be residents' parking. The nearest three are offered to the dispatcher."],
      ["costar", "ZIP code", "The lot must be in a ZIP nobody has asked for help from."],
      ["vexcel", "The aerial tile of the lot, read by a vision model", "Where the open parking is and how a van gets in."],
    ],
  },
  {
    name: "The drive", plans: "Every leg the pairing and the route search weigh.",
    fields: [
      ["costar", "Latitude and longitude", "Every distance in the plan: crew to door, door to refuge, lot to the outage. Straight-line km times 1.4, at 40 km/h."],
    ],
  },
  {
    name: "The curb", plans: "Where the drive ends and the walk begins.",
    fields: [
      ["vexcel", "Detected driveways, parking, loading zones, ramps and entrances", "Where the van stops and which side of the building the way in is on."],
      ["vexcel", "The aerial tile, read by a vision model", "The entrance pin, until the resident places their own."],
    ],
  },
  {
    name: "Door to unit", plans: "Minutes inside the building, which every route pays at every stop.",
    fields: [
      ["costar", "Stories above grade", "10 minutes inside, plus 4 for every floor climbed when there is no working elevator."],
      ["costar", "Passenger elevators and the walk-up flag", "Whether those stairs are climbed at all. No record says the elevator runs today, so someone has to say so."],
      ["matterport", "Lobby panoramas, read by a vision model", "A step-free entrance, steps at the door, an elevator in view."],
    ],
  },
  {
    name: "Inside the unit", plans: "The last walk, from the door to the machine.",
    fields: [
      ["costar", "Matterport model ids, floor plans and unit numbers", "Which scan to open for this resident's unit type."],
      ["matterport", "Scan spots and which spots each can see", "The graph the indoor route is planned over."],
      ["matterport", "Room labels and sizes, door and hallway widths", "The crew's brief: rooms on the way, the narrowest door, steps inside."],
    ],
  },
  {
    name: "The refuge", plans: "Where a ride ends, which sets the second half of its drive.",
    fields: [
      ["costar", "Property type", "A refuge is a hotel or senior housing, the nearest within 15 km."],
      ["costar", "Unit and room counts", "It takes 5% of its units, at least one person. A full refuge sends the next ride further."],
      ["costar", "ZIP code, construction and operating status", "It must be outside the dark area, standing, and not a hotel listed as closed."],
      ["matterport", "Lobby panoramas, read by a vision model", "A wheelchair user or bedbound patient needs a step-free entrance, and an elevator above the first floor."],
      ["vexcel", "Search of aerial tiles by description", "When no refuge passes: schools, churches and community centers outside the dark area, as places to call about."],
    ],
  },
];

const Dot = ({ source }: { source: Source }) => <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: SOURCES[source].color }} />;

/** What a crew spends inside one building: the rule in `service_minutes`, on a slider. */
function StairsSum() {
  const [floor, setFloor] = useState(3);
  const [elevator, setElevator] = useState(false);
  return (
    <div className="mt-5 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm">
        <label className="min-w-[180px] flex-1">
          <span style={{ color: "var(--text-muted)" }}>Patient&rsquo;s floor: </span><span className="tnum font-semibold">{floor}</span>
          <input type="range" min={1} max={12} value={floor} onChange={(e) => setFloor(+e.target.value)} className="mt-1 block w-full" style={{ accentColor: "var(--text-primary)" }} />
        </label>
        <div className="flex gap-1.5" role="group" aria-label="Elevator">
          <Choice on={!elevator} onClick={() => setElevator(false)}>No working elevator</Choice>
          <Choice on={elevator} onClick={() => setElevator(true)}>Elevator running</Choice>
        </div>
      </div>
      <p className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }} aria-live="polite">
        <span className="display tnum mr-2 text-4xl" style={{ color: "var(--text-primary)" }}>{elevator ? 10 : 10 + 4 * floor} min</span>
        inside the building{elevator ? "" : `: 10 + 4 × ${floor}`}
      </p>
    </div>
  );
}

/** One trip, leg by leg: pick a leg to see which building data shapes it. */
export default function TripData() {
  const [on, setOn] = useState(0);
  const leg = LEGS[on];
  return (
    <div>
      <ul className="mb-6 grid gap-x-8 gap-y-2 text-sm md:grid-cols-3">
        {(Object.keys(SOURCES) as Source[]).map((s) => (
          <li key={s} className="flex gap-2 leading-snug" style={{ color: "var(--text-secondary)" }}>
            <span className="mt-1"><Dot source={s} /></span>
            <span><strong style={{ color: "var(--text-primary)" }}>{SOURCES[s].name}.</strong> {SOURCES[s].what}</span>
          </li>
        ))}
      </ul>

      <div className="overflow-x-auto pb-2">
        <ol className="relative flex min-w-[760px]">
          <li aria-hidden className="absolute top-[15px] right-[7%] left-[7%] border-t-2" style={{ borderColor: "var(--border)" }} />
          {LEGS.map((l, i) => (
            <li key={l.name} className="relative flex-1">
              <button type="button" aria-pressed={i === on} onClick={() => setOn(i)} className="group flex w-full flex-col items-center gap-1.5 px-1 text-center">
                <span className="tnum flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold"
                  style={i === on ? { background: "var(--text-primary)", borderColor: "var(--text-primary)", color: "var(--surface-1)" }
                    : { background: "var(--surface-1)", borderColor: "var(--text-muted)", color: "var(--text-primary)" }}>{i + 1}</span>
                <span className={`text-sm group-hover:underline ${i === on ? "font-semibold" : ""}`}>{l.name}</span>
                <span className="flex gap-1" aria-label={[...new Set(l.fields.map((f) => SOURCES[f[0]].name))].join(", ")}>
                  {[...new Set(l.fields.map((f) => f[0]))].map((s) => <Dot key={s} source={s} />)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-4 rounded-2xl border p-7" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }} aria-live="polite">
        <h3 className="text-lg font-semibold">{on + 1}. {leg.name}</h3>
        <p className="mt-1 mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>{leg.plans}</p>
        <ul>
          {leg.fields.map(([source, field, use]) => (
            <li key={source + field} className="grid gap-x-6 gap-y-1 border-t py-3 text-sm md:grid-cols-[150px_minmax(0,2fr)_minmax(0,3fr)]" style={{ borderColor: "var(--border)" }}>
              <span className="flex items-center gap-2 self-start" style={{ color: "var(--text-muted)" }}><Dot source={source} />{SOURCES[source].name}</span>
              <span className="font-semibold">{field}</span>
              <span className="leading-relaxed" style={{ color: "var(--text-secondary)" }}>{use}</span>
            </li>
          ))}
        </ul>
        {leg.name === "Door to unit" && <StairsSum />}
      </div>
    </div>
  );
}
