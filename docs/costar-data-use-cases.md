# CoStar data use cases for Hearth

Proposal for [spec v6](spec.md). The [CoStar workshop](../sponsor-notes/costar-workshop-notes.md) emphasized combining data streams to reveal something a dispatcher can act on. Keep Beryl as the outage benchmark and use a small Houston case set to test what the property data adds.

| Use case | Data to combine | Insight and dispatch action |
| --- | --- | --- |
| **Prioritize welfare checks after a hurricane** | CoStar construction material, build year, and stories; Vexcel roof material, condition, and capture date; a separate storm exposure layer if available. | Among buildings with similar exposure, flag combinations that warrant a closer look. For example, an older building with poor observed roof condition and an unanswered check-in could get a manual review. Use explicit rules and show which evidence moved a case. Keep estimated building vulnerability separate from reported damage and individual urgency. |
| **Spot changes between aerial captures** | Dated Vexcel tiles of the same structure; CoStar property coordinates and building identifiers; a verified incident timeline. | A new obstruction or changed approach can flag a crew brief for review. An older tile may show an open drop-off that no longer exists in a newer capture. Show both dates and images. Treat the difference as a lead to verify, with no attribution to the hurricane based on the images alone. |
| **Find the home where resupply will take longer than it looks** | CoStar stories and elevator or walk-up records; Vexcel vehicle stop and approach; Matterport access or unit-type layout where the scan covers the relevant segment; caller confirmation of floor and current elevator status. | Two households can have the same backup time and driving ETA, while only one leaves enough time to carry equipment to the door. Compare time to complete delivery with backup time remaining, and surface the case for earlier dispatch or another plan if the margin disappears. |
| **Check whether an assisted move is feasible end to end** | CoStar refuge inventory and scan links; Vexcel curb and approach; Matterport lobby or entrance scan. Confirm power, space, and current access separately. | A closer refuge can have a plausible drop-off and still have steps on the route from that stop. Show the evidence for the specific route and offer a feasible alternative for dispatcher review. [Access workflow proposal](https://github.com/kevinyyin/hearth/pull/18) |

## What the toolkit supports

- The CoStar extract has year built, construction material, stories, and property coordinates where populated. These are building characteristics. Actual hurricane exposure and observed outcomes would need separate sources.
- Vexcel returned records from multiple Houston capture years in the toolkit probe. Hearth currently picks the latest. Check for dated captures of the same structure from before and after Beryl before promising a storm comparison. Check capture quality and alignment and consider construction, seasonal change, and occlusion as possible explanations for a difference.
- CoStar-linked Matterport apartment models often depict unit types. Use the scan only for the route segment it actually shows. Verify that aerial and interior evidence refer to the same entrance before joining them.

[Toolkit notes](toolkit-notes.md)

## What to build first

**Lead with resupply feasibility.** Show two synthetic patients with the same time left on backup and comparable driving ETAs. Use evidence from two or more sponsor layers to explain why the delivery plan differs. In a worked example, a crew has 25 minutes before the backup runs out. The drive is 12 minutes. A confirmed walk-up and a longer carry from the vehicle add 16 minutes, putting the delivery three minutes past the cutoff. Those numbers illustrate the decision rule. Measure or label the inputs in the actual demo.

**Probe the dated imagery in parallel.** Find a small set of Houston properties with dated, comparable captures. If there is a clear change across a relevant window, demo one before-and-after review with the images side by side. Hurricane damage prediction is a separate research task. It needs local hazard exposure, verified damage labels, and a comparison against an exposure-only baseline on held-out buildings. Until then, describe it as screening for review.

## How to tell whether the data helped

Keep the patient, outage, resource limits, and candidate buildings fixed. Compare the decision using CoStar alone, then add each other layer independently, then both together. Show the changed estimate or action, the source behind it, and any remaining uncertainty. Use a confirmed example or clearly labeled fixture. For the two-minute demo, prepare the source views in advance and label cached evidence.
