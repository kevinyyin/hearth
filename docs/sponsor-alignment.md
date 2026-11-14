# Sponsor alignment proposal

Proposed demo and evaluation amendment to [spec v6](spec.md). It complements the [outreach proposal](https://github.com/kevinyyin/hearth/pull/17).

## Where the current spec falls short

| Sponsor signal | Current gap | Proposed change |
| --- | --- | --- |
| CoStar wants multiple data layers to yield an insight that changes what the user does. | The survey shows a sourced profile and estimates indoor heat. Spec v6 reports that building-specific heating changes the county result by under 0.2%. The larger gap includes adding refuge inventory with unlimited capacity. | Hold the destination inventory fixed and show how physical access evidence changes a specific crew plan or refuge recommendation. |
| LangChain wants a realistic workflow that makes planning, delegation, files, and human review visible. | Hearth already has these pieces. The pitch lists them but gives little time to show how evidence moves between agents or what changes after a dispatcher intervenes. | Follow one request through plan, parallel evidence gathering, reconciliation, review, and revised proposal. Show why each step exists. |
| CoStar wants AI used directly by the person doing the work. | A profile and trace can look like a separate technical demo. | Put the recommendation and its evidence on the dispatcher’s review card. Open the imagery and scan from the reason they support. |

## One post-Beryl dispatch decision

A synthetic resident reports low backup power for their oxygen concentrator during the post-hurricane outage. An assisted move is under consideration. The dispatcher asks whether a crew can get the resident into a nearby powered refuge with an available space and a route that meets their mobility needs.

1. **CoStar finds candidates and links the evidence.** Use property type, coordinates, stories, and model attachments to shortlist nearby refuges and retrieve the right Matterport models. Elevator fields are missing for hotels in the kit. Confirm the destination floor and any required elevator’s operating status separately.
2. **Vexcel shows the approach.** Identify a plausible stop and the entrance it serves from the aerial tile. Show that segment to the dispatcher. Aerial imagery describes physical layout at capture time. Confirm current obstructions and road access separately.
3. **Matterport shows the path inside.** Use a lobby or entrance scan that matches the same approach. Look for an entrance threshold, stairs, or another barrier relevant to this resident. A unit-type scan can describe its interior. The entrance stays unverified if the scan only shows a unit.
4. **Join the segments into a dispatch recommendation.** The nearer candidate can look suitable in CoStar and have an apparent curbside drop-off, but the scan may reveal steps on that approach. Recommend a farther candidate only when its route fits and power and space have been confirmed in the scenario. If the approach and the scan cannot be matched, flag the gap for review. Show a labeled fixture if the team cannot corroborate this example on real sponsor data.

The insight is **whether a crew can complete the curb-to-interior trip for this resident**. Show the specific barrier or alternate entrance that changes the plan. Current power, road conditions, and refuge capacity come from dispatcher confirmation or explicit simulation inputs.

## How Deep Agents should run the case

| Component | What it does in the demo | Why use it |
| --- | --- | --- |
| Planning | Turn the request into a checklist for candidate search, access evidence, reconciliation, and review. | The dispatcher can see which checks remain open. |
| Parallel subagents | Give separate workers the CoStar record, Vexcel approach, and Matterport interior. Each returns observations, source references, and missing fields. | Each source has different tools and failure modes. The coordinator can compare independent findings. |
| Filesystem | Show the coordinator reading the per-building findings and reusing them on the second proposal. Keep sponsor files local and label cached evidence. | The agent can reuse evidence without repeating image reads, and the dispatcher can inspect what the proposal relied on. |
| Deterministic checks and middleware | Classify each required segment as supported, blocked, or unverified. Check that evidence refers to the same property and entrance before proposing a route. Keep personal identifiers out of calls to property tools. | Review decisions follow explicit checks even when the vision model is confident. |
| Human approval interrupt and memory | Pause at the existing proposal interrupt. Show why the candidate was chosen and which inputs still need confirmation. Have the dispatcher reject the first proposal because the curb is blocked, record the reason as a case-specific operational restriction, and show the revised plan reusing the evidence. | The dispatcher can correct conditions the imagery could never establish. Scope the restriction to the incident so a temporary blockage does not persist as a building fact. |

Every assisted move still requires dispatcher approval. A blocked or unverified required segment cannot be shown as a verified route.

## Demo and acceptance

- Pre-survey two Houston candidates. Confirm that CoStar links the correct property and that Vexcel and Matterport evidence cover the same entrance. Use a visible cache label for the two-minute pitch. Bring the live survey to the sponsor walkthrough if timing permits.
- Run the same request with CoStar only, with each added layer independently, and with both added. Keep candidate inventory, requested mobility, power, and available spaces fixed. Record the recommendation, the evidence gap, and which action changed. If either added layer makes no difference in the chosen case, report that and choose a better example for the combined-data demo.
- Test one missing-scan or conflicting-entrance case and one dispatcher rejection. The first should surface an unverified route. The second should change the next proposal without repeating unchanged evidence calls.
- Keep the existing county replay as context. Report the decision difference and the evidence behind it. Claim an accuracy improvement only after the planned hand-labeled check.

References: [CoStar workshop](../sponsor-notes/costar-workshop-notes.md), [LangChain workshop](../sponsor-notes/langchain-workshop-notes.md), [toolkit coverage](toolkit-notes.md), and [spec v6](spec.md).
