# Help loop: a resident asks, a crew is sent, a refuge is the drop-off

Design · slice 2 of 3 (home markup, help loop, contacts) · November 14, 2026 · builds on PR 20 (`home-markup`)

## Why

Slice 1 lets a resident describe their home and a responder read it. Nothing yet connects the two in an emergency.
The user's point: there are not enough dispatchers, so a plan that waits on one for every job rebuilds the
bottleneck. This slice lets a resident's own request send a crew, with a person pulled in only when Hearth cannot
place the request itself.

## Goals

- A resident persona presses "I need help" or "I'm safe" and watches a tracker.
- A responder persona sets up their crew once, then takes one offer at a time and gets the next after a drop-off.
- Open requests are ordered by a Claude model and placed by code: a crew that fits, and a refuge that passes the
  access rule and has a place left.
- It runs end to end in the browser for two residents and two crews, on real Houston buildings.

## Not in this slice

Contacts and live-in helpers (slice 3). Real logins. Messaging, calling or texting anyone. Booking a room. Live
crew positions (a crew is at its base, or at its last drop-off). More than one resident per trip.

## Must not happen

- The tracker never says a crew is coming, or gives an arrival time, before that crew has tapped Accept.
- No text written by a model is shown to a resident. The model's reasons go to crews and the dispatch page only.
- Silence is never read as safe. Only the "I'm safe" button records safe.
- Nothing claims a refuge has power or a room held. Every refuge shown says "not booked, power not verified".
- No real person's data. Every screen keeps the "simulated" label.

## Decisions the user made (November 14)

| Question | Decision |
|---|---|
| Who releases a job to a crew | The resident's own request is the go-ahead. A dispatcher sees a "needs a person" list only for requests code could not place. |
| Model or code | The model orders the open requests and gives one line of reason each. Code picks the crew and the refuge. If the model fails, the existing risk-per-hour order is used and the request says so. |
| What the tracker may say | Fixed lines chosen by code. "On the way" and the arrival window appear only after the crew taps Accept. A crew that declines or does not answer passes the job to the next crew. |
| Refuge capacity | Each refuge takes 5% of its CoStar unit count, at least 1. A placeholder, published as unconfirmed. |
| The model step | One quick call per new request (approach A below), not an agent. |

Spec rule change that follows: "No move is messaged, called or dispatched before a dispatcher approves it" becomes
"A move Hearth starts on its own is not messaged, called or dispatched before a dispatcher approves it. Help a
resident asks for is dispatched without one; a dispatcher is asked only when code cannot place it." The rule on
help-is-coming sentences stands as written.

## Approaches

| | What | Verdict |
|---|---|---|
| A | One Claude call when a request comes in returns the order and reasons as schema-checked JSON; code places; pages poll every 3 seconds | Picked by the user. About 3 seconds, the same placement for a given order, a rule-based fallback |
| B | A deepagents agent with tools, pausing on exceptions | Rejected: 30 to 60 seconds per dispatch, and it re-opens "model assigns" |
| C | Run the simulation's planner loop live | Rejected: built for simulated time and supplier stock |

Builder's calls within A, not the user's: Sonnet 5.5 for the ordering (`models.dispatch`; it runs on every request,
so speed over depth); the vehicle and equipment lists; the fit rules; the refuge is chosen by the existing code rule
over stored building profiles, not by the 30 to 60 second refuge agent.

## What gets built

### Data: two new document kinds in the existing store

`crew`, keyed by crew name (the responder persona's id; letters, digits, space, dash, underscore, at most 40):
base building id, current position (starts at the base; set to the refuge after each drop-off), vehicle (`car`,
`van`, `wheelchair_van`, `ambulance`), equipment (any of `oxygen`, `power`, `wheelchair_lift`, `stretcher`), and
`on_duty`.

`help`, keyed by patient id, one per resident, replaced when they ask again after it ended:

- `state`: `waiting` → `offered` → `accepted` → `at_door` → `riding` → `dropped_off`; or `safe` (the resident
  said so) or `handled` (a dispatcher took it over). The time each state was entered is kept for the tracker.
- `rank`, `reason`, `ranked_by` (`model` or `rule`).
- `blocked`: why this request needs a person, else empty. Set only when no refuge passes, or no crew on duty could
  ever carry this resident. A request that is only waiting for a busy crew is a plain queue entry, not blocked
  (builder's call: sending every queued request to a dispatcher would rebuild the bottleneck).
- `declined_by`: crews that declined or timed out.
- `refuge`: the existing `RefugeOption`.
- `job`: the existing `Job` contract, kind `ride`, `org_id` the crew name, `eta` the expected arrival at the door.
  Its status follows the state: `created` while offered, `accepted` from accepted to riding, `completed` at
  drop-off, `failed` if the resident says safe first.

### Ordering (model)

On each new request, one call to `models.dispatch` with every `waiting` request: device and detail, mobility, heat
or cold sensitivity, hours OK without the device, backup plan, note, minutes waiting. Backup plan and note are the
resident's own typing: the prompt marks them as untrusted text, never instructions. The answer is schema-checked
JSON: the patient ids in order, each with a reason of at most 140 characters, no medical advice, no promise. Code
accepts it only if it is exactly the set of ids sent; anything else (timeout, error, a missing or invented id)
falls back to the planner's own key, risk weight over hours left, and `ranked_by` says `rule`. Requests already
offered or further along keep their place; later dispatch runs reuse the stored order without a model call.

### Placement (code)

`dispatch.run()` runs after: a new request, a decline or timed-out offer, a drop-off, "I'm safe", a crew saving
its setup or going on duty. Under a lock in the process. For each waiting request, in order:

0. **Where the resident is** (builder's call). The home markup's building when there is a markup and the building
   is in CoStar; else the patient record's building when it is in CoStar; else the patient record's own latitude,
   longitude and ZIP with no address, as the existing proposal route does. The fixture personas (`B-SAMPLE`) take
   the last path on real data; their card says "no building on record".
1. **Refuge.** Hotels and senior housing within `refuge.search_radius_km` of the resident, nearest
   first, outside the dark area (the ZIPs of residents with a live request), with a stored profile that passes
   `refuge.eligible` for this resident's mobility, and a place left. Capacity is `max(1, floor(units × share))`,
   1 when units are unknown; a place is used by every request from `offered` through `dropped_off` at that
   refuge. None → `blocked`, with the reason.
2. **Crew.** `planner.assign` with one new optional argument, a `fits(need, crew)` test. A crew is free when it
   is on duty and has no request between `offered` and `riding`. It fits when: it has not declined this
   request; a power wheelchair has a wheelchair lift; a bedbound resident has a stretcher; the device's longest
   side (from the home markup; no markup means no size limit) is within the vehicle's limit. First try only
   crews that also carry what the device leans on (oxygen for oxygen, power for the rest); if none, any crew
   that fits. `assign` then picks the nearest. If no crew on duty fits at all (or none is on duty) → `blocked`:
   "no crew on duty can carry this resident". If crews fit but all are busy, the request stays `waiting`,
   unblocked, and is tried again on the next run.
3. The request becomes `offered`, with the refuge and the job. ETA = now + `planner.travel_h` from the crew's
   position to the resident's building; the window is ETA to ETA + `dispatch.eta_window_min`, recomputed at
   Accept.

An offer not answered within `dispatch.offer_timeout_s` goes back in the queue and sets that crew off duty; this is
checked whenever the tracker, the crew's job or the dispatch page is read. Unlike a decline, a missed offer does not
bar the crew from that resident once it is back on duty (changed after review: one missed offer in a background tab
left a single-crew demo stuck).

### API

| Route | Purpose |
|---|---|
| `GET /api/patients/{id}/help` | The request and the tracker's steps, each a fixed line with its time |
| `POST /api/patients/{id}/help` | Open a request, order, place. 409 if one is live |
| `POST /api/patients/{id}/safe` | Record safe: closes a `waiting`, `offered`, `accepted` or `at_door` request and frees its crew; with no request, or one already `safe` or `handled`, stores a `safe` record. 409 from `riding` on, so a drop-off record (which holds the refuge place) is never overwritten by it |
| `GET`, `PUT /api/crews/{crew}` | Crew setup |
| `GET /api/crews/{crew}/job` | The crew's current offer or job: request, patient, home markup (may be none), address, refuge |
| `POST /api/crews/{crew}/job` | `accept`, `decline`, `arrived`, `picked_up`, `dropped_off`, naming the resident on the card; refused out of order or for another resident |
| `GET /api/dispatch` | Every request in order with reasons, and every crew |
| `POST /api/dispatch/{id}/handled` | A dispatcher takes over any live request: a blocked one, or one whose crew went quiet (widened after review; an accepted job otherwise had no exit) |

The tracker's lines live in one Python module and are chosen by state. The accepted line is the existing
`move_confirmed_ride` template, used only when `templates.allowed` says so for an accepted job.

### Pages

**Resident (`/resident`).** A help panel above the home setup:

```
[ I need help ]   [ I'm safe ]        In an emergency call 911.

● Request received            1:52 pm
● A crew has been asked       1:52 pm
● A driver from Crew Alpha has accepted your ride. They expect to arrive between 2:10 pm and 2:25 pm.
○ At your door
○ On the way to <refuge name>
○ Dropped off
```

After "Request received", a request waiting for a busy crew shows "Waiting for a free crew."; a blocked one shows
"A person at the health department is looking at your request." Times are shown in the browser's time zone.

**Responder (`/responder`).** First visit: setup (base by the same building search the resident uses, vehicle,
equipment). Then: off duty / on duty; "Waiting for a job"; an offer (resident, device, the model's reason, distance,
refuge) with Accept and Decline; after Accept the slice 1 job card, the refuge as destination ("not booked, power
not verified", places left), and one button for the next step: Arrived, Picked up, Dropped off. After a drop-off
the next offer appears. The "every saved home" list goes away. A resident with no home markup still gets a card;
it shows nothing the resident did not say.

**Dispatch (`/dispatch`, linked from `/start`).** "Needs a person" on top (blocked requests, the reason, a "Mark
handled" button), then the queue in order with each reason and whether the model or the rule ordered it, then the
crews and what each is doing.

### Config (appended to `config/assumptions.yaml`, all unconfirmed placeholders except the model id)

`models.dispatch`; `dispatch.refuge_capacity_share` 0.05; `dispatch.eta_window_min` 15; `dispatch.offer_timeout_s`
90; `dispatch.vehicle_max_item_cm` car 60, van 150, wheelchair van 150, ambulance 100.

### Demo data

None added. `main` gained three synthetic residents in real CoStar buildings (`demo-3`, `demo-4`, `demo-5`, from the
demo-polish change) while this was being built, and `/api/demo-patients` now lists only personas whose building is
in the data being served. With `demo-2` that is four residents on real data: two who walk or use a manual
wheelchair, two who need a lift or a stretcher.

## Known limits

- Records-only building profiles do not know whether an entrance is step-free, and the access rule treats unknown
  as ineligible. Today 1 of the 85 refuges passes for a wheelchair or bedbound resident, 85 of 85 for one who
  walks. So wheelchair residents will often land on "needs a person". That is the rule working, and it is the
  exception path the demo shows.
- Refuge places are counted from the stored requests. A resident who asks again after a drop-off replaces their
  record and frees the place.
- The lock is per process; two hosted instances could offer one crew two jobs. Acceptable for a demo.
- Capacity, the timeout, the ETA window and the vehicle limits are placeholders.
- The dark area is only the requesters' own ZIPs, as in the existing proposal route.
- Travel is straight-line distance times the detour factor, as in the simulation.

## Left to the builder

Component split and styling within the existing tokens. Where the Python lives (`hearth/dispatch.py` suggested).
Poll interval. Tests: the loop through the API on fixtures with the model call patched (order, fit rules,
capacity, decline to the next crew, timeout, safe, next offer after a drop-off, each blocked reason, fallback on a
bad model answer, no arrival line before Accept); one web test for a pure helper. Update `docs/spec.md`: the
reworded rule, the new routes and pages.
