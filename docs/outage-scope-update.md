# Hearth scope update for review

Proposed amendment to [spec v6](spec.md). Reviewed 14 Nov; this revision keeps the resource limits for the
weekend build and moves the new outreach channels to [Later](#later).

## Product scope

Hearth helps a county dispatcher decide what each household needs during a prolonged power outage. The options are
to stay in place with adequate backup, get supplies delivered, receive a welfare check, or request an assisted move
to a powered, accessible refuge. A dispatcher approves each move, and the resident is asked for consent. Incident
command sets evacuation and shelter instructions.

## One request queue with two sources

There is one queue of requests, not a second intake path. A request reaches it either because Hearth called the
household or because the household asked for help itself. Registry membership decides who gets a proactive call;
the request decides dispatch eligibility.

- **Proactive calls** go to the powered medical-device registry first: how much backup power is left, and what the
  household needs. Other known high-risk households can be called the same way. Unanswered outreach stays
  unresolved rather than counting as "no need".
- **Resident-raised requests** come from the resident page merged in [#20](https://github.com/kevinyyin/hearth/pull/20).
  That slice carries the device answers and the home markup; the "I need help / I'm safe" loop is the slice after it
  and is where a resident-raised request is actually created.
- **Both sources compete for the same crews and refuge spaces.** Triage uses urgency, time remaining, and what the
  available crews and destinations can handle. A resident-raised request does not jump the registry, and registry
  membership does not reserve capacity.

`Job` in `hearth/contracts.py` already carries the three kinds this queue needs — `delivery`, `ride`,
`welfare_check` — so the queue is a triage and capacity change, not a new record type. `Job.patient_id` is
currently required, which is the one field that has to give before a request from outside the registry can enter
the same queue.

- **Follow official evacuation instructions.** If officials order an evacuation, ask whether everyone in the
  household can leave safely or needs assistance. Hearth's own contribution is the prolonged-outage case: a broad
  check-in plus targeted calls, to surface needs that an evacuation order does not ask about.

## Scenarios

| Scenario | Weekend scope |
| --- | --- |
| Hurricane Beryl, Harris County | Primary benchmark. Replay the prolonged post-hurricane outage for synthetic residents still at home. The demo leads with medical-device backup running low. Indoor heat remains a scenario input. |
| Texas freeze and prolonged outage | Optional illustrative case. Show a household that has lost power and heat asking for help getting somewhere warm. A historical freeze benchmark needs better outage inputs. |
| Active flood, wildfire, or missile strike | Outside the weekend build. Use official shelter or evacuation instructions and incident-command routing. A later post-incident outage case could use Hearth once responders have cleared the area for operations. |

## Proposed simulation change

This is the part of the proposal meant for this weekend. All three items match what spec v6 already lists as
unfinished, and none of them exists in the code today — there is no capacity field anywhere in `hearth/`.

1. **Give refuges finite capacity.** The v6 replay treats every refuge as unlimited, which is the largest single
   flatterer in the current results.
2. **Report unserved requests and missed deadlines** alongside patient-hours at risk, so the cost of running out of
   capacity is visible rather than absorbed.
3. **Model the crew side explicitly:** supplier delivery, assisted transport and welfare checks with the
   capabilities each needs. Represent competing emergency demand by varying the share of crews and refuge space
   available to Hearth.

Keep these limits identical across policy comparisons, or the comparison stops meaning anything.

**Current result limits.** The v6 replay uses a common crew pool for Hearth jobs, has no competing public demand,
and gives refuges unlimited capacity. Keep those three sentences attached to the published results until a
constrained replay exists.

## Demo

No new beats. The 2-minute run in spec v6 stays as written; this proposal changes what one existing beat shows and
adds nothing to the clock.

- **In the 1:00–1:25 beat**, where a refuge is already proposed and approved, show the queue the request sits in and
  one other request competing for the same space. The point to land is that capacity is finite and the dispatcher is
  choosing.
- **In the 1:25–1:50 chart beat**, if the constrained replay lands, the unserved-request count is the honest number
  to say out loud next to patient-hours at risk.
- **Sponsor walkthroughs** are separate and longer, per spec v6. The proactive call and a resident-raised request
  side by side belong there, not in the 2-minute run.

## Later

Both of these are new work, not scope clarifications, and neither is available this weekend.

- **An open hotline for unfamiliar numbers.** Today an inbound call from a number Hearth cannot match is handed to a
  person: `hearth/messaging/voice.py` renders `human_handoff` and ends the call rather than looping. Taking a
  request from an unrecognized caller means new voice work — confirming location and callback number, then creating
  a request for review.
- **The area-wide check-in text.** US SMS needs a carrier registration that takes days (spec v6, the Twilio row), so
  there is no way to send this for real this weekend. Wherever the check-in appears in a demo or a screenshot it is
  **simulated**, and should be labeled that way.

Measuring countywide demand stays out of scope either way: it needs a model of how many requests a broad check-in
generates and how those requests compete for capacity. The published Beryl results stay scoped to the synthetic
registry cohort.
