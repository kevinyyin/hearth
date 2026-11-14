# Hearth scope update for review

Proposed amendment to [spec v6](spec.md).

## Product scope

Hearth helps a county dispatcher decide what each household needs during a prolonged power outage. The options are to stay in place with adequate backup, get supplies delivered, receive a welfare check, or request an assisted move to a powered, accessible refuge. A dispatcher approves each move, and the resident is asked for consent. Incident command sets evacuation and shelter instructions.

## Outreach and intake

1. **Send the area-wide check-in first.** An agency-authorized text or alert asks households in the affected area whether they need help staying safe or getting somewhere safe. It includes a public Hearth hotline number.
2. **Call people on the powered medical-device registry next.** Check how much backup power remains and what support the household needs. Other known high-risk households can also receive targeted calls. Unanswered outreach remains unresolved.
3. **Accept inbound calls from anyone affected.** The hotline is open from the moment the check-in goes out. It accepts callers from unfamiliar numbers, confirms their location and callback number, asks what help they need, and creates a request for dispatcher review.

- **Requests share the appropriate queue.** If a registered resident and an inbound caller both need an assisted move, their requests compete for the same eligible transport and refuge capacity. Triage uses urgency, time remaining, and what crews and destinations can actually handle. Registry membership determines proactive outreach, while the request determines dispatch eligibility.
- **Follow official evacuation instructions.** If officials order an evacuation, ask whether everyone in the household can leave safely or needs assistance. Standard Response used zone-wide calls to identify ride requests during wildfire evacuations. Hearth uses a broad check-in and targeted calls to identify a wider range of needs during a prolonged outage. [Standard Response](https://devpost.com/software/standard-response)

## Scenarios

| Scenario | Weekend scope |
| --- | --- |
| Hurricane Beryl, Harris County | Primary benchmark. Replay the prolonged post-hurricane outage for synthetic residents still at home. The demo leads with medical-device backup running low. Indoor heat remains a scenario input. |
| Texas freeze and prolonged outage | Optional illustrative case. Show a household that has lost power and heat asking for help getting somewhere warm. A historical freeze benchmark needs better outage inputs. |
| Active flood, wildfire, or missile strike | Outside the weekend build. Use official shelter or evacuation instructions and incident-command routing. A later post-incident outage case could use Hearth once responders have cleared the area for operations. |

## Demo and evaluation

- **Demo the post-Beryl flow.** Start with a simulated area-wide check-in. Then show a registry call with a resident whose oxygen concentrator battery is running low. Show an off-registry caller whose caregiver cannot reach them requesting a welfare check. Put both requests in the dispatcher view and show how building evidence helps the assigned crew reach the resident.
- **Use the browser phone for the demo.** Demonstrate an inbound call from an unrecognized number once that intake path is implemented. A live hotline requires a public phone number connected to the voice agent.
- **Keep the existing Beryl results scoped to the synthetic registry cohort.** Measuring countywide demand requires modeling how many requests the check-in and open intake generate and how those requests compete for capacity.
- **Proposed simulation change.** Model supplier delivery, assisted transport, and welfare checks with explicit crew capabilities. Give refuges finite capacity. Represent competing emergency demand by varying the share of shared crews and refuge space available to Hearth. Keep these limits equal across policy comparisons and report missed deadlines and unserved requests alongside patient-hours at risk.
- **Current result limits.** The v6 replay uses a common crew pool for Hearth jobs, has no competing public demand, and gives refuges unlimited capacity. Keep those assumptions attached to the current results until a constrained replay is available.
