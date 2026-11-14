# Where the web app gets its data

The results page and the simulation both run from one switch: `NEXT_PUBLIC_API`.
Set it and they read the real replay; leave it unset and they fall back to data
drawn into the page. Nothing in between needs changing, so the same build runs on
a laptop with no kit, on the machine that has the CoStar extract, and on Vercel.

## The rule about keys

The CoStar extract, the Vexcel key and the Matterport token are **the API's**, not
the web app's. They are read server-side in `hearth/buildings/tools.py` and never
cross into the browser bundle. The web app knows one address and nothing else:

```
browser ── NEXT_PUBLIC_API ──▶ hearth-api ──▶ CoStar extract, Vexcel, Matterport
```

Never put a sponsor key in a `NEXT_PUBLIC_*` variable. Anything with that prefix
is compiled into the JavaScript every visitor downloads.

## The three environments

| Where | `NEXT_PUBLIC_API` | What the maps show |
| --- | --- | --- |
| A laptop with no kit | unset | Drawn households, labelled "Fixture" in the panel |
| A laptop pointed at the hosted API | `https://hearth-api-six.vercel.app` | The real replay, scan and tile |
| The machine with the kit | `http://localhost:8000` | The replay's own patients |
| Vercel | already set to the hosted API | The real replay |

The hosted API is **`https://hearth-api-six.vercel.app`** — not the project name.
`web/.env.example` has it ready to copy to `web/.env.local`. Next inlines
`NEXT_PUBLIC_` variables at build time, so restart the dev server after changing
it; a reload will not do.

### On the machine that has the CoStar kit

```bash
uv run uvicorn api.main:app --port 8000
```

Then, in `web/.env.local`:

```
NEXT_PUBLIC_API=http://localhost:8000
```

`HEARTH_FIXTURES=1` makes the building tools read `data/buildings/_fixtures/`
instead of the sponsor APIs — useful for checking the wiring without burning
Vexcel calls.

### On Vercel

The two projects are already split: `hearth` serves the web app and `hearth-api`
serves the API. In the `hearth` project's settings, set

```
NEXT_PUBLIC_API = https://hearth-api-six.vercel.app
```

for Production and Preview. Sponsor keys go in the **`hearth-api`** project's
environment, never in `hearth`.

A preview deployment picks the variable up at build time, so changing it needs a
redeploy, not just a reload.

## What becomes real, and what does not

Reading `web/lib/simSource.ts`:

- **Households on the side-by-side** come from `/api/runs` → `/api/runs/{id}/snapshots/0`.
  Each dot is a patient from the replay at their own coordinates, and the hour
  they need help is their own `backup_hours`. The population is thinned with an
  even stride to about 400 dots so a county replay stays drawable.
- **The map centre** comes from the run's `meta.center`.
- **The resident in the simulation** comes from `/api/demo-patients`, their pins
  from `/api/patients/{id}/home`, and their building's floors and walk-up flag
  from `/api/buildings/{id}` — which is the CoStar record itself.

Still placeholder regardless of the API, because nothing serves them yet:

- **The call transcripts.** The voice lane owns the real wording, and the rule
  that no sentence promising help is model-written.
- **The room layout behind the Recommended path.** CoStar and Matterport give
  scan ids and access facts, not a floor polygon, so `web/lib/floorplan.ts` is a
  schematic. The route across it is really planned; the shape it is planned over
  is invented.
- **The crews, stations, cruising speed and the queue rate** in the side-by-side.
  The simulation in this repository reports patient-hours at risk and has never
  modelled a fleet. That panel says so on its face.

## When it does not connect

Both panels degrade rather than break: the fixture renders, and the badge says
"Fixture" with the reason beside it. If the API answered but something was wrong
with the data, the badge shows the error. So "did the integration work?" is a
question you answer by looking at the page, not by reading a console.

## Adopting this in the other lanes

The pieces are shared, so a panel joins in without a rewrite.

- `useBuildingFeed(id)`, `useRunsFeed()`, `useReplayMeta(runId)` and
  `useSnapshotFeed(runId, i)` in `web/lib/simSource.ts` each return
  `{ data, source, detail, error }`. They go through `getJson`, so they read the
  API when one is configured and `web/public/dev/api/**` when one is not.
- `<SourceBadge source={source} detail={detail} error={error} />` renders the
  green "Live from the Hearth API" or grey "Fixture" chip. One line, no wiring.

There are now dev fixtures for `/api/buildings` and `/api/buildings/B-SAMPLE`, so
anything built on `getJson("/api/buildings/…")` draws on a laptop with no kit
instead of showing an error.

### The one place this does not reach

`web/app/dispatch/page.tsx` returns early:

```tsx
if (!API) return <p>This page needs the Hearth API.</p>;
```

That check runs before any fetch, so no fixture can satisfy it. Swapping it for
the hooks above is a few lines, but that file belongs to the voice-registration
lane and is deliberately untouched here.

`web/components/BuildingPanel.tsx` is the happier case: it already calls
`getJson`, so the fixtures above are enough for it to render without the kit — no
edit needed there, and none made.

## Not spending the deployment budget on nothing

Vercel's Hobby plan allows 100 deployments per rolling 24 hours, **per account, not
per project**. Both projects here build from this one repository, so every push
used to cost two — including the many that touched only `web/` and left the Python
API untouched. A day of ordinary PR work exhausted it, and then the production
build that actually mattered was refused while an unchanged API project took the
last free slot.

`vercel.json` and `web/vercel.json` now carry:

```json
{ "git": { "deploymentEnabled": { "claude/*": false, "codex/*": false } } }
```

Branches on those prefixes no longer create deployments at all, so a PR costs
nothing until it merges. Merges to `main` still deploy normally, which is the only
build that has to happen.

Two things worth knowing before relying on it:

- **An Ignored Build Step does not help here.** A build it cancels still counts
  against the deployment quota and the concurrent build slot — it saves build
  minutes, not deployments. `git.deploymentEnabled` is the one that stops the
  deployment being created.
- **The file has to be on the branch being pushed.** Vercel reads it from the
  commit it is about to build, so this takes effect for branches cut after it
  lands, not for ones already open.

The cost of it is that pull requests get no preview URL on those branches. Check
the change locally, or on `main` once it is merged.
