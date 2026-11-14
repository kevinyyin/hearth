# Hearth scope update for review

Proposed amendment to [spec v6](spec.md).

## Product scope

Hearth helps a county dispatcher decide what each household needs during a prolonged power outage. The options are to stay in place with adequate backup, get supplies delivered, receive a welfare check, or request an assisted move to a powered, accessible refuge. A dispatcher approves each move, and the resident is asked for consent. Incident command sets evacuation and shelter instructions.

## Who can get help

- **Send an area-wide check-in.** An agency-authorized text or alert asks households in the affected area whether they need help staying safe where they are or getting somewhere safe. It gives them a way to request help.
- **Prioritize individual calls for known high-risk households.** Start with the powered medical-device registry and other known high-risk households. Hearth checks backup power where relevant, indoor conditions, and what support the household needs. Unanswered outreach remains unresolved.
- **Inbound intake is open to anyone in the affected area.** Someone without a powered device can still need help, for example if their home is dangerously hot and they cannot get downstairs on their own. Ask whether they can safely stay, what help they need, and what would make a move feasible.
- **Requests share the appropriate queue.** If a registered resident and an inbound caller both need an assisted move, their requests compete for the same eligible transport and refuge capacity. Triage uses urgency, time remaining, and what crews and destinations can actually handle. Registry membership determines proactive outreach, while the request determines dispatch eligibility.
- **Follow official evacuation instructions.** If officials order an evacuation, ask whether everyone in the household can leave safely or needs assistance. Standard Response used zone-wide calls to identify ride requests during wildfire evacuations. Hearth uses a broad check-in and targeted calls to identify a wider range of needs during a prolonged outage. [Standard Response](https://devpost.com/software/standard-response)

## Scenarios

| Scenario | Weekend scope |
| --- | --- |
| Hurricane Beryl, Harris County | Primary benchmark. Replay the post-storm outage and heat for synthetic residents still at home. |
| Texas freeze and prolonged outage | Optional illustrative case. Show cold and backup power changing the plan. A historical freeze benchmark needs better outage inputs. |
| Active flood, wildfire, or missile strike | Outside the weekend build. Use official shelter or evacuation instructions and incident-command routing. A later post-incident outage case could use Hearth once responders have cleared the area for operations. |

## Demo and evaluation

- **Demo a targeted call and an area-wide check-in.** Show one registry call and one off-registry caller responding to a simulated check-in. Show the caller's assisted-move request entering the shared transport queue and receiving a proposal for dispatcher review. Show how building evidence changes which destination is feasible or how long a pickup takes.
- **Keep the existing Beryl results scoped to the synthetic registry cohort.** Measuring countywide demand requires modeling how many requests the check-in and open intake generate and how those requests compete for capacity.
- **Proposed simulation change.** Model supplier delivery, assisted transport, and welfare checks with explicit crew capabilities. Give refuges finite capacity. Represent competing emergency demand by varying the share of shared crews and refuge space available to Hearth. Keep these limits equal across policy comparisons and report missed deadlines and unserved requests alongside patient-hours at risk.
- **Current result limits.** The v6 replay uses a common crew pool for Hearth jobs, has no competing public demand, and gives refuges unlimited capacity. Keep those assumptions attached to the current results until a constrained replay is available.
