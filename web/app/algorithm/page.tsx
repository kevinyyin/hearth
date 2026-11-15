import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { PairingDemo, SearchDemo } from "@/components/algorithm/PlannerDemos";
import ScanRouteDemo from "@/components/algorithm/ScanRouteDemo";
import ScoreCurve from "@/components/algorithm/ScoreCurve";
import TripData from "@/components/algorithm/TripData";

export const metadata: Metadata = { title: "Algorithm · Hearth" };

// shortcut: the numbers in the text below are copied from config/assumptions.yaml; serve them from the API if they start changing
const RUNS: [string, string][] = [
  ["Results: Hearth", "The simple rule: highest weight per hour left first, to the nearest free crew. It is the published baseline."],
  ["Results: Hearth, pairing and route search", "Steps 1 and 2. 15 search rounds per half-hour step, to keep a county replay fast."],
  ["Results: the full county run", "Steps 1 and 2 with vans that make 4 stops a round and return to their station. 200 search rounds per step."],
  ["Live dispatch", "A model orders the queue, with a rule as its fallback. Step 1's solver then matches crews: a crew carrying what the device needs first, then the least driving."],
  ["Inside a building", "Step 3, in the browser, on the scan the building's CoStar record links to."],
];

const LIMITS = [
  "Travel time is straight-line distance times 1.4, at 40 km/h. There is no road network, closure or flood layer.",
  "No record says an elevator is running today. A resident or the building office has to say so; an elevator only seen in a scan does not count until someone confirms it.",
  "A scan covers a model unit and a few rooms. The route inside is the layout of that unit type.",
  "How fast a home heats up is a rule of thumb over age, walls, roof and shade, not a thermal model.",
  "The plan books nothing. A refuge or a staging lot is a place to call about, and a dispatcher approves every move.",
  "All patients are simulated. The diagrams on this page run the same formulas on made-up vans, calls and rooms.",
];

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mb-4 text-[11px] font-medium tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>{children}</p>;
}

/** One step of the plan: what it is on the left, the thing to play with on the right. */
function Step({ n, name, method, demo, children }: { n?: string; name: string; method: string; demo: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-6 grid gap-x-12 gap-y-8 rounded-2xl border p-7 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]" style={{ background: "var(--surface-1)", borderColor: "var(--border)" }}>
      <div>
        {n ? <p className="display text-5xl" style={{ color: "var(--accent)" }}>{n}</p> : <Eyebrow>The score</Eyebrow>}
        <h2 className={`${n ? "mt-3 " : ""}text-xl font-semibold`}>{name}</h2>
        <p className="mt-1 text-sm font-medium" style={{ color: "var(--text-muted)" }}>{method}</p>
        <div className="mt-4 space-y-3 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{children}</div>
      </div>
      <div className="min-w-0 max-w-[640px]">{demo}</div>
    </section>
  );
}

export default function AlgorithmPage() {
  return (
    <div className="min-h-full">
      <div className="mx-auto max-w-[1400px] px-8 pb-24">
        <header className="mb-2 flex flex-wrap items-center gap-x-7 gap-y-3 border-b py-5" style={{ borderColor: "var(--border)" }}>
          <span className="display text-2xl">Hearth</span>
          <nav className="flex flex-1 gap-6">
            <Link href="/results" className="text-sm" style={{ color: "var(--text-muted)" }}>Results</Link>
            <Link href="/algorithm" aria-current="page" className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Algorithm</Link>
            <Link href="/dispatch" className="text-sm" style={{ color: "var(--text-muted)" }}>Dispatch</Link>
          </nav>
          <Link href="/simulation" className="rounded-lg px-5 py-2.5 text-sm font-semibold" style={{ background: "var(--text-primary)", color: "var(--surface-0)" }}>
            Run the simulation
          </Link>
        </header>

        <div className="py-12">
          <Eyebrow>How the plan is made</Eyebrow>
          <h1 className="display max-w-[18ch] text-[64px] leading-[0.98] tracking-tight">Who goes where, and by which door.</h1>
          <p className="mt-7 max-w-[60ch] text-[17px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            One score, then three steps: which crew takes which person, what order each crew works in, and how
            to get from the curb to the machine. Every diagram below runs the planner&rsquo;s own formulas, so
            change the inputs and watch the plan move.
          </p>
        </div>

        <Step name="Weighted hours at risk" method="What steps 1 and 2 both minimize" demo={<ScoreCurve />}>
          <p className="rounded-lg border px-3 py-2 font-mono text-[13px] leading-relaxed" style={{ borderColor: "var(--border)", background: "var(--surface-0)", color: "var(--text-primary)" }}>
            weight × hours past the deadline + 0.1 × (weight ÷ hours left) × hours waited
          </p>
          <p>
            The line is nearly flat until a person&rsquo;s backup runs out, then climbs at their device&rsquo;s
            weight. Drag the deadline or the arrival and the cost follows.
          </p>
          <p>A person no route reaches is charged the full 6 hours, so leaving someone out is never free.</p>
        </Step>

        <Step n="1" name="Pair crews with people" method="Assignment problem, solved exactly (Hungarian method)" demo={<PairingDemo />}>
          <p>
            Sending each call its nearest van looks sensible and fails here: the most urgent call takes the
            only van close to someone else. Switch the rule to see it.
          </p>
          <p>
            The pairing looks at every van and every call at once and picks the set with the largest total
            value: the drop in the score from sending that van now, per crew-hour the job takes.
          </p>
        </Step>

        <Step n="2" name="Build each crew a route" method="Adaptive large neighborhood search (ALNS)" demo={<SearchDemo />}>
          <p>
            Take about 15% of the stops out of the plan, put them back where they cost least, keep the result
            if it helps. Repeat. Press play, or step through one move at a time.
          </p>
          <p>
            Stops come out three ways: at random, the ones paying the most where they sit, or a cluster of
            neighbors. The answer is never worse than where it started, and the same inputs always give the
            same routes. Only each van&rsquo;s first stop is committed; the plan is made again at the next step.
          </p>
        </Step>

        <Step n="3" name="Walk the last hundred feet" method="Shortest path (Dijkstra) over the 3D scan" demo={<ScanRouteDemo />}>
          <p>
            A Matterport scan is a set of spots where the camera stood, and each spot lists the spots it can
            see. A chain of them is a way a person can actually walk. Click any spot to put the machine there.
          </p>
          <p>
            With no pin, the machine is assumed to be in the farthest room scanned from more than one spot,
            which passes over the closet and the bathroom.
          </p>
        </Step>

        <section aria-labelledby="data" className="mt-16">
          <Eyebrow>The data</Eyebrow>
          <h2 id="data" className="text-xl font-semibold">One trip, and the building data that shapes each leg</h2>
          <p className="mt-2 mb-6 max-w-[68ch] text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            The three data layers of the CoStar track. Pick a leg of the trip to see what Hearth reads there and
            what it changes. The keys stay on the server; the browser only ever sees the result.
          </p>
          <TripData />
        </section>

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
