# Voice: residents register, ask for help and hear back by phone

Design · November 14, 2026 · builds on the merged resident, responder and dispatch pages, the help loop and the
`Home` record (GitHub PRs 20 to 27). The phone becomes the resident's way in; the resident page stays in the code as
a backup. Brings back two items from the weekend design's Cut list: the profile setup call and the pre-landfall
check. Moves two items from "Later" in `docs/outage-scope-update.md` into this weekend: the open line for callers
Hearth does not know (demo callers only) and the area-wide alert (simulated).

## Why

A CoStar judge pressed on voice. People on home medical devices, often older and in a storm, will not open a website
to sign up, pin their home, or press "I need help". They will make or take a phone call. So everything the resident
does happens on a call: registering, the things records and scans cannot tell a crew (which unit, which building,
which floor, which door, which room the machine is in), asking for help, saying they are safe, and hearing what
happens next.

The CoStar workshop asked for layers combined to show what one source misses, an insight that changes what the user
does, and AI inside the work rather than beside it. So the building data does two jobs. It decides what the call
asks: a question exists because the caller's CoStar record leaves that fact open, and a fact the record settles is
not asked. And the answers change decisions the dispatcher can watch: the order of the queue, and whether a refuge
passes its access check.

## Decided by the user

- The resident side is the phone. The Resident link comes off `/start`; the page stays in the code as a backup.
  Contacts, live-in helpers and pins stay on the page. The responder, dispatch and map pages stay.
- Hearth keeps the device registrations and calls registered people.
- Unregistered people in a forecast storm's path are reached by broadcast: the county's alert tells them to call
  Hearth, and that call registers them. Hearth never dials lists of unregistered numbers.
- The registration call asks device, address with apartment number (read back together), hours, then home
  questions built from the building data.
- A registered caller can ask for help or say they are safe by phone, and gets the tracker's updates as texts.
- Built by extending the scripted call (approach A below).
- Fold in six uses of the CoStar data: questions chosen from the record, the apartment number matched to CoStar's
  unit list, a live elevator question on the impact call, a call to the building's office, the answers moving the
  queue, and two small ones (closed hotels left out of refuges; a layer table). Which of them make the build is in
  [Build order](#build-order).

## Goals

- One real inbound call on the Photon line registers a persona caller at a CoStar building in about two minutes,
  with questions chosen from that building's record.
- The caller's apartment number is matched to CoStar's unit list, which gives the floor plan and, where CoStar has
  one, the scan of that floor plan for the crew.
- The registrant calls back, says "help", and the same help request the resident page's button opens goes into the
  queue. A crew accepts on `/responder`, and the caller's phone gets the accepted line as a text.
- A "Storm forecast" button on `/dispatch` sends the simulated county alert text and calls every phone registrant in
  the forecast area to check their details.
- A caller saying the elevator is out moves their request in the queue, with the reason shown.
- One real call to a building's office asks whether it has power and a running elevator, and that answer replaces
  the simulated refuge call where a real number is configured.
- One table shows a single refuge decision under CoStar alone, then adding the aerial image, the scan, and the call.

## Not in this slice

- Deleting the resident page. Contacts, live-in helpers and pins by phone.
- Hearth dialing unregistered numbers. Live hurricane forecasts. Real county alerts (WEA, reverse 911).
- Devices other than the four Hearth models (oxygen, ventilator, home dialysis, feeding pump).
- Surveying a new registrant's building automatically: the dispatcher uses the building panel's survey button.
- Spanish. Editing a registration except by calling again.
- Checked against the CoStar kit and left for later: Vexcel's angled images for the door question; the 1,700 Texas
  home listings whose scan is the actual home; tenant records for pharmacies, oxygen suppliers and dialysis centers;
  flagging a senior community with few registrants.

## Must not happen

- The model writes nothing the caller hears. Every line is a template; the model only reads answers into fields.
  This includes text an earlier model wrote: the survey's `van_dropoff` sentence is never read out.
- A number (house number, apartment number, floor, hours) counts only after the caller confirms its read-back.
- A stranger's real details are stored: only numbers on the demo caller list can register.
- Silence counts as an answer, or as safe. Keypad 1 records anyone as safe: only a spoken "I'm safe" does (on a
  call, keypad 1 means "yes" to the question asked).
- A call or text says a crew is coming, or gives an arrival time, before the crew taps Accept (the help loop's rule).
- The scan is presented as the caller's own rooms. It is the scan of their floor plan, or of a sample unit, and the
  crew's card says which.
- The floor is worked out from the apartment number. In the kit a unit number's leading digits agree with the
  building's story count for about one unit in three, so the floor is always asked.
- A call to a building names a resident, or says that anyone there uses medical equipment.
- A phone number from the CoStar kit is dialed. Every phone number in the kit is fake (area code 555).
- What a resident or a building office said is shown as a verified fact. It is shown with who said it and when.
- The close promises help.

## Approaches

| | What | Verdict |
|---|---|---|
| Call | A. Extend the scripted call: new steps and call kinds in `scripts.py`, new templates, new interpreter fields | Picked by the user. Keeps every call rule and the interpreter evals. Rigid: an answer it cannot read goes to a person |
| | B. Model-led conversation: an ElevenLabs agent with a prompt and tools, Claude writes each line | Rejected: breaks "the model never writes what's said", discards the scripted call and its evals, and the building questions depend on correct tool calls |
| Outreach | Broadcast, they call in | Picked by the user |
| | Hearth dials a county list for the area | Rejected: most calls reach homes with no device, and the list would be fake for the demo |
| Questions | Code picks each home question from the building record, by the table below | Picked: stays inside approach A, and every question traces to a missing field |
| | The same fixed questions for every caller | Rejected: asks a one-story caller for their floor, and shows no use of the record |
| Resident page | The phone does it all; the page leaves `/start` | Picked by the user |
| | The phone registers; asking for help stays on the page | Rejected: the resident would still need the website at the moment it matters most |

## The registration call

Call kind `register`. It starts when a number on the demo caller list calls the line and has no registration.
Today such a caller hears the hand-off line (`_inbound_call` in `hearth/messaging/voice.py`). Each caller turn goes
to the interpreter; code picks the next template, as in the existing calls.

1. **Open.** "This is an automated call from Hearth for the Harris County health department. Does someone at home
   use powered medical equipment, like oxygen, a ventilator, home dialysis or a feeding pump?" No: a polite close
   ("If that changes, call this number. In an emergency, call 911."), and nothing is stored but the call record.
2. **Device**, unless the caller already named it. One of the four; anything else gets the hand-off line.
3. **Address.** "What's the street address, with the apartment number if there is one?" The interpreter returns the
   house number, street name and apartment number, and the ZIP if said. Code looks for exactly one CoStar building
   (`tools.costar_all()`) with that house number and street name. One match: "I have {address}{, apartment {unit}}.
   Is that right?" One read-back covers both. A no asks once more. No match, several matches, or a second no:
   "I couldn't find that address" plus the hand-off line.
4. **Hours.** "If the power went out, about how many hours would you be OK without your {device}?", then the
   existing `readback_hours` step. One wording for every device: the existing `dialysis_check` opens "The power is
   out", which is false at registration.
5. **Home questions**, chosen from the record by the table below.
6. **Home read-back.** One sentence built from what was asked, for example "I have you in building {b}, on floor
   {floor}, using {door}, with the machine in the {room}. Is that right?" A no asks "Which part is wrong?", asks that
   one again, and reads back again.
7. **Close.** "Thank you, you're registered. If a storm or outage reaches you, a call from this number is Hearth
   checking on you. If you need help, call this number and say help. In an emergency, call 911." Then the existing
   text follow-up lists what the caller confirmed.

### Home questions, chosen from the record

Code walks this table in order. A row is asked only when its condition holds.

| Question | Asked when the CoStar record | What the answer gives |
|---|---|---|
| "What's your apartment number?" | lists unit numbers (1,242 of 1,348 Houston apartment communities) and the caller gave none with the address | A match in the unit list gives the floor plan's name and bedroom count, and that floor plan's scan when it has one (728 communities have a floor plan with both). No match after one retry: their words are kept and the call goes on |
| "Your complex has {n} buildings. Which building are you in?" | has more than one building, and the matched unit carries no building name | The building a crew drives to. When the unit carries a building name: "That's in building {b}. Is that right?" |
| "Your building has {floors} floors{, and no elevator}. Which floor are you on?" | has more than one story ("and no elevator" only for a walk-up on record). Unknown stories: the plain question | The floor. A one-story record skips this and stores floor 1 |
| "Is there an elevator in your building?" | states neither elevators nor a walk-up, and the caller is above floor 1 | The resident's statement, stored as theirs |
| "Our aerial photo suggests parking on the {side} side of the building. Is the door a crew should use on that side?" | has a surveyed profile whose `van_dropoff` names a compass side; code takes the side out (the survey's sentence is a hedged guess, 0.35 confidence on the first one checked). Otherwise: "Which door should a crew use?" | Yes stores "{side} side, near the parking"; no asks the plain question and stores their words |
| "Which room is the machine in?" | always | The interpreter gets the room names of the caller's floor-plan scan (or of the building's scans when no unit matched) and returns one verbatim when it fits, plus the caller's words. Without usable room names it gets the bedroom count from CoStar ("a bedroom, the living room, or somewhere else") |

Every existing call rule carries over: silence counting, "needs help now", the medical hand-off, asking for a
person, low confidence going to a person, keypad 1/2/3, the guard on acknowledgments, hanging up after a hand-off.

**When records are written.** The patient, contact and home documents are written once device, address, hours and
floor are confirmed, so no required field holds a number the caller did not give. Later answers update the home
document. Until then the confirmed answers live in the call document (the server is not told about a hang-up).

**A call that ends early** still leaves something a person can act on, so "I've flagged this call for a person" is
true: a `register` call that ended before the records were written shows on `/dispatch` under "Needs a person", with
the caller's number and what they confirmed.

**What counts as registered:** a home document whose `source` is `phone`. Contacts made for synthetic demo patients
(`python -m hearth.messaging.photon contact`) do not count; they stay for the outbound demo calls. One phone with
several registrations uses the newest. `python -m hearth.messaging.voice reset <phone>` removes one phone's
registrations so rehearsals start clean (the store gains a delete if it has none).

## Help by phone

**A registered caller calling in.** If they have a live help request, the call opens with its latest tracker line
("Your request: a driver from Crew Alpha has accepted your ride..."). Then: "If you need help now, say help, or
press 2. If you're safe, say I'm safe. To check your details, say details."

- **Help** (also "needs help now" or the keypad 2 on any call: this one, the check call, or the impact call):
  1. If the patient's mobility was never asked: "Can you walk to a car, on your own or with someone helping?" Yes:
     `walks_with_help`. No: "Do you use a wheelchair, or do you stay in bed?" Wheelchair: `wheelchair_power`;
     bed or unclear: `bedbound`. Each choice is the more careful of its pair, so a crew comes with a lift or a
     stretcher rather than without. Asked once and stored on the patient.
  2. `dispatch.open_request(patient_id)`, the same function the resident page's button reaches.
  3. "I've asked for a crew. We'll text you each step, and the arrival time once a crew accepts. If this is an
     emergency, hang up and call 911." A request already live: "Your request is already in," and its latest
     tracker line.
  4. "Needs help now" still also flags the call for a person, as today: the request goes into the queue, and a
     person sees the call.
- **I'm safe:** `dispatch.mark_safe(patient_id)`, then "Thank you. I've noted that you're safe. Call this number if
  that changes." From `riding` on, `mark_safe` refuses (the drop-off holds the refuge place); the caller hears the
  latest tracker line instead. Only spoken words count, never a keypad digit.
- **Details:** the check call below.

**Tracker texts.** Each new tracker line (the help loop's fixed lines, chosen by state) is sent once as a text to the
phone `phone_of` returns, through the existing Photon sender. The accepted line is the existing
`move_confirmed_ride` template and goes out only when `templates.allowed` says so for an accepted job. Lines already
sent are remembered as `message` documents. The send runs after each change of help state in `hearth/dispatch.py`
(new request, offer, accept, arrive, pick-up, drop-off, safe, handled, timeout); a failed text never blocks the
state change.

## The check call for registered people

The same `register` script, started outbound by the storm button, or inbound by saying "details". It opens with "A
hurricane is forecast for your area. We're checking your details are still right." (inbound: "Let's check your
details."). Each step whose answer is registered goes straight to its read-back ("We have you at {address}. Is that
still right?") instead of the question. A correction updates the registration. Impact calls stay outbound-only from
the dispatcher.

## One live question on the impact call

Whether an elevator runs is a fact about today, so it is asked when the power is out, not at registration. The
existing impact call gains one step after the hours read-back, only for a registrant above floor 1 in a building
with an elevator (on record, or by their statement): "Is the elevator in your building working right now?" Yes, no,
or "I don't know" (stored as unknown). A request for help on the impact call goes through [Help by phone](#help-by-phone).

## The building call

Call kind `building_check`, outbound only, started by a "Call the building" button on the building panel. CoStar
holds an on-site phone for 1,272 of 1,348 Houston apartment communities, 51 of 54 hotels and 33 of 34 senior
communities, but every kit number is fake.

1. "This is an automated call from Hearth for the Harris County health department, about {name} at {address}. Do
   you work at this building?" No: a polite close.
2. "Does the building have power right now?"
3. "Is a passenger elevator running right now?" Skipped for a one-story record.
4. Read-back of both, then "Thank you. That's all we need."

The number dialed comes from `HEARTH_BUILDING_PHONES` (environment only: building id to a real number, a teammate's
phone in the demo). A building not on that list has no button and keeps today's simulated answer.

## What the answers change

The impact call and the building call write one `building_status` document per building: power, elevator, who said
it (resident or building office), the call id and the time.

- **The queue.** `dispatch._rank` adds three fields to each row it sends the model: the floor, the elevator state
  with who said it, and `minutes_at_building` from the existing `service_minutes(profile, floor, elevator_working)`
  (10 minutes, plus 4 per floor without a working elevator). The ordering prompt gains one sentence telling it to
  weigh those minutes against the hours left. The fallback rule subtracts them from the hours left. The reason on
  the dispatch board names the elevator when it mattered.
- **Refuge access.** `refuge.confirm_elevator` reads a building-office answer first when it is newer than
  `refuge.building_answer_valid_h` (new assumption), and only then falls back to the simulated call. The reason line
  says "the building's office said so by phone at {time}" or, as today, "(simulated call)".

## Closed hotels

`normalize_costar` marks a hotel whose `propertyHospitality.operatingStatus` is temporarily (2) or permanently (3)
closed as not `existing`, the flag the refuge search already filters on. 5 of the 54 Houston hotels are permanently
closed and can be proposed as refuges today.

## The layer table

`evals/run_layers.py` takes the surveyed hotel CoStar `1508702` (CoStar has no elevator fields for any hotel; its
scan showed an elevator in lobby views) and one wheelchair patient, and runs `refuge.eligible()` four times: with only
the CoStar-sourced fields of the stored profile, then adding the Vexcel-sourced fields, then the Matterport-sourced
fields, then the building office's answer. Fields from a layer not yet added are blanked, so nothing is surveyed
again. It writes each row's result and first reason to `evals/report.md`, as they come out. If no layer changes the
result, the table says so.

## Storm forecast button

On `/dispatch`, labeled "Storm forecast (simulated)". It calls `POST /api/storm`, which:

1. Sends the county alert text through Photon to each number in `HEARTH_ALERT_PHONES` (environment only): "Simulated
   Harris County alert: a hurricane is forecast for your area. If you or someone at home relies on powered medical
   equipment, call Hearth at {line number} so a crew knows how to reach you. In an emergency, call 911."
2. Starts and dials the check call for each phone registration whose ZIP is in `storm.forecast_zips` (a fixed list
   in `config/assumptions.yaml`, from the Beryl replay).

The response lists what was sent and dialed and any failure, and the page shows it.

## Data

- **`patient` doc**, id `R-` plus 8 hex characters, the existing `Patient` contract unchanged. From the call:
  device, `backup_hours_on_hand`, floor, `building_id`; lat, lon and ZIP from the CoStar record; mobility once asked
  on a help call. Fields not asked come from `registration.defaults` in `config/assumptions.yaml`, each with its
  source: `device_detail`, use rate, temperature sensitivity, risk weight, supplier, and mobility `bedbound` until
  asked (most careful: an unasked caller who needs help gets a stretcher crew and a step-free refuge, or a person).
  `phone_status` is `unverified` (caller ID). `synthetic` stays true: every registrant in this demo is a persona.
- **`contact` doc** keyed by patient id, phone = caller ID: what `phone_of` already reads to decide who may be dialed
  or texted.
- **`home` doc**, the merged `Home` contract with these changes:
  - `size` becomes optional. `None` means "not asked": dispatch applies no size limit, as it already does for a
    resident with no home record, and the job card says "not asked". A guessed size would decide which vehicle
    fits.
  - New optional fields: `source` (`web` default, or `phone`), `unit`, `complex_building`, `door`,
    `door_from_aerial`, `room`, `scan_room`, `has_elevator` (the resident's statement). Code reads `unit`, the floor
    and `has_elevator`, so they are fields, not note text.
  - `ok_without_h` is the confirmed hours. `scan_id` is the matched floor plan's scan, so the job card opens it;
    `tools.matterport_scan_ids` must include floor-plan scans for the existing scan check to accept it.
- **`building_status` doc**, above.
- **The call doc** keeps the transcript and confirmed facts, as today.
- **The CoStar reader** (`normalize_costar`) gains, per building: apartment style, number of buildings, walk-up
  flag, on-site phone, hotel operating status, and the floor plans with name, bedrooms, scan ids and unit numbers
  (with each unit's building name where CoStar has one). The normalized Houston file is rebuilt. The unit lists are
  large (about 398,000 unit numbers).
- **Room names** come from `tools.matterport_rooms` through `tools.cached`, fetched when the address is confirmed so
  the room question does not wait on Matterport.

## API

- `POST /api/storm`, above.
- `GET /api/registrations`: phone registrations, newest first, each with patient, home, building address, how its
  last call ended and the call id; plus `register` calls that ended before any registration, with the caller's
  number.
- `POST /api/buildings/{id}/call`: starts the building call; refused for a building not in `HEARTH_BUILDING_PHONES`.
- `POST /api/calls` also accepts kind `register` with a `phone` on the demo caller list: the browser-phone fallback
  (`/phone` calls carry no caller ID), so the demo survives a failed phone line.
- `_patient` in `api/main.py` also reads stored `patient` documents. Today it reads only the demo file and the
  simulation's patient list, so the home and help routes would 404 for a phone registrant.
- Environment only, never in the repo: `HEARTH_DEMO_CALLERS` (who may register; anyone else hears today's hand-off
  line), `HEARTH_ALERT_PHONES`, `HEARTH_BUILDING_PHONES`.

## Pages

- **`/start`:** the Resident link is removed. `/resident` still works by its address, as a backup.
- **`/dispatch`:** a "Registered by phone" section (newest first), register calls that need a person under the
  existing "Needs a person", and the Storm forecast button with its result. A phone registrant's help request shows
  in the queue like any other.
- **`/responder` job card:** for a phone home, a "Said by phone" block with its time: apartment and floor plan,
  building, floor, door, room, elevator. The scan caption for a phone home: "Scan of this resident's floor plan,
  matched from their apartment number. Not their own home." Size shows "not asked".
- **Building panel (map):** the latest `building_status` with who said it and when, and the "Call the building"
  button for buildings on the list.

## Demo

The demo building is Calais Midtown Apartments (CoStar `7768847`): mid-rise, 3 buildings, 6 floors, elevators on
record, 15 floor plans with a scan and listed units. It exercises the building, floor and floor-plan questions, the
live elevator question and the queue change. It has to be surveyed once before the demo for the aerial door
question. (Dover Place, `91567`, has units numbered 1 to 32, one floor plan and two stories, so the apartment
number shows nothing there.)

1. Click Storm forecast on `/dispatch`. A teammate's phone gets the alert text.
2. The teammate calls the line as a persona and registers: building, floor and floor plan, each question opened with
   what the record says.
3. The registration appears on `/dispatch`.
4. The teammate calls back and says "help". The request enters the queue; a crew accepts on `/responder`, and the
   teammate's phone gets "A driver from Crew Alpha has accepted your ride..." The job card shows what was said by
   phone and the scan of the caller's floor plan.

The 2-minute demo plays only part of the calls live. The building call and the layer table belong to the longer
sponsor walkthrough.

## Build order

Proposed; cut from the bottom if behind.

1. The registration call with the record-chosen questions (without the unit-list match), the records it writes,
   `_patient` reading the store, the Resident link off `/start`, "Registered by phone" on `/dispatch`, the job
   card's "Said by phone", and the browser fallback.
2. Help by phone, the mobility question, and tracker texts.
3. Closed hotels (a few lines, and a wrong refuge today).
4. The unit-list match and floor-plan scan, with the CoStar reader additions.
5. The storm button, the alert text and the check call.
6. The live elevator question on the impact call, and the queue change.
7. The building call and `building_status` in `confirm_elevator`.
8. The layer table.

## Known limits

- Speech-to-text on street addresses and apartment numbers is error-prone. The read-back catches wrong ones, and a
  second miss on the address goes to a person.
- The aerial door question works only on surveyed buildings whose drop-off names a side. Elsewhere it is plain.
- Matterport room labels are mostly empty, so the room question will often fall back to the bedroom count.
- A floor plan's scan is one unit of that plan, not the caller's own home.
- CoStar's amenity lists are ids with no lookup table in the kit, so they are unused.
- The kit covers buildings on CoStar's Matterport list only, not every building in Houston.
- Caller ID can be spoofed (existing shortcut in `_inbound_call`).
- A building-office answer is one person's word at one time. It expires, and it is shown with its time.
- Mobility is asked only when someone asks for help, so a request opened before that answer goes the most careful
  way and often to a person.

## My calls, not the user's

- Only numbers on the demo caller list can register. A judge cannot call in from their own phone unless added.
- The storm trigger is a button with a fixed ZIP list; the county alert is a Photon text.
- No CoStar match, or a device outside the four, goes to a person.
- Records are written only once device, address, hours and floor are confirmed; `size` becomes optional rather
  than guessed.
- The door question speaks a compass side, never the survey's sentence.
- One hours question for every device at registration.
- Mobility is asked on the first help call, with the more careful answer of each pair; `bedbound` until then.
- "Needs help now" both opens a help request and flags the call for a person.
- Synthetic demo patients' contacts are not registrations; a reset command clears a phone for rehearsals.
- The registration goal is about two minutes: up to four record-chosen questions, each skipped when the record
  answers it. A walk-up above floor 1 gets no elevator question.
- The live elevator question sits on the impact call; the building call asks about power and the elevator only.
- Calais Midtown is the demo building.

## Left to the builder

- Template wording within the rules above; the interpreter prompt and new field names; address and apartment
  number normalization.
- Where the hosted API gets the unit lists: wherever it reads CoStar records today.
- How "Registered by phone", "Said by phone" and the building status look, within the existing design tokens.
- Tests: the script paths (full registration, no equipment, address not found, a correction at each read-back, the
  check call with known answers, an early hang-up before the records are written); each home-question row asked and
  skipped; apartment number matching; help, safe and details by phone, the mobility question, a live request, and
  keypad 1 never recording safe; tracker texts sent once each and never before Accept; the building call and its
  effect on `confirm_elevator`; the queue row and the fallback rule with the elevator out; a closed hotel left out
  of the search; one API round trip per new route. Interpreter eval cases for the new fields.
