# CoStar data use cases for Hearth

Reference for [spec v6](spec.md). The [CoStar workshop](../sponsor-notes/costar-workshop-notes.md) emphasized
combining data streams to reveal something a dispatcher can act on. Keep Beryl as the outage benchmark and use a
small Houston case set to test what the property data adds.

Reviewed 14 Nov. Nothing here is new build work for this weekend: the demo lead is the assisted move in
[#18](https://github.com/kevinyyin/hearth/pull/18), and the rest of this document is a reference for what the
sponsor layers can and cannot support.

| Use case | Data to combine | Insight and dispatch action |
| --- | --- | --- |
| **Check whether an assisted move is feasible end to end** | CoStar refuge inventory and scan links; Vexcel curb and approach; Matterport lobby or entrance scan. Confirm power, space, and current access separately. | A closer refuge can have a plausible drop-off and still have steps on the route from that stop. Show the evidence for the specific route and offer a feasible alternative for dispatcher review. [Access workflow proposal](https://github.com/kevinyyin/hearth/pull/18) |
| **Find the home where resupply will take longer than it looks** | CoStar stories and elevator or walk-up records; Vexcel vehicle stop and approach; Matterport access or unit-type layout where the scan covers the relevant segment; caller confirmation of floor and current elevator status. | Two households can have the same backup time and driving ETA, while only one leaves enough time to carry equipment to the door. Compare time to complete delivery with backup time remaining, and surface the case for earlier dispatch or another plan if the margin disappears. |
| **Prioritize welfare checks after a hurricane** | CoStar construction material, build year, and stories; Vexcel roof material, condition, and capture date; a separate storm exposure layer if available. | Among buildings with similar exposure, flag combinations that warrant a closer look. For example, an older building with poor observed roof condition and an unanswered check-in could get a manual review. Use explicit rules and show which evidence moved a case. Keep estimated building vulnerability separate from reported damage and individual urgency. |
| **Spot changes between aerial captures** | Dated Vexcel tiles of the same structure; CoStar property coordinates and building identifiers; a verified incident timeline. | A new obstruction or changed approach can flag a crew brief for review. An older tile may show an open drop-off that no longer exists in a newer capture. Show both dates and images. Treat the difference as a lead to verify, with no attribution to the hurricane based on the images alone. |

## What the toolkit supports

- The CoStar extract has year built, construction material, stories, and property coordinates where populated. These
  are building characteristics. Actual hurricane exposure and observed outcomes would need separate sources.
- Vexcel returned records from multiple Houston capture years in the toolkit probe, 2023 to 2026, and Hearth
  currently takes the latest. Check for dated captures of the same structure from before and after Beryl before
  promising a storm comparison. Check capture quality and alignment, and consider construction, seasonal change and
  occlusion as possible explanations for a difference.
- CoStar-linked Matterport apartment models often depict unit types. Use the scan only for the route segment it
  actually shows. Verify that aerial and interior evidence refer to the same entrance before joining them.

[Toolkit notes](toolkit-notes.md)

## What to build first

**Lead with the assisted move.** Spec v6 reports that almost all of the measured benefit comes from moving people,
so the curb-to-interior access decision in [#18](https://github.com/kevinyyin/hearth/pull/18) is the beat that
carries the CoStar and LangChain story. That proposal owns the demo slot and the layer comparison.

**Resupply feasibility is the second example.** It is the cheapest one to show, because the rule is already in the
code: delivery service time is `service_base_min` plus `service_min_per_floor_no_elevator` per floor whenever the
elevator is out or absent (`hearth/buildings/profile.py`, `service_minutes`), which is 10 minutes plus 4 minutes per
floor in `config/assumptions.yaml` today.

A worked example computed from that rule. Two synthetic patients, each with **25 minutes of backup left** and a
**12-minute drive**:

| | Floor | Elevator | Service time | Total | Against 25 min |
| --- | --- | --- | --- | --- | --- |
| Patient A | 3 | working | 10 min (base only) | 22 min | 3 minutes inside the cutoff |
| Patient B | 3 | out | 10 + 4 x 3 = 22 min | 34 min | 9 minutes past the cutoff |

Same device, same backup, same drive, same floor. The elevator status is the whole difference, and it is the one
field the CoStar extract cannot supply for a hotel and can only infer for an apartment building, so it has to come
from the resident or the caller. That is the decision rule; measure or label the inputs in the actual demo rather
than reusing these numbers as findings.

**The dated-imagery probe is after the weekend.** It needs a set of Houston properties with dated, comparable
captures spanning Beryl, and the data kit is not in this checkout to check for one. If someone with the kit finds a
clear before-and-after pair in under an hour, one side-by-side review is worth demoing; otherwise it waits.
Hurricane damage prediction is a separate research task that needs local hazard exposure, verified damage labels,
and a comparison against an exposure-only baseline on held-out buildings. Until then, describe it as screening for
review, not prediction.

## How to tell whether the data helped

Keep the patient, outage, resource limits, and candidate buildings fixed. Compare the decision using CoStar alone,
then add each other layer independently, then both together. Show the changed estimate or action, the source behind
it, and any remaining uncertainty. Use a confirmed example or a clearly labeled fixture.

Only one decision gets this treatment before Sunday morning, and [#18](https://github.com/kevinyyin/hearth/pull/18)
claims it for refuge eligibility for a single wheelchair user. The resupply margin above is the next candidate if
there is time, not a second parallel run.
