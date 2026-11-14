# Hearth: keeping people on home medical devices safe through long outages

Spec v6, as built · HackPrinceton Fall 2026 · written early Saturday, November 14, 2026

This replaces v5. v5 said what we planned; this says what exists on `main`, what the numbers are, and what is
left. The first part is for the team and the pitch. The second part is the build reference. Where this document
and the code disagree, the code is right and this document has a bug.

**Status in one paragraph.** The building agent, the simulation, the dispatcher map, the results page, the call
logic and the browser phone are all on `main`, with 203 Python tests passing (and 26 web tests, per the build
session's last run). Not done: the real
phone number and follow-up text (blocked on the Photon project), the hand-labeled building check, the Saturday
interview, and the README and Devpost write-up. The demo has not been rehearsed end to end.

---

# Part 1: for the team

## The pitch in one line

When the grid goes down for days, Hearth gives each person on a power-dependent medical device a plan built
around their device and their building, and gives the health department a way to run thousands of those plans at
once: ride it out on their own backup, get supplies at home, or move somewhere with power.

## The problem (wording checked against sources)

- Over 3 million Medicare beneficiaries have a claim for electricity-dependent medical equipment (HHS emPOWER).
  1.6 million Medicare beneficiaries used oxygen therapy in 2023.
- Devices run on backup for hours; major outages last days. More than 2 million CenterPoint customers lost power
  after Hurricane Beryl in July 2024.
- Health departments work these lists by hand. In Broome County, New York, in 2017, staff phoned all 58 people on
  the list, could not reach 24, and asked the Sheriff's Office to send patrols.
- About 29% of cell sites in the FCC's six-county Beryl disaster area were down on July 9, 2024.

The people behind the numbers, each as publicly reported. Use this wording and nothing beyond it.

| Person | What was reported | Source |
|---|---|---|
| Andy Anderson, Crosby, Texas (2021 freeze) | A Vietnam veteran with COPD. He could not get a generator going and went to his truck, where he had an oxygen device; he died of hypothermia. His wife: "We didn't know the power would be out for days like it was." | abc30.com/post/winter-storm-texas-power-outage-vietnam-veteran-dies-copd/10355546/ |
| James Thomas Jones, 83, Houston (2021 freeze) | According to a wrongful-death lawsuit filed by his daughter against CenterPoint, his backup respirator's battery ran out during a 24-hour outage; the family tried charging it with jumper cables. | abc13.com/post/houston-wrongful-death-family-suing-centerpoint-over-elderly-mans-man-on-respirator-dies-during-winter-storm-woman-sues-for-fathers/10423358/ |
| Judith Greet, 71, Crystal Beach, Texas (Beryl) | Died after her oxygen machine's battery ran out and her generator shut down. | poweredforpatients.org (name, age, town); CNN wire copy at kvia.com/?p=1258459 (details) |
| Mark Edward Rutland, 64, Webster, Texas (Beryl) | Died of hyperthermia when his oxygen concentrator shut off during a power loss. | khou.com Beryl deaths list (single source; open the page before quoting) |
| Pamela Jarrett, 64, Spring, Texas (Beryl) | Used a wheelchair and a feeding tube. Her sister said she was on a CenterPoint emergency list, and that it was difficult to get enough signal to call 911. She died of heat on the fourth day without power. | abc13.com/post/hurricane-beryl-aftermath-family-mourns-death-64-year/15065823/ ; texastribune.org/2024/07/22/texas-hurricane-beryl-heat-deaths/ |

Rules: no dramatization, no invented detail, no contact with families. We never claim Hearth would have saved
anyone, and never claim lives saved.

## What Hearth does, as built

1. **Replays a real outage over simulated patients.** Hurricane Beryl in Harris County, 23,273 synthetic patients,
   half-hour steps over 11 days. Each patient has two clocks: hours of device backup left, and how fast their home
   is heading toward unsafe heat.
2. **Surveys the building.** A deep agent reads the CoStar record, the Vexcel aerial image and attributes, and the
   Matterport scans, reconciles disagreements, and writes an outage profile in which every field names its source.
3. **Briefs the crew.** A one-screen access brief in two parts: getting to the door (stories, walk-up or elevator,
   where a van can stop) and inside the unit (the floor plan's rooms and widths from the scan).
4. **Proposes a refuge.** A second agent finds hotels and senior housing outside the dark area, checks access for
   this patient's mobility, and stops for a dispatcher's approval. A rejection reason is remembered.
5. **Calls for consent.** After approval, a voice agent calls the patient. Code picks every line that matters;
   numbers are read back before they count.

## What changed from v5

| v5 planned | What we built, and why |
|---|---|
| Two scenarios plus fallbacks | Beryl only. The 2021 freeze data shows a third of the reported peak. |
| Eight policies | Five: phone tree, Hearth, and Hearth with buildings off, moves off, or supplier mutual aid on. |
| Device type by ZIP from emPOWER | Not public. One county-wide mix from 2024 Texas Medicare counts: 81% oxygen, 9% ventilator, 8% home dialysis, 2% feeding pump. |
| Elevators and entrances read from scans | Elevator and walk-up status come from CoStar, which states them. Scans are mostly unit interiors, so they give room layout and widths. |
| Agent surveys every patient's building | A 55 to 61 second agent survey cannot cover 1,300 buildings. 1,386 buildings have a profile built from their records with no model call, marked "records only". The agent survey is for the live demo and for refuges. |
| Road-graph travel times | Straight-line distance times a detour factor. |
| Twilio for calls, SMS for texts | ElevenLabs voice agent whose model endpoint is our server. US SMS needs a carrier registration that takes days, so texts go by Photon iMessage. |
| Crews from 5 to 80 | 20 to 320. Eighty crews deliver about a tenth of peak demand, so the old range showed only the start of the curve. |
| Spanish, profile setup call, pre-landfall screen, self-signup, local search, retention purge job | Cut. |

## Results so far

Median risk-weighted patient-hours at risk, in millions, over 10 seeds. Lower is better. Simulated patients.

| Policy | 20 crews | 40 | 80 | 160 | 320 |
|---|---|---|---|---|---|
| Phone tree (today) | 4.32 | 4.22 | 4.08 | 4.12 | 4.12 |
| Hearth | 3.88 | 3.48 | 2.82 | 1.67 | 0.54 |
| Hearth without building data | 3.93 | 3.56 | 2.98 | 2.04 | 0.95 |
| Hearth without moves | 4.10 | 3.95 | 3.94 | 3.96 | 3.96 |
| Hearth with supplier mutual aid | 3.86 | 3.45 | 2.75 | 1.60 | 0.54 |

How to read it, honestly:

- **Hearth against the phone tree is the solid result:** 10% better at 20 crews, 31% at 80, 87% at 320. The ranges
  across seeds do not overlap.
- **Almost all of it comes from moving people.** With moves off, Hearth barely beats the phone tree.
- **The building number is an upper bound, and it is not about heat.** Building data adds 1% at 20 crews, 6% at 80
  and 43% at 320. All of that comes from hotels and senior housing as places to move people, and those have no
  capacity limit in the model. How fast each building heats up changes the total by under 0.2%: in a Houston July
  every dark home is unsafe within hours.
- **Mutual aid adds almost nothing** at these stock levels.
- **The phone tree gets slightly worse past 80 crews** because stock never restocks in the model and
  first-come-first-served spends it sooner. That is an assumption, not a finding.

What we claim: a policy result on simulated patients, every assumption published, every number traceable to a
command. Placeholders that drive these numbers and still need a real source: crews, stock per supplier and restock,
phone-tree staffing, refuge capacity.

## Tracks

| Priority | Track | What its judges see |
|---|---|---|
| Win | CoStar: Inside and Out | The agent on a Houston building: all three layers, the conflicts it found, what each layer changed, the crew brief, a refuge proposal. Lead with the agent, not with patient-hours. |
| Win | LangChain: deepagents | The same agent's plan, three parallel subagents, files as cache, the approval interrupt, and the rejection it remembered. |
| Lean | Photon: voice agent | One real call out and in, then a text that remembers the call. Blocked until the Photon project exists; the browser phone is the fallback. |
| Rides along | Amazon; Healthcare (main track) | The whole flow, the results chart, a clean interface, the README. |
| If earned | Peri | One view built for a business interviewed Saturday morning. |

Not entering the ChatOverflow leaderboard from the build machine: it installs a hook into every agent session and
can upload lessons from past sessions, and this machine's sessions contain our keys.

## The 2-minute demo

| Time | Beat | Risk |
|---|---|---|
| 0:00 to 0:15 | The problem, with one sourced case | None |
| 0:15 to 0:30 | Two clocks per person; the map colored by plan state | County replay must be generated on the demo laptop |
| 0:30 to 1:00 | The building agent on a real building | A live survey takes 55 to 61 seconds, longer than this beat. Either start it at 0:15 and return to it, or show a pre-surveyed building with its "cached" label. Decide and rehearse. |
| 1:00 to 1:25 | Scrub the outage; a refuge is proposed; the dispatcher approves; the phone rings | Real phone needs Photon; otherwise the browser phone |
| 1:25 to 1:50 | The crews chart | Say what the building line is and is not |
| 1:50 to 2:00 | Close | None |

Sponsor judges visit separately. Same build, different emphasis: CoStar gets the building beat at length, LangChain
the agent trace and approval, Photon the call and the text.

## What is left, in order

| # | Item | Owner | Blocked on |
|---|---|---|---|
| 1 | Photon project: iMessage, an SMS number, a Voice profile; then the follow-up text and a real call | Team, then build session | Account creation |
| 2 | Decide the demo's building beat (live or pre-surveyed) and rehearse the full run twice | Team | Nothing |
| 3 | A measured number for the building layer that is honest: hours of earlier warning per resident, and a refuge capacity limit | Build session | A decision to do it |
| 4 | Hand-label the ten buildings in `evals/buildings_labels.csv` (the ids are there, the columns are empty) | Teammate | Nothing |
| 5 | Saturday-morning interview: a real business for Peri, and real figures for crews, stock and restock | Team | Nothing |
| 6 | README, Devpost paragraph per track, corrected pitch facts | Build session, team review | Nothing |
| 7 | Rotate the API keys that were pasted into chat | Team | After the weekend |

---

# Part 2: build reference

## Rules that hold everywhere

- Every patient is synthetic, flagged `synthetic: true`, and every view says "simulated".
- No sentence that says help is coming is written by a model. Those are fixed templates, chosen by code, allowed
  only after a job is accepted.
- No medical advice. Medical questions get one fixed hand-off line.
- A move Hearth starts on its own is not messaged, called or dispatched before a dispatcher approves it. Help a
  resident asks for themselves is dispatched without one (there are not enough dispatchers to approve every job); a
  dispatcher is asked only when code cannot place the request.
- No reply is never treated as safe.
- Same seed, same output bytes.
- Every default number is in `config/assumptions.yaml` with a source and a `confirmed` flag. Each run copies the
  file next to its results.
- Every building profile field carries its value, its source (`costar`, `vexcel`, `matterport`, `default`) and a
  confidence. A missing layer is named; nothing is filled silently.
- Sponsor data never enters the repo. It lives in git-ignored `data/raw/` and `data/buildings/<id>/`. Only
  hand-made fixtures are committed.

## Architecture

One Python package, one API, one web app, one SQLite document store. Components share only the contracts, the
store and the run files; they do not import each other's internals.

| Path | What it holds |
|---|---|
| `hearth/contracts.py`, `store.py`, `config.py` | Shared data shapes, the store (`put`, `get`, `all` by kind), config access |
| `hearth/buildings/` | Data tools with cache, profile formulas, crew brief, surveyor agent, refuge finder, records-only profiles, season sweep |
| `hearth/messaging/` | Templates, interpreter, guard, call scripts, call logic and the model endpoint |
| `hearth/population.py`, `outage.py`, `weather.py`, `temperature.py`, `devices.py`, `decision.py`, `planner.py`, `metrics.py`, `sim/` | The simulation |
| `api/main.py`, `api/live.py` | Routes and the approve-then-call flow |
| `web/` | Next.js and MapLibre: map (`/`), results (`/results`), browser phone (`/phone`) |
| `config/`, `evals/`, `tests/`, `scripts/`, `results/` | Assumptions and scenarios, evals, tests, data fetch, run outputs |

Models, set in config: Claude Sonnet 5.5 for the agent coordinator and image reads; Claude Haiku 5.5 for layer
subagents, the call interpreter and the guard.

## Sponsor data, as it really is

| Layer | Access | What we use |
|---|---|---|
| CoStar | A data extract on disk, not an API. 1,758 Houston properties: 1,314 multifamily, 54 hotels, 35 senior housing. | Stories, units, year built, construction material, walk-up and elevator status, property type, location, and the Matterport model ids |
| Vexcel | REST API, under half a second per call | Roof material, condition and shape, tree cover over the roof and lot; the top-down image; plain-language detection of parking and entrances. No roof tone field, so tone is an image read. |
| Matterport | GraphQL API; 1,732 of the 1,758 buildings have a scan | Panorama views sent to the vision model, room tags where present, and the embeddable 3D view. Apartment scans are unit floor plans; hotel scans can include the lobby. |

Field names and coverage are in `docs/toolkit-notes.md`.

## Building agent

- **Surveyor** (`hearth/buildings/agent.py`): a `deepagents` deep agent. It writes a to-do plan, dispatches three
  subagents in one turn (`costar`, `aerial`, `interior`), saves each layer's findings to files that double as the
  cache, asks one follow-up where layers conflict, then calls `write_profile` once. That tool rejects any field
  without one of the four sources. On any error or timeout the survey still ends with a default-backed profile and
  the error recorded.
- **Derived numbers are code** (`profile.py`): heat time constant = 8 h default, scaled by construction, roof tone,
  tree cover and age, clamped to 3 to 24 h; delivery time = 10 minutes plus 4 per floor when there is no working
  elevator. A heuristic, labeled as one; coefficients in config, unconfirmed.
- **What each layer changed**: hours until unsafe at 35 °C, shown with each layer's fields reset to default.
- **Crew access brief** (`brief.py`): built only from fields with a real source. It says "floor plan of this unit
  type", never the patient's own rooms.
- **Refuge finder** (`refuge.py`): searches CoStar within 15 km for hotels and senior housing outside the dark
  area, surveys up to three candidates (cache first), filters with a code rule (a wheelchair or bedbound patient
  needs a step-free entrance, and an elevator above one floor; unknown access is ineligible), and stops at the
  approval interrupt. A rejection reason is appended to the agent's memory file and read on the next proposal.
- **Records-only profiles**: `python -m hearth.buildings bulk` builds a profile for every Houston home and refuge
  from CoStar and Vexcel fields with no model call. 1,386 are stored, plus 6 agent surveys. The interface marks
  which is which.
- **Season sweep**: `python -m hearth.buildings sweep` ranks buildings by hours until unsafe.
- **Measured**: a fixture survey takes 38 s; a real hotel 61 s with two conflicts found; a real apartment 55 s.
- **Not done**: the ten-building accuracy check (labels are empty).

## Voice and text

- **Call logic** (`voice.py`, `scripts.py`): two scripts, the impact call and the move-consent call, plus inbound
  calls matched by caller number. A backup number counts only after the caller confirms the read-back. A vague
  later turn never overwrites a confirmed fact. Three silences end the call and escalate. A consent call is
  refused unless a dispatcher-approved proposal exists for that patient.
- **Interpreter** (`interpreter.py`): Claude Haiku turns each caller turn into structured fields; one retry on bad
  output, then hand-off to a person. Plain yes, no and keypad digits are read by code.
- **Guard** (`guard.py`): a model-written acknowledgment is spoken only if it implies no help, safety or timing.
- **Templates** (`templates.py`): 16 fixed lines and the table of when each is allowed.
- **Model endpoint**: `POST /voice/v1/chat/completions`, which ElevenLabs calls as its model. Turn-taking is set to
  patient, with keypad input on.
- **Browser phone**: `/phone`, on the ElevenLabs React SDK, with a text-only mode.
- **Eval, 50 invented caller turns**: backup hours within 10% on 28 of 30; needs-help-now right on 7 of 8;
  escalation precision 83%, recall 86%; guard canaries 20 of 20; interpreter latency median 1.36 s, 90th
  percentile 2.77 s. Failures are listed in `evals/report.md`. Known weak spots: it over-escalates suspicious
  callers, and it took "about 40 hours" at face value where the case meant 4.
- **Not done**: the Photon follow-up text and the real number over SIP. No real phone call has been placed.

## Help loop (resident and responder sides)

- **Personas, not logins** (`/start`): a resident picks a demo patient, a responder types a crew name; the choice
  lives in the browser. `/resident` holds the home markup and the help panel, `/responder` the crew's setup and
  jobs, `/dispatch` the queue.
- **A resident's request is the go-ahead** (`hearth/dispatch.py`). "I need help" opens a request; "I'm safe" closes
  one that no crew has picked up. Silence is never read as safe.
- **A model orders, code places.** One Claude Sonnet call per new request orders the waiting requests and gives each
  a one-line reason, shown to crews and dispatchers only. The answer counts only if it is exactly the ids sent;
  otherwise the planner's risk-per-hour order is used and the request says so. Code then picks the nearest refuge
  that passes the access rule and has a place left, and offers the job to the nearest free crew that fits (a power
  wheelchair needs a lift, a bedbound resident a stretcher, the device must fit the vehicle), preferring one that
  carries what the device leans on.
- **The crew accepts.** An offer not answered in 90 seconds passes to the next crew and sets the first off duty
  until it says otherwise. A dispatcher can take over any open request, for example when a crew goes quiet.
  The resident's tracker is fixed lines chosen by state; the crew and arrival window appear only after Accept.
- **A person only by exception.** No refuge passes, or no crew on duty can carry the resident: the request is
  listed under "needs a person". A request waiting for a busy crew is just queued.
- **Refuge capacity** is 5% of the building's CoStar unit count, at least 1: a placeholder. Nothing is booked and
  power at the refuge is not verified; every screen that shows a refuge says so.
- **Limit.** Records-only profiles do not know whether an entrance is step-free, so for a wheelchair or bedbound
  resident almost no refuge passes and the request goes to a person.

## Simulation

- **Population**: 23,273 patients from emPOWER July 2024 ZIP totals, homes placed at random inside each ZIP.
  2,939 of them live in 1,027 CoStar buildings (a cap of 3 per building keeps this at 13%, below the 35% target).
  Half have complete profiles; the rest get conservative defaults.
- **Outage**: EAGLE-I customers-out for Harris County, divided by the customer total from the dataset's own
  county file. 58 intervals are corrected and listed: a late onset, a false dip, and near-zero readings. The
  simulated share of dark homes stays within 0.5% of the curve. Darkness is not geographic.
- **Weather**: hourly IAH temperature and humidity.
- **Clocks**: backup drains while the home is dark; indoor temperature drifts toward outdoor at the building's time
  constant; unsafe means a heat index above 32 °C or below 16 °C for a sensitive patient. Home dialysis is a
  treatment deadline within two days, not a draining battery.
- **Decision** (`decision.py`), first match wins: unsafe home, then unsafe temperature (never "fine on own
  backup", however charged the device), then dialysis, then backup covers the outage plus 12 hours, then resupply,
  then move, then urgent. Switching between resupply and move needs two ticks.
- **Planner**: greedy, highest risk per hour left first. Crews belong to suppliers and deliver only for their own
  unless mutual aid is on.
- **Policies**: `p0` phone tree; `p3` Hearth; switches `--no-buildings`, `--no-moves`, `--mutual-aid`.
- **Speed**: a full-county run takes about 6 seconds and writes about 350 MB; the 250-run sweep takes about 4.5
  minutes on 10 cores.
- **One documented-case replay**: a synthetic stand-in for the Spring, Texas case, labeled as simulated. It gives
  one patient all 20 crews, so it is optimistic.

Sources, corrections and the two oddities we investigated are in `docs/sim-notes.md`.

## API and web

| Route | Purpose |
|---|---|
| `GET /api/runs`, `/api/runs/{id}/meta`, `/snapshots/{i}`, `/events` | The replay |
| `GET /api/results` | The crews sweep |
| `GET /api/buildings`, `/api/buildings/ranking`, `/api/buildings/{id}`, `/image` | Profiles, brief, layer effects |
| `GET /api/buildings/{id}/survey` | The live agent trace, streamed |
| `POST /api/patients/{id}/propose` | The refuge finder, streamed, ending at the approval pause |
| `GET /api/demo-patients` | The demo patients a resident persona can pick |
| `GET /api/patients/{id}/home` | The patient and the home markup they saved, if any |
| `PUT /api/patients/{id}/home` | Save the home markup: device answers, the matching scan, outside and inside pins |
| `GET /api/homes` | Every saved home markup with its patient and address, for the responder's job list |
| `GET /api/proposals`, `POST /api/proposals/{id}/decision` | Approve or reject, with a reason on reject |
| `POST /api/calls`, `GET /api/calls/{id}` | Start a call (refused without an approved proposal); read its transcript and confirmed facts |
| `POST /voice/v1/chat/completions` | The model endpoint ElevenLabs calls |
| `GET`, `PUT /api/patients/{id}/home`, `GET /api/homes`, `GET /api/demo-patients` | The resident's home markup |
| `GET`, `POST /api/patients/{id}/help`, `POST /api/patients/{id}/safe` | A resident asks for help or says they are safe; the tracker's fixed lines |
| `PUT /api/crews/{crew}`, `GET`, `POST /api/crews/{crew}/job` | Crew setup; the crew's current offer or job and its next step |
| `GET /api/dispatch`, `POST /api/dispatch/{id}/handled` | Every help request in order, and the ones that need a person |

The map opens the county Hearth replay when one has been generated, else a sample. With no API configured the web
app reads hand-made files and shows a "Sample data, not results" banner.

## Run it

```bash
uv sync && cp .env.example .env
uv run pytest
uv run python scripts/fetch_data.py --scenario beryl_2024
uv run python -m hearth.buildings bulk
uv run python -m hearth.sim sweep --scenario beryl_2024
uv run python -m hearth.sim run --scenario beryl_2024 --policy p3 --seed 1 --crews 20
uv run uvicorn api.main:app --port 8000
cd web && npm install && NEXT_PUBLIC_API=http://localhost:8000 npm run dev
```

## Assumptions that flatter Hearth

List these beside the results, every time.

- Simulated patients answer at configured rates, and crews accept jobs instantly.
- Refuges have no capacity limit, so the building-data gap is an upper bound.
- Hearth assumes per-home outage status from the utility, which most utilities do not share today.
- Dispatcher approval is assumed instant in the simulation; the live app requires it.
- The indoor temperature model and the building time constants are simple heuristics.
- Crews work around the clock; stock never restocks; crew counts, stock and phone-tree staffing are placeholders.
- Every ZIP gets the same device mix, and the Medicare-only count misses children and younger adults.

## Change log

**v6 (November 14, 2026).** Rewritten as built. Scenarios cut to Beryl; policies to five; sourced device mix;
dialysis as a deadline; records-only building profiles; elevators from CoStar and unit layouts from scans;
two-part crew brief; ElevenLabs and Photon in place of Twilio and SMS; crews 20 to 320; first real results and
their limits; documented-case wording corrected against sources.

**v5 and earlier.** The team's planning spec, not in this repository.
