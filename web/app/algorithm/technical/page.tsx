import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import LiveSurvey from "@/components/algorithm/LiveSurvey";

export const metadata: Metadata = { title: "Algorithm, technical · Hearth" };

// shortcut: counts and constants below are copied from the code and config/assumptions.yaml; serve them from the API if they start changing
const FIGURES: [string, string][] = [["1,758", "Houston CoStar records"], ["1,732", "with a Matterport scan"], ["4", "Vexcel endpoints"], ["3", "subagents in parallel"]];

const PIPELINE: [string, string][] = [
  ["CoStar extract", "commercial-property.jsonl"],
  ["normalize_costar", "research market 14 → flat fields"],
  ["Surveyor deep agent", "costar · aerial · interior"],
  ["BuildingProfile", "{value, source, confidence}"],
  ["Planner", "deadline · access · refuge · lot"],
];

const FIELDS: [string, string, string][] = [
  ["primaryAddress.latitude, longitude", "lat, lon", "Every travel time: straight-line km × 1.4 at 40 km/h"],
  ["numStoriesAboveGrade", "floors", "10 min inside, +4 min per floor climbed without a working elevator"],
  ["propertyApartment.elevators[], structural.elevators[], isWalkup", "elevator_count", "Whether those floors are climbed at all"],
  ["constructionEvents[eventType=2].year, buildingConstructionMaterial", "year_built, construction", "Heat time constant → hours until the home is unsafe"],
  ["propertyType, propertySubtype, apartmentLifestyleType", "property_type", "Hotels and senior housing become refuge candidates"],
  ["constructionStatus, propertyHospitality.operatingStatus", "existing", "A closed hotel is never offered as a refuge"],
  ["parking[parkingType=1].totalSpaces, lotSize", "surface_spaces, lot_acres", "A crew staging lot needs 100+ surface spaces"],
  ["primaryAddress.postcode", "zip", "A staging lot sits in a ZIP with no open help request"],
  ["propertyApartment.models[].units, attachments[].videoKey", "floor_plans, matterport_model_ids", "Which Matterport scan to open for a resident's unit"],
];

const CALLS: [string, string, string][] = [
  ["Vexcel", "GET /v2/property/extract", "Roof material and tree cover from the latest capture → heat deadline"],
  ["Vexcel", "POST /v2/elements/detect", "Driveways, parking, loading zones, ramps, entrances → where the van stops"],
  ["Vexcel", "POST /v2/ortho/extract", "40 m tile read by Claude vision → roof tone, entrance, lot access"],
  ["Vexcel", "POST /v2/embedding/extract", "Semantic search over aerial tiles → shelter leads near a patient"],
  ["Matterport", "GraphQL model.rooms, model.locations", "Room sizes and panoramas → crew brief, vision on the entry and lobby"],
  ["Matterport", "Showcase SDK sweeps", "Each sweep's visible neighbors → Dijkstra from the door to the device"],
];

const RULES = [
  "write_todos plans the run; the task tool fans out to three Haiku subagents in one turn; each saves its findings to /<building_id>/<layer>.md.",
  "Every field written needs a source layer and a confidence; a field no layer showed stays unknown. write_profile validates and rejects the rest.",
  "CoStar is the authority on elevators and walk-ups. An elevator only seen in a scan is written at confidence ≤ 0.5 and flagged as a conflict.",
  "Derived numbers (heat and cold time constants) are computed by code from the fields, never by the model.",
];

const PLANNER: [string, string][] = [
  ["Score", "weight × hours past the deadline + 0.1 × (weight ÷ hours left) × hours waited; an unreached person costs 6 h"],
  ["Pairing", "Hungarian assignment, crews × people, value = drop in the score per crew-hour"],
  ["Routes", "Adaptive large neighborhood search: remove ~15% of stops (random, worst, cluster), reinsert cheapest, keep if better"],
  ["Indoors", "Dijkstra over the Matterport sweep graph, curb → door → device"],
];

const LIMITS = [
  "Travel is straight-line, with no road, closure or flood layer.",
  "No record says an elevator runs today; a resident or the building office has to say so.",
  "A scan shows a unit type, never a resident's own rooms. All patients are simulated.",
];

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="mt-14">
      <p className="mb-2 text-[11px] font-medium tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>{eyebrow}</p>
      <h2 className="mb-4 text-xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const cell = "border-t py-2 pr-4 align-top";
const border = { borderColor: "var(--border)" };

export default function TechnicalPage() {
  return (
    <div className="min-h-full">
      <div className="mx-auto max-w-[1400px] px-8 pb-24">
        <header className="mb-2 flex flex-wrap items-center gap-x-7 gap-y-3 border-b py-5" style={border}>
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

        <div className="flex flex-wrap items-end justify-between gap-6 py-10">
          <div>
            <p className="mb-4 text-[11px] font-medium tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Technical overview</p>
            <h1 className="display text-[56px] leading-[0.98] tracking-tight">CoStar in, a dispatch plan out.</h1>
            <p className="mt-5 max-w-[68ch] text-[16px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Every plan starts from a CoStar property record. Vexcel and Matterport fill what the record can&rsquo;t, a
              LangChain deepagents surveyor reconciles the three into one sourced profile, and three solvers turn it into
              crews, routes and a walk to the machine.
            </p>
          </div>
          <Link href="/algorithm" className="text-sm underline underline-offset-2" style={{ color: "var(--text-secondary)" }}>Interactive version →</Link>
        </div>

        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 border-y py-5 md:grid-cols-4" style={border}>
          {FIGURES.map(([n, label]) => (
            <div key={label}>
              <dt className="sr-only">{label}</dt>
              <dd className="display tnum text-4xl">{n}</dd>
              <dd className="mt-1 text-[13px]" style={{ color: "var(--text-muted)" }}>{label}</dd>
            </div>
          ))}
        </dl>

        <Section eyebrow="Live" title="One building, surveyed by the agent">
          <p className="-mt-2 mb-4 max-w-[75ch] text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Real CoStar properties from the API. The trace is the last real survey of the building, replayed at twice its
            speed; run it live to start a fresh one.
          </p>
          <LiveSurvey />
        </Section>

        <Section eyebrow="Pipeline" title="From record to plan">
          <ol className="grid gap-2 md:grid-cols-5">
            {PIPELINE.map(([name, sub], i) => (
              <li key={name} className="relative rounded-xl border px-4 py-3" style={{ ...border, background: "var(--surface-1)" }}>
                <p className="text-sm font-semibold">{name}</p>
                <p className="mt-0.5 font-mono text-[11.5px]" style={{ color: "var(--text-muted)" }}>{sub}</p>
                {i < PIPELINE.length - 1 && <span aria-hidden className="absolute top-1/2 -right-2 hidden -translate-y-1/2 text-sm md:block" style={{ color: "var(--text-muted)" }}>→</span>}
              </li>
            ))}
          </ol>
        </Section>

        <Section eyebrow="CoStar" title="Which record fields Hearth reads, and what each one changes">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead>
                <tr className="text-left text-xs" style={{ color: "var(--text-muted)" }}>
                  <th className="pb-2 font-medium">CoStar field</th><th className="pb-2 font-medium">Hearth field</th><th className="pb-2 font-medium">What it drives</th>
                </tr>
              </thead>
              <tbody>
                {FIELDS.map(([raw, ours, drives]) => (
                  <tr key={ours}>
                    <td className={`${cell} font-mono text-[12px]`} style={border}>{raw}</td>
                    <td className={`${cell} font-mono text-[12px]`} style={border}>{ours}</td>
                    <td className={cell} style={{ ...border, color: "var(--text-secondary)" }}>{drives}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <div className="grid gap-x-12 lg:grid-cols-2">
          <Section eyebrow="Agents" title="The surveyor and the refuge finder">
            <ul className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {RULES.map((r) => <li key={r} className="border-t py-2" style={border}>{r}</li>)}
              <li className="border-t py-2" style={border}>
                Refuge finder: CoStar hotels and senior housing outside the dark area, access checked by code, ranked by a
                deep agent, stopped at a human approval interrupt. Rejections go to the agent&rsquo;s memory file.
              </li>
            </ul>
          </Section>
          <Section eyebrow="Adjacent data" title="Vexcel and Matterport calls">
            <table className="w-full text-[13px]">
              <tbody>
                {CALLS.map(([src, call, what]) => (
                  <tr key={call}>
                    <td className={`${cell} font-mono text-[12px] whitespace-nowrap`} style={border}>
                      <span style={{ color: src === "Vexcel" ? "var(--series-3)" : "var(--series-2)" }}>●</span> {call}
                    </td>
                    <td className={cell} style={{ ...border, color: "var(--text-secondary)" }}>{what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>

        <div className="grid gap-x-12 lg:grid-cols-2">
          <Section eyebrow="Planner" title="What the profile feeds">
            <dl className="text-sm leading-relaxed">
              {PLANNER.map(([k, v]) => (
                <div key={k} className="grid grid-cols-[5.5rem_1fr] gap-3 border-t py-2" style={border}>
                  <dt className="font-semibold">{k}</dt><dd style={{ color: "var(--text-secondary)" }}>{v}</dd>
                </div>
              ))}
            </dl>
          </Section>
          <Section eyebrow="Limits" title="What it does not know">
            <ul className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {LIMITS.map((l) => <li key={l} className="border-t py-2" style={border}>{l}</li>)}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
