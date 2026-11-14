# Sponsor alignment proposal

Proposed demo and evaluation amendment to [spec v6](spec.md). It complements the
[outreach proposal](https://github.com/kevinyyin/hearth/pull/17) and builds on the home markup merged in
[#20](https://github.com/kevinyyin/hearth/pull/20). Reviewed 14 Nov; this revision names the candidates, connects
the resident's own markup to the decision, and cuts the comparison to one decision.

## Where the current spec falls short

| Sponsor signal | Current gap | Proposed change |
| --- | --- | --- |
| CoStar wants multiple data layers to yield an insight that changes what the user does. | The survey shows a sourced profile and estimates indoor heat. Spec v6 reports that building-specific heating changes the county result by under 0.2%. The larger gap is refuge inventory with unlimited capacity. | Hold the destination inventory fixed and show how physical access evidence changes a specific crew plan or refuge recommendation. |
| LangChain wants a realistic workflow that makes planning, delegation, files, and human review visible. | Hearth already has these pieces. The pitch lists them but gives little time to show how evidence moves between agents or what changes after a dispatcher intervenes. | Follow one request through plan, parallel evidence gathering, reconciliation, review, and revised proposal. Show why each step exists. |
| CoStar wants AI used directly by the person doing the work. | A profile and trace can look like a separate technical demo. | Put the recommendation and its evidence on the dispatcher's review card. Open the imagery and scan from the reason they support. |

## One post-Beryl dispatch decision

A synthetic resident reports low backup power for their oxygen concentrator during the post-hurricane outage. An
assisted move is under consideration. The dispatcher asks whether a crew can get the resident into a nearby powered
refuge with an available space and a route that meets their mobility needs.

1. **CoStar finds candidates and links the evidence.** Use property type, coordinates, stories, and model
   attachments to shortlist nearby refuges and retrieve the right Matterport models. Elevator fields are missing for
   every hotel in the kit, known for 0 of 54 Houston hotels ([toolkit notes](toolkit-notes.md)), so the destination
   floor and any required elevator's operating status are confirmed separately.
2. **Vexcel shows the approach.** Identify a plausible stop and the entrance it serves from the aerial tile. Show
   that segment to the dispatcher. Aerial imagery describes physical layout at capture time. Confirm current
   obstructions and road access separately.
3. **Matterport shows the path inside.** Use a lobby or entrance scan that matches the same approach. Look for an
   entrance threshold, stairs, or another barrier relevant to this resident. Apartment models in the kit are unit
   floor plans, not entrances, so an apartment scan leaves the entrance unverified; hotel lobby scans are the ones
   that show it.
4. **Join the segments into a dispatch recommendation.** The nearer candidate can look suitable in CoStar and have
   an apparent curbside drop-off, but the scan may reveal steps on that approach. Recommend a farther candidate only
   when its route fits and power and space have been confirmed in the scenario. If the approach and the scan cannot
   be matched, flag the gap for review.

The insight is **whether a crew can complete the curb-to-interior trip for this resident**. Show the specific
barrier or alternate entrance that changes the plan. Current power, road conditions, and refuge capacity come from
dispatcher confirmation or explicit simulation inputs.

## The two Houston candidates

The sponsor data kit is not in this checkout, so this names the one candidate the repo already documents and gives
runnable criteria for the second. Ids only, no addresses, and no sponsor records in the repo.

**Candidate A, CoStar `1508702`.** A real Houston hotel, already surveyed live end to end in 61 seconds across all
three layers ([toolkit notes](toolkit-notes.md), live survey timings). That survey produced two conflicts, one of
them an elevator seen in some lobby views and not others, which is exactly the kind of unverified segment this beat
is meant to surface. Still to record before the demo: which model id and sweep shows the lobby, and what the aerial
tile shows for that same approach.

**Candidate B, selection criteria to run against the kit.** From the normalized Houston subset:

- `propertyType == 1` (hospitality) and `primaryAddress.researchMarketId == 14` (Houston). Hotels are the place to
  look because their Matterport `name` fields can list "Lobby"; apartment models list unit floor plans.
- At least one `attachments[]` entry with `videoExternalReferenceType` 36 or 234, and a model whose `name` contains
  "Lobby" or "Entrance".
- `numStoriesAboveGrade` greater than 1, so the elevator question is live rather than moot.
- Within a few kilometres of candidate A, so both are plausible destinations for the same request.
- An ortho tile at the property's `primaryAddress.latitude/longitude` where a vehicle stop and the entrance it
  serves are both legible.

Pick the pair so that **one has a usable route and one does not**. The beat only works if the nearer candidate fails
on a segment the scan reveals. If no pair in the kit does that, say so and demo a labeled fixture instead of
implying the data produced a result it did not.

## What the resident can tell us that the imagery cannot

The trip has two ends. The refuge imagery above covers the destination; [#20](https://github.com/kevinyyin/hearth/pull/20)
covers the origin, from the resident themself. A resident marks their own building on the aerial image with
`park`, `entrance`, `blocked` and numbered `route` pins, and marks `machine`, `blocked` and `route` pins inside a
scan they say is laid out like their home (`OutsidePin` and `InsidePin` in `hearth/contracts.py`, stored as the
`home` document). The responder card already shows those pins next to the crew access brief.

This matters for the access decision in three ways.

- **A `blocked` pin is a current condition, and no layer provides one.** Vexcel describes layout at capture time;
  Matterport describes a scan taken once. A resident saying the near approach is blocked today is the only live
  input in the stack. Treat it as evidence that overrides an aerial drop-off, and show it as the resident's
  statement rather than as a verified fact.
- **Outside and inside pins do not carry the same weight.** Outside pins sit on the resident's actual building, so
  they are about that building. Inside pins sit in a scan the resident chose as *similar* to their home, so they
  describe a layout, not that address. Use them for what the crew should expect to carry equipment through, never as
  verification of the real entrance.
- **The resident closes the loop the imagery leaves open.** Floor and current elevator status are the two fields the
  kit cannot supply for a hotel, and both are things a resident or caller can simply be asked.

## How Deep Agents should run the case

| Component | What it does in the demo | Why use it |
| --- | --- | --- |
| Planning | Turn the request into a checklist for candidate search, access evidence, reconciliation, and review. | The dispatcher can see which checks remain open. |
| Parallel subagents | Give separate workers the CoStar record, Vexcel approach, and Matterport interior. Each returns observations, source references, and missing fields. | Each source has different tools and failure modes. The coordinator can compare independent findings. |
| Filesystem | Show the coordinator reading the per-building findings and reusing them on the second proposal. Keep sponsor files local and label cached evidence. | The agent can reuse evidence without repeating image reads, and the dispatcher can inspect what the proposal relied on. |
| Deterministic checks and middleware | Classify each required segment as supported, blocked, or unverified. Check that evidence refers to the same property and entrance before proposing a route. Keep personal identifiers out of calls to property tools. | Review decisions follow explicit checks even when the vision model is confident. |
| Human approval interrupt and memory | Pause at the existing proposal interrupt. Show why the candidate was chosen and which inputs still need confirmation. Have the dispatcher reject the first proposal because the curb is blocked, and show the revised plan reusing the evidence. | The dispatcher can correct conditions the imagery could never establish. |

The deterministic check this table asks for already exists. `eligible()` in `hearth/buildings/refuge.py` is code,
not model output, and for a wheelchair or bedbound patient it returns eligible, a specific blocking reason, or the
explicit string `unverified access`, based on a step-free entrance and an elevator above one floor.

**One caveat to state in the demo.** A rejection reason is written to a single dispatcher memory file that every
later proposal reads (`refuge.py`, `MEMORY_FILE`), with no incident scoping, so a temporary blockage currently
sticks to the building for good. Scoping that restriction to the incident is a code change outside this PR; until it
lands, use a rejection reason that is genuinely a lasting building fact, or say plainly that the scoping is pending.

Every assisted move still requires dispatcher approval. A blocked or unverified required segment cannot be shown as
a verified route.

## Demo and acceptance

- Pre-survey the two candidates above. Confirm that CoStar links the correct property and that Vexcel and Matterport
  evidence cover the same entrance. Use a visible cache label for the two-minute pitch; a live survey takes 55 to 61
  seconds, longer than the beat allows. Bring the live survey to the sponsor walkthrough if timing permits.
- **One decision gets the four-way layer run: refuge eligibility for a single wheelchair user.** Feed `eligible()`
  with CoStar only, with each added layer independently, and with both. Keep candidate inventory, requested
  mobility, power, and available spaces fixed, and record the recommendation, the evidence gap, and which action
  changed. One decision and one patient is what fits before Sunday morning; today a per-layer comparison exists only
  for hours-until-unsafe, so this is new work either way. If neither added layer changes the outcome, report that
  rather than trying patients until one does.
- Test one missing-scan or conflicting-entrance case and one dispatcher rejection. The first should surface an
  unverified route. The second should change the next proposal without repeating unchanged evidence calls.
- Keep the existing county replay as context. Report the decision difference and the evidence behind it. Claim an
  accuracy improvement only after the planned hand-labeled check.

References: [CoStar workshop](../sponsor-notes/costar-workshop-notes.md),
[LangChain workshop](../sponsor-notes/langchain-workshop-notes.md), [toolkit coverage](toolkit-notes.md), and
[spec v6](spec.md).
