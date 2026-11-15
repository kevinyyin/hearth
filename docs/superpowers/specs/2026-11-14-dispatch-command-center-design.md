# Dispatch command center

Written Saturday, November 14, 2026, late, from a design conversation with the team's script writer. Builds on `main`
at `ef59445` (call-everyone rounds and shelter search merged).

## Intent

The dispatch page today is six unrelated boxes stacked in a column, and it names people by ID. The script writer said
it "makes zero sense". It is also where the demo video shows Hearth working, so it has to tell the story at a glance:
who is out there, what needs a person, and what Hearth is doing on its own.

Two asks from the same conversation are folded in here because they meet on this page:

1. **The LangChain agents start on their own.** "When they call in from a building, all the subagents from LangChain
   Deep Agent should be automatically activated so the dispatcher does not have to do anything manually." Today the
   building survey and the refuge search start only from buttons on the map page's building panel.
2. **Before the storm, Hearth calls people** (already built and merged as the three storm rounds, PR 52). This page
   is where the rounds are started and their results read.

## Goals

- One screen, chosen by the script writer from three options: **a county map with household pins, and a rail on the
  right** ("C. Command center").
- The dispatcher clicks nothing unless something is under "Needs you".
- The agents' work is visible live, so a viewer sees CoStar, Vexcel and Matterport being read without anyone pressing
  a button.
- Households are named by address, never by patient ID.

## Non-goals

- No change to how requests are ordered or offered to crews. Placement changes in one place only: an approved refuge
  proposal becomes the drop-off for that resident's request (see "Builder questions settled").
- No change to the call scripts or the storm rounds' calling logic.
- No new map style or visual world: the app's "paper" look (`web/app/globals.css`) stays.
- The map page (`/`) keeps its county replay; only its approve/reject moves here (see below).

## Anti-goals

- An agent that delays a person in danger. Agents run beside the instant rule-based path, never in front of it.
- A screen that claims more than is true: shelter leads are "call to confirm", a refuge's power is "not verified",
  and simulated households are labelled simulated.
- Running the same building's survey twice at once because two dispatch tabs are open.

## Constraints

- Hosted on Vercel (Python API, 300 s function limit). Work started after a voice turn's reply may be cut off, and a
  building survey takes about a minute. So agents are started by requests the page makes, not by background threads
  in the voice endpoint. (Agreed in the conversation: the dispatch page starts them.)
- Real calls go only to numbers in `HEARTH_DEMO_CALLERS`; the storm rounds already enforce this.
- A full agent survey costs model calls; never start one for a building that already has an agent profile
  (`store.get("profile", id)["method"] == "agent"`), and `agent.survey` already returns the cached profile.
- Next.js App Router, React, Tailwind 4, MapLibre (already a dependency, `web/components/Map.tsx` shows the setup).

## Approaches considered

| | What | Trade-off |
|---|---|---|
| A. Inbox | Ordered by urgency: needs you, help in progress, everyone registered, crews | Most practical; least visual for the video |
| B. Pipeline | Each household a card moving across columns: called, registered, researched, needs help, crew on way, safe | Tells the story; weak for a real dispatcher with many households |
| **C. Command center (picked)** | County map with pins plus a rail | Most impressive and best for the video; most work |

For starting the agents, a server-side background thread on each call was rejected (unreliable on Vercel). The page
starts them, which also puts their live trace on screen.

## The design

High-fidelity mockup: `.superpowers/brainstorm/11988-1794705309/content/dispatch-hifi.html` in the main checkout
(local only). Desktop is a header, then a two-column body: the map fills the left, a 384 px rail on the right. Under
960 px wide the rail and the household card stack below the map.

### Header

- "Dispatch" in the display face, with one line under it: "Harris County · simulated storm · real calls go only to
  numbers on the demo list".
- The three storm rounds as one segmented control: rounds already placed show a check; the next round is the dark
  primary button ("Call everyone: landfall day"); later rounds are plain.
- Under it, one line for the last round placed: when, calls placed, how many registered, how many failed. This needs
  the server to remember which rounds ran and their results (today it stores only the time of the last one).

### Map

- Every household Hearth knows from a phone registration or a help request is a labelled pin at its building's
  coordinates: address, then a short status ("1 h left", "crew A, 14 min", "agents researching").
- Pin colour by state: needs you (`#c4461a`), waiting (`#a87400`), crew on the way (`#2a78d6`), safe (`#0e7a54`).
- Behind them, small faint dots for the simulated county, labelled "Simulated" in the legend. Source: an existing
  replay run's patient positions; a sample of a few hundred is enough.
- The chosen crew staging lot appears as a dark square "P" pin.
- The view fits all real pins, padded so the household card never covers one on wide screens.

### Household card (click a pin)

- Address and apartment; "Registered by phone [time] · asked for help [time]".
- **From the call:** device and backup hours, floor and building, room, door.
- **The building, researched by the agents:** the profile's sourced fields with a source chip each (CoStar, Vexcel,
  Matterport), or "Agents researching…" while a survey runs.
- **Where to take them:** the refuge if one was placed; otherwise the reason none fits, and shelter leads with their
  aerial thumbnail, distance, ZIP and "call to confirm".
- Actions: "Take over" (today's mark-handled) and "Open the floor plan" (the scan view that already exists).

### Rail, top to bottom

1. **Needs you (n)**, tinted red: requests code could not place (with "Take over"), registration calls that need a
   person, and refuge proposals waiting for approval (Approve / Reject, moved here from the map page's building panel;
   a rejection still needs a reason). Empty state: "Nothing needs you."
2. **Agents at work (n):** each running or just-finished agent, with the building, the kind (building survey / refuge
   search), a line per step with a check or a live dot and its seconds, and what started it ("Started by the
   registration call at 10:06 PM"). Finished agents stay a few minutes, then drop off.
3. **Help in progress (n):** the queue in the model's order, each with its state chip (crew and minutes, or "waiting
   for a crew") and the model's one-line reason.
4. **Crews (n):** vehicle and equipment, and who they are with or "free".

The staging lot proposal (today's `StagingCard`) moves into the card for the lot pin.

### Agents start on their own

- **Building survey:** for every phone registration whose building has no agent profile, the page starts
  `GET /api/buildings/{id}/survey` and streams its trace into "Agents at work". The registration call is what
  creates the registration, so the trigger reads as "started by the registration call".
- **Refuge search:** for every waiting request that code could not place because no refuge fits, the page starts
  `POST /api/patients/{id}/propose`. Its end is either a proposal (it appears under Needs you for approval) or the
  shelter leads (they appear on the household card).
- **Never twice at once:** the server refuses to start a second survey or refuge search for the same building or
  patient while one is running, and the page does not retry a finished one. If the page is closed, nothing starts;
  that is accepted.

## Decided by the script writer

- Option C, the command center. Approve and reject live on this page.
- The agents start without a dispatcher click.

## My calls (correct any of these)

- Simulated households shown faintly behind the real ones, so the map isn't one pin in the video.
- The page, not the voice endpoint, starts the agents (Vercel constraint).
- The refuge agent runs only for requests the rules could not place, so it never slows a person in danger.
- Display face and palette are the app's existing ones.

## Builder questions settled (my calls after the review; the script writer approved building without another round)

1. **Approve sends a crew.** When the dispatcher approves a refuge proposal for a request code could not place, that
   refuge becomes the request's drop-off and placement runs again, so a crew is offered and the story ends with a
   crew on the way. This is the only change to `hearth/dispatch.py` placement. It follows what the script writer said:
   "if we're moving the person, that should be a dispatcher call." Placement also runs again when any agent survey
   finishes (`place_again` for waiting requests), since a newly surveyed hotel can unblock someone.
2. **One entry per request in "Needs you", and only when a person is needed.** While the refuge agent is running for
   a blocked request, it shows under "Agents at work", not under "Needs you". When the agent ends, the request enters
   "Needs you" once: as Approve / Reject if it proposed a refuge, or as "No refuge fits · N shelter leads" with
   "Take over" if it did not. A request blocked for another reason (no crew can carry them) goes to "Needs you" at once.
3. **Agent runs live on the server.** Each run is a stored record (kind, building or patient, what started it, status,
   step lines with times, result). Every tab reads the same records; a reload loses nothing and starts nothing new.
   Shelter leads are stored with the run. A refuge search runs once per request; it runs again only after the
   dispatcher rejects its proposal (the rejection reason already goes to the agent's memory file). A building survey
   runs once per building (an agent profile is its result). Finished runs drop off "Agents at work" after
   10 minutes (a config value) but their results stay on the household card.
4. **Storm-round line counts only what the server knows.** For the last round: when, calls placed, calls that could
   not be placed, and registrations made by that round's calls (call records carry `ctx.storm`). No "no answer"
   count: the server is not told about hang-ups. Any round may be placed again after the existing two-minute guard;
   a round shows a check once it has been placed at least once.
5. **Staging lots as pins.** Proposed lots show as outlined "P" pins; the chosen lot is a solid "P". Each lot's card
   holds today's staging card content and the Choose / Clear action.
6. **Which households, and a clean start.** The map shows phone registrations and every request from the last 24 hours
   (a config value); finished requests show green. A command-line reset (not a page button, since it deletes stored
   data) clears help requests, call records, agent runs and storm-round history, and registrations for the demo
   numbers, so a rehearsal starts clean and stale blocked requests do not start agents.

## Left to the builder

- Component split, polling cadence, how the trace stream is shared between the rail and the card.
- The exact endpoint shape for map positions, the storm-round history and the in-progress guard.
- Tests: the in-progress guard, the storm-round history, and the new dispatch data fields need pytest coverage; the
  page needs a browser check at desktop and phone widths.
