# Task C: results chart page, then the map with a time slider

Self-contained brief for one teammate's coding agent. Front end only. Do part 1 first; do part 2
only if usage allows, and open a pull request after each part.

**Branch:** `task/web-results` for part 1, `task/web-map` for part 2. Pull requests to `main`; do not push to `main`.
**Owns:** `web/` except `web/app/phone/`. Do not touch anything outside `web/`.

## What this is for

Hearth is a dispatcher tool that replays a hurricane power outage over simulated patients who
depend on home medical devices. Judges see two things from you: one chart that shows how many
patient-hours at risk each policy leaves at a given number of delivery crews, and a map where a
time slider scrubs through the outage.

Every page shows a fixed badge reading **Simulated patients**. Never write "lives saved" anywhere.

## Setup

Create the app in `web/` with Next.js (app router, TypeScript, Tailwind). Dependencies allowed:
`recharts` for the chart, `maplibre-gl` for the map, `vitest` for tests. Nothing else.
All data comes through one helper:

```ts
// web/lib/api.ts
export const API = process.env.NEXT_PUBLIC_API ?? "";       // empty means "read the static dev files"
export async function getJson<T>(path: string): Promise<T>  // fetches `${API}${path}`; when API is empty, fetches `/dev${path}.json`
```

Static dev files live in `web/public/dev/` and mirror the API paths, so pages work before the
backend exists and switch to the real API by setting `NEXT_PUBLIC_API=http://localhost:8000`.

## Part 1: results page (`/results`)

**Files:** `web/app/results/page.tsx`, `web/components/CrewsChart.tsx`, `web/lib/api.ts`, `web/lib/types.ts`,
`web/public/dev/api/results.json`, `web/lib/results.test.ts`.

Data: `GET /api/results` returns

```ts
type SweepRow = { policy: string; crews: number; median: number; p5: number; p95: number; unweighted_median: number };
```

Policies and their labels: `p0` "Phone tree (today)", `p3` "Hearth", `p3__nobld` "Hearth without building data",
`p3__nomove` "Hearth without moves", `p3__aid` "Hearth with supplier mutual aid".
Write a `results.json` dev file by hand with crews `5, 10, 20, 40, 80` for all five policies.

Build:
- A line chart: x is crew count, y is median patient-hours at risk, one line per policy, with a shaded band from `p5` to `p95`. The first three policies are shown by default; the last two are toggles.
- A toggle between risk-weighted and unweighted (`unweighted_median`; no band in that mode).
- Under the chart, a short list titled "Assumptions that flatter Hearth": simulated patients reply at configured rates; crews accept jobs instantly; the indoor temperature model is a simple heuristic; Hearth assumes per-home outage data from the utility.
- A line of text: "A policy result on simulated patients. Every number traces to a command in the README."

```ts
export function toSeries(rows: SweepRow[], weighted: boolean): { policy: string; label: string; points: { crews: number; y: number; lo?: number; hi?: number }[] }[]
```

Test first (`npm test`): `toSeries` groups rows by policy, sorts points by crews, uses `median`
with `lo`/`hi` when weighted and `unweighted_median` without them otherwise, and maps each policy to its label.

**Done when:** `npm test` passes and `/results` renders five policies from the dev file with the toggles working.

## Part 2: map and time slider (`/`)

**Files:** `web/app/page.tsx`, `web/components/{Map,TimeSlider,PatientPanel}.tsx`,
`web/public/dev/api/runs.json` and the dev copies listed below, `web/lib/snapshots.test.ts`.

Data (copy the repo's `results/sample__p3__c20__s1/` files into `web/public/dev/api/runs/sample__p3__c20__s1/` as `meta.json`, `snapshots/0.json`, `snapshots/1.json`, `events.json`):

```ts
type PlanState = "NOT_AFFECTED" | "OWN_BACKUP" | "RESUPPLY" | "MOVE" | "MOVED" | "URGENT" | "UNREACHABLE" | "RESTORED";
type PatientSnap = { id: string; lat: number; lon: number; device: string; state: PlanState; backup_hours: number; indoor_temp_c: number; unpowered: boolean; building_id: string | null };
type Snapshot = { t: string; patients: PatientSnap[]; crews: object[]; depots: object[] };
type Run = { run_id: string; scenario: string; policy: string; crews: number; seed: number };
type Meta = { ticks: string[]; center: [number, number] };            // center is [lat, lon]
type HearthEvent = { t: string; type: string; patient_id: string | null; data: object };
// GET /api/runs -> Run[]        GET /api/runs/{run_id}/meta -> Meta
// GET /api/runs/{run_id}/snapshots/{i} -> Snapshot        GET /api/runs/{run_id}/events?patient_id= -> HearthEvent[]
```

Build:
- A MapLibre map centered on `meta.center`, using a free style that needs no key (`https://tiles.openfreemap.org/styles/positron`).
- Patients as one circle layer, colored by plan state. `stateColor(state)` returns a distinct color for each of the eight states; `URGENT` is the most prominent.
- A slider over `meta.ticks` showing the time in US Central. Moving it swaps the snapshot; preload the next ten snapshots so scrubbing does not stall.
- A legend with a count per state for the current tick.
- Clicking a patient opens a panel: device, state, backup hours left as a gauge, indoor temperature, and that patient's events in time order.

```ts
export function stateColor(state: PlanState): string
export function countByState(snap: Snapshot): Record<PlanState, number>
```

Test first: `stateColor` gives eight distinct colors; `countByState` on the sample snapshot sums to the number of patients.

**Done when:** `npm test` passes, the sample run scrubs smoothly, and the patient panel shows events.

## Not yours

The building panel, the agent trace, the proposal card and the phone page are written by the
manager lane on top of this. Leave a right-hand panel slot in the layout for them.
