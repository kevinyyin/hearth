# Simulation notes (lane S)

Patients are synthetic. Every number the simulation uses is in `config/assumptions.yaml`; each run copies it next
to its results. These notes record where the inputs come from and every place the data was corrected.

## Inputs

`uv run python scripts/fetch_data.py --scenario beryl_2024` downloads to `data/raw/` (git-ignored, SHA-256 sums in
`data/raw/SHA256SUMS`) and writes row extracts (our county and window only, values unchanged) to `data/processed/`.
The extracts are small public data and are committed, so tests and the demo run offline.

| Input | Source | Extract |
|---|---|---|
| Patients per ZIP | HHS emPOWER 2024 historical dataset (`2024_HHSemPOWERMapHistoricalDataset.xlsx`), sheet "Zip Code", columns `Jul_2024_Power_Dependent_Devices_DME`, `Jul_2024_O2_Services_Any_DME`, rows with `FIPS_Code` 48201 | `empower_beryl_2024.csv` (132 ZIPs, total 23,281; county sheet also says 23,281) |
| Outages | EAGLE-I recorded outages (ORNL), figshare article 24237376, `eaglei_outages_2024.csv`, fetched by HTTP Range for FIPS 48201 only (the file is sorted by FIPS) | `eaglei_beryl_2024.csv` (Jul 8 to Jul 19, 15-minute rows) |
| Customer total | same article, `MCC.csv`: 1,827,686 for 48201 (the outage file's `total_customers` is not used) | checked against `config/scenarios/beryl_2024.yaml` |
| Weather | Iowa Environmental Mesonet ASOS, station IAH, `tmpf` and `relh`, routine hourly METARs (`report_type=3`), UTC | `weather_beryl_2024.csv` |
| Home placement | Census TIGERweb, 2020 ZCTA layer, generalized to about 50 m (`maxAllowableOffset=0.0005`) | `zcta_beryl_2024.geojson` (all 132 ZIPs have a polygon) |

The xlsx is read with the standard library (`zipfile` plus XML), so no spreadsheet dependency was added.

## EAGLE-I facts used

From Brelsford et al., "A dataset of recorded electricity outages by United States county 2014-2022", Scientific
Data, 2024: all times are UTC; `run_start_time` marks the start of the collection run; rows with zero customers out
are omitted, so a missing row is either zero or a collection gap and the dataset does not say which.

## Corrections to the Beryl outage curve

Every replaced interval is listed in `fraction_out(...).attrs["corrected"]` (58 intervals for Beryl).

1. **Late onset.** The utility's outage map read near zero (98 to 925 customers) from landfall (Jul 8 09:00 UTC) until
   14:15 UTC, then jumped to 1,247,430. We replace those readings with a straight ramp from landfall to the first
   reading above `outage.onset_fraction` (5%) of customers.
2. **False dip.** Jul 8 15:45 to 19:00 UTC drops from 1.42 million to 0.80 million, then returns to 1.66 million.
   Replaced by interpolation.
3. **Near-zero readings.** Runs of 2,300 to 3,200 customers between readings above 1 million (Jul 9 15:30, Jul 10
   00:45 to 05:30). Replaced by interpolation.

Rule for 2 and 3 (and a few small-count wobbles on Jul 17 and 18, about 1% of customers): inside the cleaning window,
a reading below `outage.dip_ratio` (0.75) times the smaller of the highest reading in the previous and the next
`outage.dip_window_h` (6 h) is a glitch. The plan's rule (below 10% of the mean of neighbors one hour either side)
missed multi-interval runs and the dip, so it was widened; both numbers are in config and unconfirmed. Readings above
the customer total are clipped. Gaps after landfall are interpolated, not treated as restoration.

Which patients are dark: each patient draws `r` once by seed and is dark while `r < f(t)`, so the curve's share of
patients is dark at every tick, the same people stay dark as the curve falls, and nobody's power returns for one
interval because of a glitch. Darkness is not geographic (no ZIP-level outage data is used).

## Synthetic attributes

Device type by ZIP is not public. Oxygen per ZIP is the emPOWER oxygen count capped at the ZIP total; the rest split
by `population.non_oxygen_mix`. Counts published as 11 mean "1 to 11" and are drawn uniformly by seed. Backup hours,
mobility, heat or cold sensitivity, supplier, phone and profile status are drawn from `population.*` (most are our
placeholders, `confirmed: false`). No patient has a phone number. Homes are uniform random points inside the ZIP's
polygon. A building resident (`population.costar_building_share`) moves into the nearest surveyed CoStar building
within `population.building_match_km` (at most `population.patients_per_building` each), so a run uses that
building's profile; with no surveyed buildings everybody uses the default time constants.

## Engine (Task S3)

Half-hour ticks over the scenario window. Per tick, for every patient (numpy arrays): power from the curve, backup
drain, indoor temperature (true building time constants), hours at risk (`hearth.metrics.at_risk`), then plan states
and crew assignment. The world is identical under every policy; policies differ in what they know and do:

- **p0, manual phone tree**: staff call the list in a seeded order at `phone_tree.staff` x `calls_per_staff_hour`;
  `phone_tree.unreachable_rate` of calls fail and go to a welfare-check queue; reached patients ask their supplier
  for a delivery when backup falls below `decision.low_backup_h`, first come first served; nobody is moved.
- **p3, Hearth**: dark patients with a verified phone are known at once; each tick `hearth.decision` rules run with
  a rolling `sim.horizon_h` (no restoration foresight) and an indoor forecast over the next 12 h of observed weather;
  hysteresis as in the spec. Unverified patients are UNREACHABLE until a crew checks (silence is never safe).
  Crews go to the highest risk weight per hour left (welfare checks assume `decision.low_backup_h` left).
- **Crews** belong to suppliers (split by `population.supplier_shares`), start at synthetic depots, and deliver only
  for their own supplier unless mutual aid. A delivery adds `planner.delivery_backup_h`. A ride ends at the nearest
  hospital or shelter in `planner.destinations` (plus surveyed hotels and senior housing when buildings are on). A
  dispatcher's approval of each move is assumed in the simulation; the live app requires it.
- **`--no-buildings`** gives the planner default time constants and no refuge buildings; the world keeps the true
  ones. Building time constants come from surveyed profiles in the store (`HEARTH_DB`), else config defaults.

## Sweep and replay (Task S4)

`uv run python -m hearth.sim sweep --scenario beryl_2024 --crews 5,10,20,40,80 --seeds 10` (250 runs, about 2.5 min
on 10 cores) writes `results/sweep_beryl_2024.json` and `results/sweep_beryl_2024.assumptions.yaml`. It ran with an
empty profile store, so **`p3__nobld` equals `p3`**: no synthetic home sits in a surveyed building yet. The store in
the main checkout holds hand-made fixtures (B-SAMPLE, H-*) that must not feed published results. Rerun the sweep
after real season-sweep profiles are in the store to see a building effect (expect it to be small: a few residents
per surveyed building).

`results/case_jarrett__p3__c20__s1/` replays one documented case (Spring, TX, July 2024; sources in
`config/scenarios/case_jarrett.yaml`) with a synthetic stand-in patient, labeled "replay of a documented case;
outcome under Hearth is simulated". The home cooled to 22-26 C during the storm day, so OWN_BACKUP was right then;
on day 2 the forecast turned unsafe and the patient was moved, two days before the documented date. The replay gives
this one patient all 20 crews, so it is optimistic; the county run shows the contention.

Regenerate the map's county run (about 7 s, about 350 MB, git-ignored) and the patients file the API reads:
`uv run python -m hearth.sim run --scenario beryl_2024 --policy p3 --seed 1 --crews 20`.
