# Central planner: one optimizer for who goes where

Date: 2026-11-14. Status: design, awaiting approval. Deadline: Sunday 2026-11-15, 8:00 AM ET.

## Intent

Today three separate pieces of code decide which crew goes to which person, and each one is greedy: the most urgent
need takes the nearest free crew, one job at a time, with no look-ahead. The user wants one central planner that looks
at every known need and every crew together and builds the plan that gets people help in the least time, with the
existing pieces (urgency rules, crew-fit rules, refuge choice, building minutes, stock) feeding into it instead of each
deciding on its own. The reference point the user gave is a Cal Hacks project that used an ALNS search.

## Goals

1. One planning function that the Beryl replay, the `/simulation` page and the live help loop all call.
2. Two layers inside it, each measurable on its own:
   - **Pairing**: the free crews and the open needs are matched jointly and exactly, instead of nearest-first.
   - **Route search (ALNS)**: each crew gets a route of several jobs over a look-ahead window, improved by repeatedly
     removing some jobs and reinserting them better.
3. The results chart gains two lines beside the existing five, so the gain of each layer is visible.
4. The Hearth side of `/simulation` draws routes planned by the Python planner.

## Non-goals

- Road networks or real travel times. Travel stays straight-line distance times the detour factor.
- Changing who needs what. `decide_vec`, `allot_deliveries`, the refuge access rule and the crew-fit rule stay as they
  are and remain the planner's inputs.
- Optimizing the phone-tree policy (`p0`) or the "today" side of `/simulation`. Those are the baselines.
- A learned policy, an external solver, or a claim of optimality.
- Sending vans ahead of a need on `/simulation` (see "Calls made in this design").

## Anti-goals (these make it a failure even if it runs)

- **Any existing published number changes.** The current 25 sweep rows must reproduce exactly. The greedy path stays
  the default and stays byte-identical.
- **Results that cannot be reproduced.** The search uses a fixed number of iterations and a seeded random stream, never
  a wall-clock budget.
- **Shipping an "optimized" line that is worse than greedy without saying so.** See "If the numbers disappoint".
- **Breaking the live demo flow** (resident asks, crew is offered the job, refuge is the drop-off, texts go out).
- **The hosted API failing to start.** It installs no numpy or scipy; everything the API imports must run without them.

## What exists today

| Where | File | How it routes |
|---|---|---|
| Beryl replay | `hearth/sim/engine.py` calls `planner.assign` each half-hour step | Needs sorted by risk weight over hours left; each takes the nearest free crew allowed to serve it. A crew does one job, then is free at the drop-off. |
| Live help loop | `hearth/dispatch.py` `run()` | A model orders the queue (rule fallback). In that order, each request gets the nearest eligible refuge, then `planner.assign` with a single need picks the nearest free crew that fits, strict equipment first, then loose. |
| `/simulation` page | `web/lib/simulation.ts` `runSide` | Its own TypeScript model: a 24-hour day, 5 stations of 3 vans, rounds of up to 4 stops that return to the station, closest van-and-order pair first, then nearest-stop chaining. Household positions come from the API; routes do not. |

`planner.assign` and its tests (`tests/sim/test_planner.py`) stay untouched.

## Approaches considered

1. **ALNS alone, starting from today's greedy plan.** The user's first idea. Flexible with our odd rules (one-person
   rides, stock, crew fit). Weak at county scale in plain Python: with 320 crews and thousands of open needs it gets few
   search steps per half-hour, so it would land close to its greedy start. It also leaves the bigger flaw in place: the
   greedy start ranks by urgency and ignores travel time.
2. **An off-the-shelf routing solver (OR-Tools, PyVRP).** PyVRP's hybrid genetic search beats ALNS on standard
   benchmarks. Rejected: a heavy dependency the night before the deadline, and our score has to be bent into its model.
3. **Exact pairing only.** Small and safe, fixes nearest-first, but no multi-job look-ahead.
4. **Two layers: exact pairing as the starting plan, ALNS on top. Chosen by the user.** Pairing fixes the bigger flaw
   cheaply; ALNS adds look-ahead where it can; each gets its own line in the sweep so the chart shows what each adds.

Not measured before choosing: which layer gains more is an expectation, not a result.

## Design

### The score both layers minimize

For a plan made at time `now` with look-ahead `H` hours:

```
cost_n(reach) = w_n * max(0, reach - deadline_n)                      # late: hours at risk waiting for a crew
              + early * (w_n / max(h_n, 0.1)) * (reach - now)         # sooner is better, by today's urgency key

J = sum over needs n of cost_n(reach_n)   +   tiny * total crew-hours
```

- `w_n` is the need's weight (`Need.weight`, the patient's risk weight in the replay) and `h_n` is
  `Need.hours_until_empty`.
- `deadline_n = now + h_n`: the moment the person starts being at risk. A need already past it has a deadline in the
  past.
- `reach_n` is when a crew arrives at the person. A need no route reaches inside the window counts as reached at
  `now + H`.
- `early` is a small constant (`planner.early_weight`). The early term keeps today's rule (risk weight over hours left)
  alive for needs that are not yet late, so a crew never idles while an allowed need exists, and a need whose deadline
  is beyond the window is still worth sending for. Without it, the 4-hour welfare checks, the early deliveries greedy
  sends today (about a quarter of offered needs at 320 crews have more than 6 hours left) and the demo residents
  (13 to 28 hours of backup) would get no crew. `H` therefore only sets how deep routes are planned.
- The crew-hours term only breaks ties toward shorter plans.

In words: weighted hours people spend at risk waiting for a crew, inside the window, with a light pull toward reaching
everyone sooner. This is the planner's stand-in for the published metric (risk-weighted hours at risk); it is not the
same number.

### The entry point

`hearth/planner.py` gains one function beside `assign`:

```python
def plan(needs, crews, stock, flags, now_h, *, routing, fits=None, travel=travel_h, rng=None) -> list[Job]
```

- `routing` is `"paired"` or `"alns"`. (`"greedy"` callers keep calling `assign`.)
- It returns jobs in the same shape `assign` returns, and mutates the chosen crews and `stock` the same way, so callers
  change one line.
- `crews` includes busy crews. A busy crew's route starts at its `free_at_h` and its drop-off position, which `Crew`
  already holds.
- Only the first job of each crew that is free now is returned. The rest of the plan is thrown away and rebuilt at the
  next step.
- `travel` is injectable because `/simulation` measures distance in degrees, not km.
- `Crew` gains two optional fields, `base` and `capacity`, both `None` in the replay and the live loop. With them set, a
  route returns to `base` after every `capacity` jobs. Only `/simulation` sets them.
- `plan` must run with neither numpy nor scipy installed (the hosted API). When they are importable it may use them
  for the value matrix and the assignment, guarded the way `planner.py` already guards `km`. This is needed: a 320-crew
  run offers about 151 million crew-need pairs, which is minutes per run in plain Python. A test checks the fast and
  plain paths return the same pairing.

`Flags` gains `routing: str = "greedy"`. `policy_label` appends `__paired` or `__alns`. The default leaves every
existing label and number unchanged.

### Layer 1: pairing

For each free crew `c` and each candidate need `n` the crew is allowed to serve (supplier or mutual aid, stock, `fits`):

```
value(c, n) = ( cost_n(now + H) - cost_n(reach(c, n)) ) / hours(c, n)
```

`hours(c, n)` is the crew time the job uses: travel to the person, service, and the ride leg if there is one. The value
is the drop in `J` from sending this crew now, per crew-hour spent. It is positive for any need the crew can reach
inside the window; a pair with value 0 or less is left out.

Solve the assignment that maximizes total value, one need per crew and one crew per need. The candidates are the same
ones the engine offers today (the top needs per free crew), and the builder may also keep only each crew's best few
columns for speed. The pairing is exact over the pairs considered, and the pitch says "jointly best pairing among the
candidates", not "exact" or "optimal" without that qualifier.

- With scipy installed (`sim` dependency group, new): `scipy.optimize.linear_sum_assignment`.
- Without it (the hosted API): a plain-Python Hungarian solver. Sizes there are small (a handful of crews live, 15 vans
  on `/simulation`).
- A test checks the two solvers agree on random small matrices.
- Stock: if an assignment gives a supplier more deliveries than it has units, keep that supplier's highest-value
  deliveries and solve once more without the dropped pairs.

### Layer 2: ALNS

- **Start**: the pairing's jobs as each free crew's first job, then every remaining candidate inserted at the position
  that raises `J` least, until no insertion lowers `J`.
- **Remove** a share of routed jobs with one of: random, worst (largest share of `J`), related (near each other).
- **Reinsert** with one of: cheapest insertion, regret-2 insertion.
- **Accept** by simulated annealing; keep the best plan seen. Operator choice adapts to which ones have been improving.
- **Budget**: a fixed iteration count from `config/assumptions.yaml`. The random stream is seeded from the run seed and
  the step, so a run is reproducible.
- **Speed cut**: a job is only tried in the routes of the few crews nearest to it.
- Because the best plan seen is kept, the ALNS plan's `J` is never above the pairing's.

New entries in `config/assumptions.yaml`, each with a source and `confirmed: false` like the rest:
`planner.lookahead_h`, `planner.early_weight`, `planner.alns_iterations`, `planner.alns_remove_share`,
`planner.insert_nearest_crews`.

### Beryl replay

In `engine.run`, the `# crews` block keeps building `needs` exactly as now (including the top-50-per-free-crew cut). If
`flags.routing == "greedy"` it calls `assign` as today; otherwise `plan`. Events, snapshots and job bookkeeping are
unchanged.

`hearth/sim/sweep.py` adds `("p3", Flags(routing="paired"))` and `("p3", Flags(routing="alns"))`. `python -m hearth.sim
run` gains `--routing`.

Speed target: a 320-crew ALNS run under about three minutes, and the whole sweep (350 runs, 10 cores) under an hour.
The builder tunes the iteration count and the nearest-crews cut to fit.

### Results page

`web/lib/types.ts`: `POLICY_ORDER` and `POLICY_LABELS` gain `p3__paired` ("Hearth, best pairing") and `p3__alns`
("Hearth, optimized routes"). The comparison card adds `p3__alns`. The chart copy says in one sentence what the two new
lines are. Follow the existing pattern for colours and toggles.

### `/simulation`

- New `hearth/sim/day.py` (plain Python, no numpy): the page's 24-hour day run through `plan`. Needs appear at their
  hour, a served repeat household needs a restock `refill_h` later, vans leave a station and return to it.
- New `POST /api/sim/day`. The page sends its households and its own constants (stations, vans per station, cruise
  speed, service time, step, run length, refill hours, capacity), so Python holds no copy of them. It returns the
  Hearth side in the `SideSim` shape the page already draws (`jobs`, `legs`, `station`, `tours`, `stops`, `refills`,
  `events`, and an empty `calls`).
- `buildCounty` takes an optional ready-made Hearth side. `loadCounty` asks the API for it. On any error, or with no API
  configured, the page uses the existing TypeScript greedy routes and the source badge says so. Nothing throws into the
  page.
- A free van's committed round is the first `capacity` jobs of its planned route, as the page's model already commits
  whole rounds.
- The "today" side is untouched.
- **What it is measured against.** The Hearth side the page shows today is the TypeScript greedy (`runSide`), so that is
  the reference, not `planner.assign`. A small script writes the fixture households, the page's constants and the
  TypeScript greedy's total weighted wait to a committed JSON file under `tests/`; the Python test reads it. Wait is
  `servedAt - dueAt` per job, with a job unserved at the end counted to the end of the day, weighted as the planner
  weights it.
- **If the Python side loses to that reference** after tuning the new assumptions, the page keeps its TypeScript routes
  and the user is told. A Hearth side worse than today's is not shipped.

### Live help loop

`dispatch.run()` keeps the model's ordering, the refuge choice in rank order, the strict-then-loose equipment rule, the
offer and accept flow, and every blocked reason. The change is the last step: instead of calling `assign` once per
request, it builds one `Need` per placeable request and calls `plan(..., routing="paired")` once, strict fit first and
then loose for whatever is left. A request's weight comes from the model's order (first of N gets N, last gets 1); its
deadline comes from the hours the rule already uses. No ALNS here: there are a handful of requests.

Refuge places: pairing needs every request's drop-off before it knows who gets a crew. Refuges are chosen in rank order
and each placeable request holds its place for that planning pass only; a request that gets no crew in the pass
releases it (nothing is saved for it, as today). When a refuge is nearly full, a lower-ranked resident can therefore be
sent to a farther one while the holder is still waiting for a crew.

With one waiting request the outcome is the same as today. Existing tests in `tests/test_dispatch.py` and
`tests/test_help.py` must pass unchanged or the builder stops and reports which expectation moved.

## Build order and cut lines

Each step leaves `main` shippable. If time runs out, stop after any step.

1. `plan` with pairing, both solvers, tests.
2. ALNS layer, tests.
3. Replay flag, sweep, results page, `docs/spec.md` numbers.
4. `/simulation` endpoint and page.
5. Live help loop.

## Done means

- All existing tests pass. The 25 existing sweep rows are identical after the rerun. Reproduce them before changing
  anything, with `HEARTH_DB=data/hearth.db` set: `.env` points the store at Postgres, and the published rows came from
  the local store (the reviewer reproduced the `p3`, 20-crew row that way; the other 24 are unchecked).
- New tests: pairing beats nearest-first on a hand-built case; the two assignment solvers agree, and so do the fast and
  plain value paths; `J` of the ALNS plan is never above the pairing plan's on random cases; a need with a deadline
  beyond the window still gets a free crew; a run with the same seed gives the same summary twice; `day.py` with ALNS
  has total weighted wait no higher than the TypeScript greedy reference; importing `api.main` without numpy still
  works.
- The sweep file has 35 rows and the results page draws seven lines.
- `/simulation` on `localhost:3000` shows the Hearth side from the API, and falls back cleanly with the API stopped.
- `docs/spec.md` is updated: results table, the routing paragraph, the assumptions list, and wording for the pitch
  ("a central planner: exact pairing plus ALNS route search", never "optimal").

## If the numbers disappoint

`J` is a stand-in for the published metric, so a lower `J` does not guarantee fewer risk-weighted hours. After step 3
the builder compares `p3`, `p3__paired` and `p3__alns` on seeds 1 to 3 at 20, 80 and 320 crews.

- If a new line is worse than `p3`, the builder may tune only the five new assumptions, on those seeds, and must say so.
- If it is still worse, stop and tell the user before touching the results page. The numbers are published as they are
  or the line is left off; they are not tuned until they look good.

## Calls made in this design (the user has not confirmed these)

- The score is weighted hours at risk waiting for a crew, not plain average time, plus a light pull toward reaching
  everyone sooner so crews never idle.
- The pairing value is the drop in the score per crew-hour.
- The planner uses numpy and scipy when they are installed and plain Python when they are not.
- If the Python routes on `/simulation` are worse than the page's current ones, the page keeps the current ones.
- In the live loop a request holds its refuge place only for the planning pass, in rank order.
- The results chart adds two lines and keeps the current Hearth line as is.
- In the live loop the model's order becomes a weight, so a much closer request can go before a higher-ranked one when
  crews are short. The model's reasons still show.
- On `/simulation` a first delivery weighs twice a restock (today the greedy code puts every first delivery ahead of
  every restock), and a need can be planned only once it has started, as now.
- scipy is added to the `sim` dependency group only.
- The plain-Python fallback solver is a Hungarian implementation written here, not a new package.

## Left to the builder

- The exact removal share, annealing schedule and operator weighting.
- Names and file layout inside `hearth/planner.py` (split into a second module if it grows past easy reading).
- Event wording returned by `/api/sim/day`, matching the page's existing lines.
- Chart colours and the one-sentence copy for the new lines.
