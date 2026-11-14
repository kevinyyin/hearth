# Hearth: weekend design

HackPrinceton Fall 2026. Build window: Fri Nov 13 8:00 PM to Sun Nov 15 8:00 AM ET. Demo: 2 minutes, in person.
Source spec: `hearth-spec.md` v5. Where this document and the spec disagree, this document wins.

## What it is

Hearth keeps people on power-dependent home medical devices safe through multi-day outages.
For each person it tracks two clocks: hours of device backup left, and hours until their home is
unsafely hot or cold. The building sets the second clock. A building agent reads CoStar records,
Vexcel aerial imagery and Matterport scans to work out how fast each building becomes dangerous,
how long a delivery takes with the elevator out, and where a person could be moved. A dispatcher
approves every move; a voice agent then calls the person for consent and follows up by text.

User: a county health department's emergency planner and dispatcher. Patients are synthetic.

## Where the effort goes

| Tier | Track | What we show |
|---|---|---|
| Win | CoStar: Inside and Out | The building agent, live, on a judge-picked Houston building |
| Win | LangChain: deepagents | The same agent: plan, subagents, files, approval interrupt, memory |
| Lean but real | Photon: voice agent | One real call out and in on a Photon number, then an iMessage that remembers it |
| Rides along | Amazon: Practical AI | The whole flow, the agent learning from rejections, a clean interface, a README |
| Rides along | Healthcare (main track) | The problem, the replay, the results chart |
| Only if earned | Peri: Forward Deployed | One filtered view built for a business interviewed Saturday morning |

## The building agent (deep)

Built with `deepagents` on Claude. Model names live in config.

- **Surveyor.** Input: one building. It writes a to-do plan, then delegates to one subagent per layer:
  - `costar`: floors, units, year built, construction, property type, elevators if present.
  - `aerial`: Vexcel attributes (roof material, condition, tree cover) plus a vision read of the
    image tile for roof tone, shade and where a van can stop.
  - `interior`: finds entrance and stair panoramas in the Matterport scan and reads steps,
    elevator presence and door widths with a vision model.
  It reconciles conflicts between layers, takes a second look when they disagree, and writes one
  outage profile. Every field carries `value`, `source` and `confidence`. A missing layer is
  recorded as missing with the stated default; nothing is filled silently.
- **Derived numbers are code, not model.** Heat and cold time constants and service minutes come
  from a published formula over the profile fields. It is a heuristic and is labeled as one.
- **Refuge finder.** Searches CoStar for hotels and senior housing outside the dark area, checks
  step-free access in the scan and drop-off in the aerial image, ranks options for the patient's
  device and mobility, and drafts a proposal with reasons and sources. It books nothing.
- **Approval is the library's human-approval interrupt.** The dispatcher approves or rejects. A
  rejection reason is saved to the agent's memory file and applied to later proposals.
- **Files are the cache.** Subagents write raw findings under `data/buildings/<id>/`; the demo
  reads from there when the network is slow. Cached results are labeled as cached.
- **Season sweep.** Run the surveyor across every building with a registered patient and rank
  which become dangerous first. This is the "switch it on Monday" use.
- **What each layer changed.** The building panel shows the unsafe time with and without each
  layer, per building. The results chart shows it county-wide.
- **Crew access brief.** For every delivery, ride or welfare check, the agent turns the profile
  into a one-screen brief for the crew: where to stop the vehicle (aerial), which entrance is
  step-free, the route from entrance to elevator or stairs, stair and door widths, and the scan
  frames that show each point (Matterport). CoStar's record has no floor plan; the layout comes
  from the scan, so the brief exists only where a scan does, and says so otherwise. Scans of
  apartment buildings usually cover common areas and model units, not a specific resident's unit;
  the brief never claims to show the patient's own rooms.
- **Check.** Ten hand-labeled buildings; report accuracy per field and silent fills (target zero).

Live survey target: about 30 seconds, subagents in parallel.

Proven in a throwaway test on Nov 13 (`deepagents` 0.7.38, Claude Haiku, fake data tools): the
agent wrote a to-do plan, ran three layer subagents in parallel, saved each layer to a file,
and stopped at the approval interrupt before writing the profile, then finished on approval.
22.7 seconds end to end. Real data tools and vision reads will add time.

**Amended Nov 13 after the toolkit arrived** (details in `docs/toolkit-notes.md`; this paragraph
wins over the bullets above where they differ). CoStar is a data extract, and it already states
walk-up and elevator status for most Houston apartment buildings, so those come from CoStar, not
from a vision read. Matterport scans are mostly unit interiors with labeled rooms. The `interior`
subagent therefore reads the unit: room layout, room sizes, door and hallway widths, interior
steps. The crew access brief becomes two parts: getting to the door (stories, walk-up or elevator
from CoStar; where to stop and the entrance side from the aerial image) and inside the unit (the
floor plan's rooms and the path from the front door to the bedroom, from the scan). The refuge
finder checks a hotel or senior unit's interior the same way. The brief says "floor plan of this
unit type", never "the patient's own rooms".

## Voice and text (lean)

- One ElevenLabs voice agent whose model endpoint is our server. Each caller turn goes to Claude
  Haiku, which returns structured fields; code picks the next line from templates.
- Flows: move-consent call (the demo), impact call, inbound call to the same agent.
- Kept from the spec: opens by saying it is automated; numbers read back; keypad answers; no
  promise sentences from the model; a guard on model-written acknowledgments; medical questions
  get a fixed hand-off line.
- After a call, a Photon iMessage carries the confirmed facts and, once a crew has accepted, the
  templated confirmation.
- The real call runs on a Photon SMS number over SIP. The same agent in the browser is the fallback.

## Simulation (enough to drive the replay and one chart)

- About 23,000 synthetic Harris County patients from emPOWER July 2024 ZIP totals, split by a
  configured device mix (device type by ZIP is not public). Homes placed inside ZIP boundaries.
- Hurricane Beryl outage curve from EAGLE-I, cleaned (late onset, false dip, near-zero readings),
  with corrected intervals labeled. Hourly IAH weather. Straight-line travel times with a factor.
- Backup clock, indoor temperature clock, the spec's decision logic with hysteresis, greedy planner.
- Policies: manual phone tree, Hearth, Hearth without buildings. Sweep: crew count, 10 seeds.
- Output contract as in the spec: `events.jsonl`, `snapshots/<tick>.json`, `summary.json`.
- Every default number in `config/assumptions.yaml`; results saved beside the copy used.

## Dispatcher map

Next.js and MapLibre. Time slider over the outage; patients colored by plan state; building panel
with the aerial tile, embedded scan, agent plan and trace, and the profile with sources; refuge
proposal card with approve and reject; results page with the crews chart and assumptions. The web
app reads state and never computes plan logic.

## Architecture

Python 3.11+, FastAPI, SQLite as the one shared state store. Components react to state and do not
call each other. Secrets in `.env`, never in the repo.

## Team and delegation

One Claude session is the manager. It owns the building agent, the shared contracts and
integration. Other lanes are GitHub issues that teammates pick up; any lane nobody takes falls
back to the manager. Each lane owns its own directories, so two people never edit the same files.

| Lane | Owner | Directories | Depends on |
|---|---|---|---|
| Contracts and skeleton (hour 0-1) | Manager | `config/`, state schema, profile schema, events and snapshots format | Nothing |
| Building agent | Manager | `hearth/buildings/`, `data/buildings/` | CoStar toolkit keys |
| Integration and live demo mode | Manager | `api/` | All lanes |
| Simulation | Delegable | `hearth/` except `buildings/` and `messaging/`, `scripts/` | Contracts |
| Dispatcher map | Delegable | `web/` | Contracts (works from sample files first) |
| Voice and text | Delegable | `hearth/messaging/`, voice routes | Photon project, ElevenLabs key |
| No-code tasks | Teammates | Photon account and number, Saturday-morning interview, hand-labeling ten buildings, pitch, Devpost | Nothing |

The contracts land first so the lanes cannot drift: every lane reads and writes the same state
store and file formats, and the map can be built against sample files before the simulation runs.

## Rules that stay from the spec

Synthetic patients only, labeled everywhere. No promises from the model. No medical advice.
Humans approve moves. Silence is never treated as safe. Deterministic runs by seed. Assumptions
published with results. Never claim lives saved. Pitch facts use the corrected wording from the
source check.

## Build order

| Hours | Work |
|---|---|
| 0-1 | Repo and skeleton. Spikes: one building through all three layers; one browser call; Photon number. |
| 1-14 | Three lanes: building agent (priority), simulation core, map. |
| 14-20 | Refuge finder, approval interrupt, memory; consent call; results chart. |
| 20-26 | Integration: replay, move flip, proposal, approve, call, text. |
| 26-30 | Season sweep, building check, documented-case replays, Peri view, extra policy switches. |
| 30-34 | Interface polish, README, Devpost paragraph per track. |
| 34-36 | Freeze, rehearsals, submit before 8:00 AM. |

If behind at hour 20, drop from the 26-30 row first.

## Cut

Freeze, Milton and Kyiv scenarios. Call-when-low, emptiest-first and no-meter-data policies.
Local search. Spanish. Profile setup call. Pre-landfall screen. Self-signup page. Retention purge
job. Road-graph routing. Dispatcher takeover of text threads. Large eval sets and the 30-call exam.

If on track only: no-moves and mutual-aid switches; documented-case replays beyond one.

## Approaches considered

1. **Depth on the building agent, lean everything else (chosen).** One artifact serves the two
   tracks with the best fit and the largest prize.
2. **Even effort across five tracks.** Rejected: no track gets a standout demo.
3. **Depth on voice.** Rejected as the lead: it depends on a Photon SIP path that is untested,
   and it serves one track.

## Open and untested

- CoStar toolkit fields, coverage and rate limits: unknown until the keys arrive. This is the
  one thing the top track depends on that could not be tested. First act on receiving the keys:
  pull one building through all three layers and count how many Houston multifamily, senior and
  hotel buildings have a scan.
- Whether the toolkit's Matterport access includes floor plans, room labels and door openings,
  or only panoramas. The crew access brief uses whichever exists; panoramas alone are enough.
- Model access is confirmed: the Anthropic key works with its workspace ID and can reach
  `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`.
- ElevenLabs custom-model endpoint with keypad input: to test in hour 0.
- Photon SMS number placing calls without carrier registration: to test in hour 0.
- A live survey finishing in about 30 seconds: to measure on the first real building.

## Left to the builder

File layout within the spec's structure, the profile formula's coefficients (in config), prompt
wording, and interface styling.
