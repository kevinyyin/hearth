# Staging lots on the dispatch page (short design)

14 Nov 2026. Status: approved by the user on 14 Nov; the last three sentences of the API paragraph were added while planning.

## Why

CoStar judges pointed out that the data kit also carries lot and parking data. Hearth reads none of it today. The
CoStar track is the first priority, so the two-minute demo should show that data changing something a dispatcher
does. Crews need somewhere real to stage vans and supplies near an outage; today the only "depots" are made-up
coordinates in `config/assumptions.yaml`.

## Goals

- The dispatch page proposes a real parking lot to stage crews at, with the CoStar evidence and a Vexcel aerial of
  the lot next to it, and the dispatcher approves it.
- The approved lot is shown to the dispatcher and to crews.

## Non-goals

- No change to the simulation, the planner, `planner.depots`, or the Beryl sweep numbers.
- No new agent. The refuge agent stays the deepagents example; this is a rule in code plus one vision read.
- No use of amenities (the kit has ids without a lookup table), land records (2 in Houston) or renovation history.

## Anti-goals

- Claiming a lot is available. CoStar says how big it is, not whether the owner agrees or the lot is clear. Every
  option carries "needs a call: owner permission; lot not verified clear".
- Proposing apartment lots. They are residents' parking.

## What the data supports (Houston, 1,741 existing properties)

- Lot size on 1,752 of 1,758 records, parking type on 1,519, space counts on 1,247.
- Non-apartment properties with a surface lot: 131 have 100 or more surface spaces, 27 have 300 or more. Coverage is
  thin in the southeast. The kit is CoStar's Matterport list, not a census of Houston lots.
- A Vexcel tile 300 m across, centred on the CoStar point, shows the building and its lot with the capture date
  (checked on CoStar 1383155, a Target with 611 surface spaces on 9.5 acres, capture 01/2026).

## Approaches considered

1. **Dispatch card (chosen).** Shortlist in code, aerial per option, dispatcher approves. Visible in the demo and
   touches nothing the planner work is changing.
2. **Config swap.** Replace the three synthetic depots with real lots. Cheapest, but on screen it is only a label, and
   the sweep needs a re-run.
3. **Planner chooses lots.** Lots picked to minimise crew travel and moved as the outage shifts. Most interesting, but
   it rewrites `hearth/sim/engine.py`, which has uncommitted planner changes, and invalidates the sweep.

Chosen by the user on 14 Nov: approach 1, because it is the only one the judges would see.

## Design

**Data.** `normalize_costar` gains two fields: `surface_spaces` (sum of `parking[].totalSpaces` where `parkingType`
is 1, Surface) and `lot_acres` (`lotSize`, converted from square feet when `lotSizeMeasurementType` is 1). The cached
index name is bumped to `houston_v4.json` and uploaded to the private bucket for the hosted API.

**Rule (code, not a model).** A candidate is an existing property that is not multifamily or senior housing, has at
least 100 surface spaces (a number in `config/assumptions.yaml`), and whose ZIP is not dark. Dark ZIPs are the ZIPs
of residents with an open help request, the same convention the refuge check uses. Candidates are ranked by distance
to the centre of the open requests; with no open request, to the centre of registered homes. The top 3 are returned.

**Evidence per option.** Name and address, property type, surface spaces, lot acres, distance, all labelled CoStar.
A Vexcel tile 300 m across, cached per building under its own file name so the 80 m building tile is untouched. One
vision read of that tile, cached, answering where the open lot is and how a van gets in from the road, shown as one
line labelled as a model's reading. If Vexcel has no tile, the option still shows with "no aerial".

**API.** `GET /api/staging` returns the approved lot, if any, and the current options. `POST /api/staging` with a
building id records the dispatcher's choice in the store, and with no building id clears it. `GET
/api/buildings/{id}/lot-image` serves the tile and `GET /api/buildings/{id}/lot-reading` the model's line, read only
for the option on show. An approved lot whose ZIP later gets an open request stays chosen and is flagged for the
dispatcher.

**Screens.**

```
Staging lot · proposed
Target · retail · 4323 San Felipe St · 3.1 km from open requests
CoStar: 611 surface spaces · 9.5 acres · existing
[aerial tile, Vexcel capture 01/2026]
Model reading: open lot north of the store, entered from San Felipe St
Needs a call: owner permission; lot not verified clear
[Approve]  [Next option]
```

After approval the card reads "Staging at Target, 4323 San Felipe St (not confirmed with the owner)" with a Change
link. The crew's job page shows the same line. "Next option" cycles through the 3 options locally and stores nothing.

## Left to the builder

- Component layout, and whether the card reuses `ProposalCard` or is its own small component (my call: its own; the
  refuge card posts to a different endpoint and requires a rejection reason).
- The exact vision question.
- One test for the candidate rule (apartments excluded, dark ZIP excluded, order by distance) and one for the
  `normalize_costar` fields.

## My calls, not the user's

- Threshold of 100 surface spaces.
- Dark area taken from open requests' ZIPs.
- Approval only records and displays the lot; it does not change which crew gets a job.
- No rejection reason and no agent memory for staging lots.
