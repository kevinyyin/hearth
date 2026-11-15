import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Algorithm · Hearth" };

// shortcut: the constants below are copied from config/assumptions.yaml (planner, travel, building, refuge, dispatch,
// staging, risk_weight); serve them from the API if they start changing after the demo

const STEPS: { n: string; name: string; method: string; body: ReactNode }[] = [
  {
    n: "1",
    name: "Pair crews with people",
    method: "Assignment problem, solved exactly (Hungarian method)",
    body: (
      <>
        <p>
          Every free crew and every open need go into one table. Each cell is what that crew is worth to that
          person: the drop in the score from sending the crew now instead of not at all in the next 6 hours,
          divided by the crew-hours the job takes (drive, time inside the building, and the ride to the refuge
          if there is one).
        </p>
        <p>
          The solver picks one need per crew so the total is the largest possible. A nearest-crew rule can send
          the only close van to the wrong door; this cannot. A delivery is only allowed to a crew from the
          patient&rsquo;s own supplier with a unit left in stock. If a supplier is short, its least valuable
          deliveries are dropped and the table is solved again.
        </p>
      </>
    ),
  },
  {
    n: "2",
    name: "Build each crew a route",
    method: "Adaptive large neighborhood search (ALNS)",
    body: (
      <>
        <p>
          The pairing is the first stop of each route. The remaining needs are inserted, most urgent first,
          wherever they lower the score most. Then the search repeats: take about 15% of the stops out, put
          them back better, keep the result if it helps.
        </p>
        <p>
          Three ways to take stops out (at random, the ones paying the most where they sit, a cluster of
          neighbors) and two ways to put them back (cheapest place first, or the stop that loses most by not
          getting its best place first). Whichever finds a new best plan is picked more often. A worse plan is
          sometimes accepted early on, less and less as the search cools, so it does not get stuck. The answer
          is never worse than the pairing it started from, and the same inputs always give the same routes.
        </p>
        <p>
          Only the first stop of each route is committed. At the next step the whole plan is made again with
          whoever has called since.
        </p>
      </>
    ),
  },
  {
    n: "3",
    name: "Walk the last hundred feet",
    method: "Shortest path (Dijkstra) over the 3D scan",
    body: (
      <>
        <p>
          A Matterport scan is a set of spots where the camera stood, and each spot lists the spots it can see.
          A chain of them is a way a person can actually walk, so no floor polygon is needed. The route runs
          from the entrance to the spot nearest the resident&rsquo;s machine, and is drawn on the scan&rsquo;s
          own floor plan for the crew.
        </p>
        <p>
          When nobody has pinned the machine, it is assumed to be in the farthest room that was scanned from
          more than one spot, which passes over closets and bathrooms. The page labels that as an assumption.
        </p>
      </>
    ),
  },
];

const RUNS: [string, string][] = [
  ["Results: Hearth", "The simple rule: highest weight per hour left first, to the nearest free crew. It is the published baseline."],
  ["Results: Hearth, pairing and route search", "Steps 1 and 2. 15 search rounds per half-hour step, to keep a county replay fast."],
  ["Results: the full county run", "Steps 1 and 2 with vans that make 4 stops a round and return to their station. 200 search rounds per step."],
  ["Live dispatch", "A model orders the queue, with a rule as its fallback. Step 1's solver then matches crews: a crew carrying what the device needs first, then the least driving."],
  ["Inside a building", "Step 3, in the browser, on the scan the building's CoStar record links to."],
];

type Row = { field: string; use: string };
const SOURCES: { name: string; what: string; rows: Row[] }[] = [
  {
    name: "CoStar",
    what: "Property records. 3,339 in the kit, 1,758 of them in the Houston market.",
    rows: [
      { field: "Latitude and longitude", use: "Every distance in the plan: crew to door, door to refuge, lot to the outage." },
      { field: "Stories above grade", use: "Time inside the building: 10 minutes, plus 4 per floor when there is no working elevator. That time is part of every route." },
      { field: "Passenger elevators and the walk-up flag", use: "The same service time, and whether a wheelchair user or a bedbound patient can be moved to a refuge above the first floor." },
      { field: "Property type", use: "A refuge is a hotel or senior housing, the nearest within 15 km. Patients in the replay are placed in multifamily buildings and senior housing." },
      { field: "Unit and room counts", use: "How many people a refuge can take: 5% of its units, at least one. A full refuge sends the next ride further." },
      { field: "ZIP code", use: "A refuge or staging lot must be outside the dark area. An unknown ZIP does not count as outside." },
      { field: "Construction and hotel operating status", use: "A building that is not standing, or a hotel listed as closed, is never a destination." },
      { field: "Year built and construction material", use: "How fast a home heats up once the power is out, which sets the hours a heat-sensitive patient has left. That is one of the two deadlines in the score." },
      { field: "Surface parking spaces and lot size", use: "Staging lots where crews start: at least 100 surface spaces, not residents' parking, nearest to the open requests." },
      { field: "Matterport model ids, floor plans and unit numbers", use: "Which scan to open for a resident's unit type. 1,732 of the 1,758 Houston buildings have one." },
    ],
  },
  {
    name: "Matterport",
    what: "3D scans of the buildings CoStar lists. A scan shows a unit type or a lobby, never a resident's own rooms.",
    rows: [
      { field: "Scan spots and which spots each can see", use: "The graph the indoor route is planned over." },
      { field: "Panoramas, read by a vision model", use: "Step-free entrance, steps at the entrance, an elevator in view, door and hallway widths. These decide which refuges a patient can enter." },
      { field: "Room labels and dimensions", use: "The crew's brief for the inside of the unit: rooms, narrowest door, steps." },
    ],
  },
  {
    name: "Vexcel",
    what: "Aerial imagery of the same properties, 2023 to 2026 captures over Houston.",
    rows: [
      { field: "Roof material and tree cover", use: "With CoStar's age and construction, how fast the home heats up." },
      { field: "Detected driveways, parking, loading zones, ramps and entrances", use: "Where the van stops and which side the way in is on: the point where the drive ends and the walk begins." },
      { field: "The aerial tile, read by a vision model", use: "Roof tone, and the entrance pin until the resident places their own." },
      { field: "Search of aerial tiles by description", use: "When no refuge passes: schools, churches and community centres outside the dark area, as places for a dispatcher to call about." },
    ],
  },
];

const LIMITS = [
  "Travel time is straight-line distance times 1.4, at 40 km/h. There is no road network, closure or flood layer.",
  "No record says an elevator is running today. A resident or the building office has to say so; an elevator only seen in a scan does not count until someone confirms it.",
  "A scan covers a model unit and a few rooms. The route inside is the layout of that unit type.",
  "The plan books nothing. A refuge or a staging lot is a place to call about, and a dispatcher approves every move.",
  "All patients are simulated.",
];

const WEIGHTS: [string, number][] = [["Ventilator", 5], ["Oxygen", 3], ["Home dialysis", 2], ["Feeding pump, jejunal", 2], ["Feeding pump, gastric", 1]];

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mb-4 text-[11px] font-medium tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>{children}</p>;
}

export default function AlgorithmPage() {
  const cell = "border-t px-4 py-3 align-top";
  return (
    <div className="min-h-full">
      <div className="mx-auto max-w-[1400px] px-8 pb-24">
        <header className="mb-2 flex flex-wrap items-center gap-x-7 gap-y-3 border-b py-5" style={{ borderColor: "var(--border)" }}>
          <span className="display text-2xl">Hearth</span>
          <nav className="flex flex-1 gap-6">
            <Link href="/results" className="text-sm" style={{ color: "var(--text-muted)" }}>Results</Link>
            <Link href="/dispatch" className="text-sm" style={{ color: "var(--text-muted)" }}>Dispatch</Link>
            <Link href="/algorithm" aria-current="page" className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Algorithm</Link>
          </nav>
          <Link href="/simulation" className="rounded-lg px-5 py-2.5 text-sm font-semibold" style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}>
            Run the simulation
          </Link>
        </header>

        <div className="py-12">
          <Eyebrow>How the plan is made</Eyebrow>
          <h1 className="display max-w-[18ch] text-[64px] leading-[0.98] tracking-tight">Who goes where, and by which door.</h1>
          <p className="mt-7 max-w-[60ch] text-[17px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Hearth plans a path in three steps: which crew takes which person, what order each crew works in, and
            how to get from the curb to the machine. The first two minimize one score. All three lean on what
            CoStar, Matterport and Vexcel know about the building at each end of the trip.
          </p>
        </div>

        {/* ---------- the score ---------- */}
        <section aria-labelledby="score" className="rounded-2xl border p-7" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
          <Eyebrow>The score</Eyebrow>
          <h2 id="score" className="mb-4 text-xl font-semibold">Weighted hours people spend at risk, waiting for a crew</h2>
          <div className="flex flex-wrap gap-x-14 gap-y-8">
            <div className="min-w-0 flex-[2_1_520px]">
              <p className="rounded-lg border px-4 py-3 font-mono text-sm leading-relaxed" style={{ borderColor: "var(--border)", background: "var(--surface-0)" }}>
                cost = weight × hours past the deadline + 0.1 × (weight ÷ hours left) × hours waited
              </p>
              <p className="mt-4 max-w-[68ch] text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                The deadline is the moment a person starts being at risk: their backup runs out, or their home
                turns unsafe in the heat. The first term counts every hour past it. The second is small and
                keeps a person who is not late yet worth a crew, more so the less time they have. A need no
                route reaches is charged as if it waited the full 6-hour window, so leaving someone out is
                never free.
              </p>
            </div>
            <dl className="flex-[1_1_240px] text-sm">
              <dt className="mb-2 font-medium" style={{ color: "var(--text-muted)" }}>Weight, by device</dt>
              {WEIGHTS.map(([device, w]) => (
                <div key={device} className="flex justify-between border-t py-1.5" style={{ borderColor: "var(--border)" }}>
                  <dd>{device}</dd>
                  <dd className="font-semibold">{w}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ---------- the three steps ---------- */}
        <ol className="mt-6 grid gap-6 lg:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-2xl border p-7" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
              <p className="display text-5xl" style={{ color: "var(--accent)" }}>{s.n}</p>
              <h2 className="mt-3 text-xl font-semibold">{s.name}</h2>
              <p className="mt-1 text-sm font-medium" style={{ color: "var(--text-muted)" }}>{s.method}</p>
              <div className="mt-4 space-y-3 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{s.body}</div>
            </li>
          ))}
        </ol>

        {/* ---------- where each runs ---------- */}
        <section aria-labelledby="runs" className="mt-16">
          <Eyebrow>On this site</Eyebrow>
          <h2 id="runs" className="mb-5 text-xl font-semibold">Where each step runs</h2>
          <dl className="grid gap-x-10 sm:grid-cols-2">
            {RUNS.map(([where, what]) => (
              <div key={where} className="border-t py-4" style={{ borderColor: "var(--border)" }}>
                <dt className="text-sm font-semibold">{where}</dt>
                <dd className="mt-1 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{what}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* ---------- the data ---------- */}
        <section aria-labelledby="data" className="mt-16">
          <Eyebrow>The data</Eyebrow>
          <h2 id="data" className="text-xl font-semibold">What the building data changes in the plan</h2>
          <p className="mt-2 mb-6 max-w-[68ch] text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            The three data layers of the CoStar track. Each row is a field Hearth reads and the place it enters the path.
            The keys stay on the server; the browser only ever sees the result.
          </p>
          <div className="overflow-x-auto rounded-2xl border" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead>
                <tr style={{ color: "var(--text-muted)" }}>
                  <th scope="col" className="w-[34%] px-4 py-3 font-medium">Field</th>
                  <th scope="col" className="px-4 py-3 font-medium">What it does to the path</th>
                </tr>
              </thead>
              {SOURCES.map((src) => (
                <tbody key={src.name}>
                  <tr>
                    <th scope="colgroup" colSpan={2} className="border-t px-4 py-3 text-left" style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}>
                      <span className="display text-xl">{src.name}</span>
                      <span className="ml-3 font-normal" style={{ color: "var(--text-secondary)" }}>{src.what}</span>
                    </th>
                  </tr>
                  {src.rows.map((r) => (
                    <tr key={r.field}>
                      <th scope="row" className={`${cell} font-semibold`} style={{ borderColor: "var(--border)" }}>{r.field}</th>
                      <td className={`${cell} leading-relaxed`} style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}>{r.use}</td>
                    </tr>
                  ))}
                </tbody>
              ))}
            </table>
          </div>
        </section>

        {/* ---------- limits ---------- */}
        <section aria-labelledby="limits" className="mt-16">
          <Eyebrow>Limits</Eyebrow>
          <h2 id="limits" className="mb-4 text-xl font-semibold">What the plan does not know</h2>
          <ul className="max-w-[80ch] text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {LIMITS.map((l) => (
              <li key={l} className="border-t py-3" style={{ borderColor: "var(--border)" }}>{l}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
