# Central Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One planning function, jointly best pairing plus an ALNS route search, that the Beryl replay, the `/simulation` page and the live help loop all call.

**Architecture:** `hearth/routing.py` holds the score, the pairing and the two entry points (`routes`, `plan`); `hearth/alns.py` holds the route search. Today's greedy `planner.assign` stays untouched and stays the default, so nothing published changes. Each caller switches on one flag or one call.

**Tech Stack:** Python 3.12 (plain Python on the API path; numpy and scipy as a guarded fast path in the replay), FastAPI, Next.js 15 with vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-central-planner-design.md`

## Global Constraints

- The 25 existing rows of `results/sweep_beryl_2024.json` must be identical after every rerun. Always run the sweep with `HEARTH_DB=data/hearth.db` (`.env` points the store at Postgres).
- `planner.assign` and `tests/sim/test_planner.py` are not edited. `Flags().routing` defaults to `"greedy"`.
- Do not regenerate the committed run folders under `results/` (their `meta.json` would gain a `routing` key). Only the sweep file is regenerated.
- The search uses a fixed iteration count and `random.Random` seeded from the run seed and the step. No wall-clock budgets, no `hash()`.
- Everything `api.main` imports must import with numpy, pandas and scipy absent (`tests/test_hosted_start.py`).
- Every new setting goes in `config/assumptions.yaml` as `{value, source, confirmed: false}` and is read with `a("planner.…")`.
- Pitch and page wording: "jointly best pairing among the candidates, plus ALNS route search". Never "optimal" or "exact" on their own.
- Commit after each task on the branch `central-planner`. Do not push: every push asks Vercel for two deployments and the account is rate limited. Push once, when the user says so.
- The user reviews on `localhost:3000`, served from the `main-preview` checkout (`web-main` and `api-main` in `.claude/launch.json`). To show work: commit, `git -C <main-preview> checkout --detach central-planner`, and restart `api-main` when Python changed.

## Review Focus

1. **Nothing to plan.** No free crew, no needs, or every pair disallowed (wrong supplier, `fits` false, no stock): `plan` returns `[]` and never calls a solver with an empty matrix. Test in Task 1.
2. **Uneven sides.** More crews than needs and more needs than crews, in both assignment solvers. Test in Task 1.
3. **A job that takes no time.** Live requests have `service_h=0` and a crew can stand in the resident's building: crew-hours are floored at 0.01 so the value never divides by zero. Test in Task 1.
4. **Parked vans after JSON.** `vehiclesAt` detects a parked leg with `leg.from === leg.to`, which is false for arrays parsed from the API. Compare by value. Test in Task 6.
5. **A hostile or huge day request.** `/api/sim/day` with 100,000 households, `dt` of 0 or a 10,000-hour run answers 422 instead of running. Test in Task 5.

---

### Task 1: Score, pairing and the `plan` entry point

**Files:**
- Create: `hearth/routing.py`, `tests/test_routing.py`
- Modify: `hearth/planner.py` (two dataclasses only), `config/assumptions.yaml` (`planner:` block), `pyproject.toml` (`sim` group)

**Interfaces:**
- Consumes: `planner.Need`, `planner.Crew`, `planner.Flags`, `planner.travel_h`, `contracts.Job`, `config.a`.
- Produces:

```python
# hearth/planner.py
class Flags:  ... routing: str = "greedy"            # greedy | paired | alns
class Crew:   ... base: tuple[float, float] | None = None; capacity: int | None = None

# hearth/routing.py
Point = tuple[float, float]
Travel = Callable[[Point, Point], float]              # hours between two points
def cost(n: Need, reach_h: float, now_h: float) -> float
def allowed(n: Need, c: Crew, stock: dict, flags: Flags, fits) -> bool
def solve(values: list[list[float]]) -> list[tuple[int, int]]      # (row, col) pairs, positive entries only
def hungarian(values: list[list[float]]) -> list[tuple[int, int]]  # same answer, plain Python
def pair(needs, crews, stock, flags, now_h, *, fits=None, travel: Travel = travel_h) -> dict[str, Need]  # crew_id -> need
def routes(needs, crews, stock, flags, now_h, *, routing: str, fits=None, travel: Travel = travel_h,
           rng: random.Random | None = None) -> dict[str, list[Need]]   # crew_id -> ordered needs; mutates nothing
def plan(needs, crews, stock, flags, now_h, *, routing: str, fits=None, travel: Travel = travel_h,
         rng: random.Random | None = None) -> list[Job]
```

- [ ] **Step 1: Add the settings and the dependency**

In `config/assumptions.yaml` under `planner:` add, each with `source: "our call (central planner design, Nov 14)"` and `confirmed: false`:
`lookahead_h: 6`, `early_weight: 0.1`, `alns_iterations: 40`, `alns_remove_share: 0.15`, `insert_nearest_crews: 4`.
In `pyproject.toml` add `"scipy>=1.14"` to the `sim` group, then run `uv sync`.
Add `routing: str = "greedy"` to `Flags` and `base`, `capacity` (both default `None`) to `Crew`.

- [ ] **Step 2: Write the failing tests** in `tests/test_routing.py`

Reuse the `need`, `crew`, `stock` helpers' shapes from `tests/sim/test_planner.py` (copy the three small builders; add `lat`/`lon` parameters).

```python
def test_cost_is_weighted_lateness_plus_a_pull_toward_sooner():
    n = need("a", w=3, hours=2)                       # deadline at now + 2
    assert cost(n, 1.0, 0.0) == pytest.approx(0.1 * (3 / 2) * 1.0)             # early term only
    assert cost(n, 5.0, 0.0) == pytest.approx(3 * 3.0 + 0.1 * (3 / 2) * 5.0)   # 3 h late

def test_pairing_beats_nearest_first():
    # two crews, two needs on a line: greedy gives the urgent need its nearest crew and leaves the other a long drive;
    # the joint pairing has the higher total value. Build so assign() and pair() choose different crews for "urgent".
    ...assert sum of value under pair() > sum of value under the pairing assign() makes

def test_a_need_due_after_the_window_still_gets_a_free_crew():
    assert len(plan([need("far", hours=28)], [crew("c1")], stock(1), Flags(), 0, routing="paired")) == 1

def test_nothing_to_plan_returns_nothing():
    assert plan([], [crew("c1")], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a")], [], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a", supplier="s1")], [crew("c2", org="s2")], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a")], [crew("c1")], stock(1), Flags(), 0, routing="paired", fits=lambda n, c: False) == []

@pytest.mark.parametrize("rows,cols", [(2, 5), (5, 2), (4, 4), (1, 1)])
def test_the_two_solvers_agree_on_uneven_sides(rows, cols):
    rng = random.Random(rows * 10 + cols)
    for _ in range(30):
        v = [[rng.choice([0.0, rng.random()]) for _ in range(cols)] for _ in range(rows)]
        total = lambda pairs: sum(v[r][c] for r, c in pairs)
        assert total(solve(v)) == pytest.approx(total(hungarian(v)))
        assert all(v[r][c] > 0 for r, c in hungarian(v))

def test_a_job_that_takes_no_time_does_not_divide_by_zero():
    n = Need("a", "ride", "", 2.0, 1.0, 29.80, -95.40, 0.0, 0.0, dest=(29.80, -95.40))   # crew stands on it
    assert len(plan([n], [crew("c1")], {}, Flags(), 0, routing="paired")) == 1

def test_stock_caps_deliveries_and_keeps_the_most_valuable():
    jobs = plan([need("low", w=1), need("high", w=5)], [crew("c1"), crew("c2")], stock(1), Flags(), 0, routing="paired")
    assert [j.patient_id for j in jobs] == ["high"]

def test_plan_commits_like_assign():
    c, s = crew("c1"), stock(3)
    job = plan([need("a")], [c], s, Flags(), 0, routing="paired")[0]
    assert job.status == "accepted" and job.data["crew_id"] == "c1" and job.data["done_h"] == c.free_at_h > 0
    assert s["s1"] == 2 and (c.lat, c.lon) == (29.76, -95.37)

def test_routes_mutates_nothing():
    c, s = crew("c1"), stock(3)
    routes([need("a")], [c], s, Flags(), 0, routing="paired")
    assert c.free_at_h == 0 and s["s1"] == 3
```

- [ ] **Step 3: Run them and see them fail**

Run: `uv run pytest tests/test_routing.py -q`
Expected: collection error, `No module named 'hearth.routing'`.

- [ ] **Step 4: Implement `hearth/routing.py`**

Decisions the tests do not pin:

- `cost(n, reach, now) = n.weight * max(0, reach - (now + n.hours_until_empty)) + a("planner.early_weight") * n.weight / max(n.hours_until_empty, 0.1) * (reach - now)`.
- `allowed` is the rule inside `assign`: a delivery needs `flags.mutual_aid or c.org_id == n.supplier_id` and `stock.get(c.org_id, 0) > 0`; then `fits is None or fits(n, c)`.
- For a crew free now, `reach = now + travel(crew, need)` and `hours = max(travel(crew, need) + n.service_h + (travel(need, n.dest) if n.dest else 0), 0.01)`.
- `value = (cost(n, now + H, now) - cost(n, reach, now)) / hours` with `H = a("planner.lookahead_h")`; a disallowed pair is `0.0`.
- `pair` considers only crews with `free_at_h <= now_h`. After solving, if a supplier got more deliveries than `stock` holds, keep its highest-value ones, zero the dropped pairs and solve once more.
- `solve` uses `scipy.optimize.linear_sum_assignment(maximize=True)` when scipy imports, else `hungarian`; both drop pairs whose value is not positive. Guard the import the way `planner.py` guards `km`.
- Fast path: when numpy imports and `travel is travel_h`, build the value matrix with arrays (`hearth.population.km` takes arrays). Otherwise loop. Add `test_fast_and_plain_value_paths_agree` in `tests/sim/test_routing_fast.py` (numpy lives in the `sim` tests): same `pair` result with the fast path on and with `routing._np` monkeypatched to `None`.
- `routes(..., routing="paired")` returns `{crew_id: [need]}` from `pair`. `routing="alns"` raises `NotImplementedError` until Task 2.
- `plan` calls `routes`, then for each crew free now, in descending value of its first job, commits that job exactly as `assign` does (same `Job` fields, `done_h`, crew position at the drop-off, stock minus one for a delivery). A delivery whose supplier has no unit left at commit time is skipped. Comment: `# shortcut: a skipped crew waits one step, upgrade if stock ever runs short in the sweep`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_routing.py tests/sim/test_routing_fast.py tests/sim/test_planner.py tests/test_hosted_start.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hearth/routing.py hearth/planner.py tests/test_routing.py tests/sim/test_routing_fast.py config/assumptions.yaml pyproject.toml uv.lock
git commit -m "feat: central planner entry point with jointly best pairing of crews and needs"
```

---

### Task 2: ALNS route search

**Files:**
- Create: `hearth/alns.py`, `tests/test_alns.py`
- Modify: `hearth/routing.py` (`routes` with `routing="alns"`)

**Interfaces:**
- Consumes: `routing.cost`, `routing.allowed`, `routing.pair`, `Crew.base`, `Crew.capacity`.
- Produces:

```python
# hearth/alns.py
Routes = dict[str, list[Need]]                         # crew_id -> ordered needs
def reach_times(c: Crew, route: list[Need], now_h: float, travel: Travel) -> list[float]
def plan_cost(routes: Routes, pool: list[Need], crews: list[Crew], now_h: float, travel: Travel) -> float
def search(start: Routes, pool: list[Need], crews: list[Crew], can: Callable[[Need, Crew], bool], now_h: float,
           *, travel: Travel, rng: random.Random) -> Routes
```

`pool` is every need in play, routed or not. `plan_cost` is the spec's `J`: `cost` at each routed need's reach time, `cost(n, now + H, now)` for the rest, plus `1e-6 *` total crew-hours.

- [ ] **Step 1: Write the failing tests** in `tests/test_alns.py`

```python
def test_reach_times_follow_the_route_and_return_to_base_when_full():
    # one crew at base (0, 0), capacity 2, three needs at (0, 1), (0, 2), (0, 3), travel = distance, service 0:
    # reaches at 1, 2, then back to base (2 more) and out again (3): [1, 2, 7]
    assert reach_times(c, [n1, n2, n3], 0.0, flat) == [1.0, 2.0, 7.0]

def test_a_busy_crew_starts_when_it_is_free():
    assert reach_times(Crew("c", "s1", 0.0, 0.0, free_at_h=5.0), [n1], 0.0, flat) == [6.0]

def test_a_ride_ends_at_its_drop_off_before_the_next_stop():
    # ride at (0, 1) with dest (0, 5), then a need at (0, 6): reach [1, 6]
    ...

@pytest.mark.parametrize("seed", range(20))
def test_search_never_ends_above_its_start(seed):
    # random crews and needs; start = routing.routes(..., routing="paired")
    assert plan_cost(search(start, pool, crews, can, 0.0, travel=flat, rng=random.Random(seed)), pool, crews, 0.0, flat) \
        <= plan_cost(start, pool, crews, 0.0, flat) + 1e-9

def test_search_is_reproducible():
    assert search(..., rng=random.Random(7)) == search(..., rng=random.Random(7))

def test_search_keeps_every_need_at_most_once_and_only_on_crews_that_can_take_it():
    ...

def test_search_finds_the_obvious_chain():
    # one free crew, three late needs in a line; pairing routes one, search routes all three in line order
    assert [n.patient_id for n in out["c1"]] == ["a", "b", "c"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_alns.py -q`
Expected: `No module named 'hearth.alns'`.

- [ ] **Step 3: Implement `hearth/alns.py`**

Plain Python only. The algorithm, which the tests do not determine:

```
start: copy of `start`; then repeat: over needs not yet routed, find the (need, crew, position) with the largest drop in
       plan_cost, trying only the a("planner.insert_nearest_crews") crews nearest the need (by crew start point) that
       `can` take it; insert it; stop when no insertion lowers the cost.
best = current = start;  T = 0.05 * plan_cost(start) or 1.0
weights = {operator: 1.0} for remove in (random, worst, related) and repair in (cheapest, regret2)
for i in range(a("planner.alns_iterations")):
    q = max(1, round(a("planner.alns_remove_share") * routed_count))
    remove q needs:  random | the q with the largest own cost | a random seed need and its q-1 nearest
    repair:          cheapest insertion as above | regret-2 (insert first the need whose best and second-best
                     positions differ most)
    accept if new < current, or with probability exp((current - new) / T);  T *= 0.95
    if new < best: best = new; that pair of operators' weights += 1
    choose the next operators with rng.choices(weights)
return best
```

A crew free now keeps a first job only from needs it `can` take; the first job of a busy crew is unconstrained in time (its route starts at `free_at_h`). With `capacity` set, `reach_times` inserts a trip to `base` after every `capacity` stops.

In `routing.routes`, `routing="alns"`: pool = `needs`; start = the `pair` result; `can = lambda n, c: allowed(n, c, stock, flags, fits)`; return `alns.search(...)`. Crews in play are all crews with `free_at_h < now_h + H`. `rng` defaults to `random.Random(0)`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_alns.py tests/test_routing.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add hearth/alns.py hearth/routing.py tests/test_alns.py
git commit -m "feat: ALNS route search on top of the pairing"
```

---

### Task 3: Replay flag, sweep, and the honesty gate

**Files:**
- Modify: `hearth/sim/engine.py` (`policy_label`, the `# crews` block), `hearth/sim/sweep.py`, `hearth/sim/__main__.py`, `tests/sim/test_engine.py`
- Regenerate: `results/sweep_beryl_2024.json`, `results/sweep_beryl_2024.assumptions.yaml`

**Interfaces:**
- Consumes: `routing.plan`, `Flags.routing`.
- Produces: policy labels `p3__paired` and `p3__alns`; sweep rows for both.

- [ ] **Step 1: Reproduce the published rows before touching anything**

```bash
HEARTH_DB=data/hearth.db uv run python -m hearth.sim sweep --scenario beryl_2024 > /dev/null && git diff --stat results/
```
Expected: no diff in `results/sweep_beryl_2024.json`. If there is one, stop and report: the baseline does not reproduce and nothing after this can be trusted.

- [ ] **Step 2: Write the failing tests** in `tests/sim/test_engine.py`

```python
def test_routing_changes_the_label_and_leaves_greedy_alone():
    assert policy_label("p3", Flags()) == "p3"
    assert policy_label("p3", Flags(routing="alns")) == "p3__alns"
    assert policy_label("p3", Flags(use_buildings=False, routing="paired")) == "p3__nobld__paired"

@pytest.mark.parametrize("routing", ["paired", "alns"])
def test_a_routed_run_is_reproducible_and_valid(routing):
    s1 = run("sample", "p3", 1, 5, Flags(routing=routing), out_root=None)
    s2 = run("sample", "p3", 1, 5, Flags(routing=routing), out_root=None)
    assert s1 == s2 and s1["run_id"] == f"sample__p3__{routing}__c5__s1"
```
Change `test_sweep_writes_one_row_per_policy_and_crew_count` to expect 14 rows and the set of seven labels.

- [ ] **Step 3: Implement**

- `policy_label`: append `f"__{flags.routing}"` when `flags.routing != "greedy"`.
- `# crews` block: `needs` is built as now. `jobs = assign(needs, fleet, stock, flags, now, fcfs=policy == "p0") if policy == "p0" or flags.routing == "greedy" else plan(needs, fleet, stock, flags, now, routing=flags.routing, rng=random.Random(f"{seed}:{k}"))`.
- `SWEEP` gains `("p3", Flags(routing="paired"))` and `("p3", Flags(routing="alns"))`, last.
- `python -m hearth.sim run` gains `--routing {greedy,paired,alns}`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/sim -q`
Expected: all pass, including `test_same_seed_same_bytes`.

- [ ] **Step 5: Time one run of each kind**

```bash
HEARTH_DB=data/hearth.db uv run python -c "
import time; from hearth.sim.engine import run; from hearth.planner import Flags
for r in ('paired','alns'):
    for c in (20, 320):
        t=time.time(); s=run('beryl_2024','p3',1,c,Flags(routing=r),out_root=None); print(r, c, round(time.time()-t), 's', round(s['risk_hours_weighted']), s['moves'])"
```
Expected: every run under 180 s. If the ALNS run at 320 crews is slower, lower `planner.alns_iterations`, then `planner.insert_nearest_crews`, and cap the pool to the top `8 * crews in play` needs by pairing value, in that order, until it fits.

- [ ] **Step 6: The gate. Compare on seeds 1 to 3 at 20, 80 and 320 crews**

Run `p3` greedy, `paired` and `alns` for those nine cells (same one-liner, three seeds) and print the weighted risk-hours and `moves` side by side.

- Both new lines at or below greedy in every cell: go on.
- A new line above greedy: tune only the five `planner.*` settings added in Task 1, on these seeds, and write down what was changed and why. First thing to look at is `moves`: the pairing's per-crew-hour value favours short jobs, so rides may be starved.
- Still above greedy: **stop and tell the user** before any further task. Do not touch the results page.

- [ ] **Step 7: Run the sweep and check the old rows**

```bash
HEARTH_DB=data/hearth.db uv run python -m hearth.sim sweep --scenario beryl_2024 > /dev/null
uv run python -c "
import json, subprocess
old = json.loads(subprocess.check_output(['git','show','HEAD:results/sweep_beryl_2024.json'])); new = json.load(open('results/sweep_beryl_2024.json'))
assert new[:25] == old, 'published rows changed'; print(len(new), 'rows; first 25 identical')"
```
Expected: `35 rows; first 25 identical`.

- [ ] **Step 8: Commit**

```bash
git add hearth/sim tests/sim/test_engine.py results/sweep_beryl_2024.json results/sweep_beryl_2024.assumptions.yaml config/assumptions.yaml
git commit -m "feat(sim): the replay can route with the central planner; sweep adds pairing and ALNS lines"
```

---

### Task 4: Results page and the spec's numbers

**Files:**
- Modify: `web/lib/types.ts`, `web/app/results/page.tsx`, `web/app/globals.css`, `web/lib/results.test.ts`, `docs/spec.md`

**Interfaces:**
- Consumes: sweep rows with `policy` `p3__paired` and `p3__alns`.

- [ ] **Step 1: Write the failing test** in `web/lib/results.test.ts`

```ts
it("orders and labels the two central planner lines", () => {
  expect(POLICY_ORDER.slice(-2)).toEqual(["p3__paired", "p3__alns"]);
  expect(policyLabel("p3__paired")).toBe("Hearth, best pairing");
  expect(policyLabel("p3__alns")).toBe("Hearth, optimized routes");
});
```

- [ ] **Step 2: Run it and see it fail**

Run: `cd web && npm test -- results`
Expected: FAIL on `POLICY_ORDER`.

- [ ] **Step 3: Implement**

- `types.ts`: append the two ids to `POLICY_ORDER` and the two labels to `POLICY_LABELS`; add `p3__alns` to `DEFAULT_POLICIES` and `p3__paired` to `OPTIONAL_POLICIES`.
- `globals.css`: add `--series-6` and `--series-7` in both the light and the dark block. Pick two colours distinct from the five there and from each other; check contrast against the page background in both themes.
- `results/page.tsx`: add `p3__alns` to `COMPARISONS`. In the "How to read this chart" block add one sentence: "The two central planner lines use the same crews and the same rules as Hearth; only who goes where changes: jointly best pairing among the candidates, then an ALNS route search."

- [ ] **Step 4: Run the web checks**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all pass, no type errors.

- [ ] **Step 5: Update `docs/spec.md`**

Add the two rows to the results table from the new sweep file, a line under "How to read it, honestly" stating what each layer added at 20, 80 and 320 crews (whatever the numbers say, including "nothing"), a paragraph in the Simulation section naming `hearth/routing.py` and `hearth/alns.py`, and one line in "Assumptions that flatter Hearth": the planner's score is a stand-in for the published metric and its five settings are our own.

- [ ] **Step 6: Show it on `localhost:3000` and check**

Commit, check the commit out in `main-preview`, restart `api-main`, open `/results`: seven lines in the legend, the card shows "Hearth, optimized routes", no console errors.

```bash
git add web/lib/types.ts web/app/results/page.tsx web/app/globals.css web/lib/results.test.ts docs/spec.md
git commit -m "feat(web): results chart shows the pairing and ALNS lines; spec updated with the new sweep"
```

---

### Task 5: The `/simulation` day in Python, and its endpoint

**Files:**
- Create: `hearth/sim/day.py`, `tests/test_day.py`, `tests/fixtures/sim_day.json` (generated), `web/lib/simDayFixture.test.ts`
- Modify: `web/lib/simulation.ts` (two exports), `api/main.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `routing.routes`, `Crew.base`, `Crew.capacity`.
- Produces:

```ts
// web/lib/simulation.ts
export const DAY_CONSTANTS: { stations: {name: string; at: [number, number]}[]; crewsPerStation: number; cruise: number;
  serviceH: number; dt: number; runHours: number; refillH: number; capacity: number }   // capacity = CAPACITY.hearthAt
export function weightedWait(side: SideSim): number   // sum of (refill ? 1 : 2) * ((servedAt ?? RUN_HOURS) - dueAt)
```
```python
# hearth/sim/day.py   (plain Python: no numpy, no pandas)
def run_day(households: list[dict], k: dict, routing: str = "alns", seed: int = 0) -> dict   # the page's SideSim shape
def weighted_wait(side: dict, run_hours: float) -> float
# api/main.py
POST /api/sim/day   body {"households": [{lon, lat, needsAt, repeats}], "constants": DAY_CONSTANTS}  ->  SideSim
```

- [ ] **Step 1: Export the constants and write the reference fixture**

Add `DAY_CONSTANTS` and `weightedWait` to `simulation.ts`. Create `web/lib/simDayFixture.test.ts`: it builds `{households: drawHouseholds(), constants: DAY_CONSTANTS, greedy: {weightedWait, stops, tours}}` from `buildCounty(drawHouseholds()).sides.hearthAt`; with `WRITE_SIM_FIXTURE=1` it writes that to `../tests/fixtures/sim_day.json`; otherwise it expects the committed file to equal it, so the reference cannot drift from the page.

Run: `cd web && WRITE_SIM_FIXTURE=1 npm test -- simDayFixture && npm test -- simDayFixture`
Expected: file written, then PASS.

- [ ] **Step 2: Write the failing tests** in `tests/test_day.py`

```python
FX = json.loads((ROOT / "tests/fixtures/sim_day.json").read_text())

def test_the_planner_day_waits_no_longer_than_the_pages_greedy():
    side = run_day(FX["households"], FX["constants"])
    assert weighted_wait(side, FX["constants"]["runHours"]) <= FX["greedy"]["weightedWait"]

def test_the_day_has_the_shape_the_page_draws():
    k = FX["constants"]; side = run_day(FX["households"], k)
    vans = len(k["stations"]) * k["crewsPerStation"]
    assert set(side) == {"jobs", "calls", "legs", "station", "tours", "stops", "refills", "events"} and side["calls"] == []
    assert len(side["legs"]) == vans == len(side["station"])
    for legs in side["legs"]:                                   # a van is in one place at a time
        assert all(a["t1"] <= b["t0"] + 1e-9 for a, b in zip(legs, legs[1:]))
    for j in side["jobs"]:
        assert j["servedAt"] is None or j["dueAt"] <= j["sentAt"] <= j["servedAt"]
    assert all(e.get("stops", 1) <= k["capacity"] for e in side["events"] if e["kind"] == "dispatch")
    assert [e["t"] for e in side["events"]] == sorted(e["t"] for e in side["events"])

def test_the_day_is_reproducible():
    assert run_day(FX["households"], FX["constants"]) == run_day(FX["households"], FX["constants"])

def test_a_repeat_household_needs_a_restock_after_refill_hours():
    k = FX["constants"]; side = run_day([{"lon": -95.37, "lat": 29.76, "needsAt": 0, "repeats": True}], k)
    first, second = side["jobs"][0], side["jobs"][1]
    assert second["refill"] and second["dueAt"] == pytest.approx(first["servedAt"] + k["refillH"])
```
In `tests/test_api.py`:
```python
def test_sim_day_returns_a_side_and_refuses_runaway_requests():
    fx = json.loads((ROOT / "tests/fixtures/sim_day.json").read_text())
    r = client.post("/api/sim/day", json={"households": fx["households"][:20], "constants": fx["constants"]})
    assert r.status_code == 200 and len(r.json()["legs"]) == 15
    big = [fx["households"][0]] * 100_000
    assert client.post("/api/sim/day", json={"households": big, "constants": fx["constants"]}).status_code == 422
    for bad in ({"dt": 0}, {"runHours": 10_000}, {"capacity": 0}, {"cruise": 0}):
        assert client.post("/api/sim/day", json={"households": [], "constants": {**fx["constants"], **bad}}).status_code == 422
```

- [ ] **Step 3: Run them and see them fail**

Run: `uv run pytest tests/test_day.py tests/test_api.py -q -k "day"`
Expected: `No module named 'hearth.sim.day'`.

- [ ] **Step 4: Implement `run_day`**

It is the Hearth half of `runSide` in `web/lib/simulation.ts` (lines 422 to 582), with the dispatch decision (lines 487 to 523) replaced by the planner. Read that function first and keep its bookkeeping identical: jobs, `addJob` and the refill rule, `freeAt`, the three legs per stop (drive, park, drive home), counters, and the event texts character for character.

Per step `t`:
- `waiting` = jobs with `sentAt` unset and `dueAt <= t`. One `Need` each: `kind="delivery"`, `supplier_id=""`, `weight` 2.0 for a first delivery and 1.0 for a refill, `hours_until_empty = dueAt - t`, `lat`/`lon` from the household, `service_h = serviceH`.
- One `Crew` per van, at its station, `org_id=""`, `free_at_h = freeAt[c]`, `base` = the station, `capacity = k["capacity"]`.
- `routes(needs, crews, {"": 10**9}, Flags(mutual_aid=True), t, routing=routing, travel=lambda p, q: math.hypot(p[0]-q[0], p[1]-q[1]) / cruise, rng=random.Random(f"{seed}:{t}"))`.
- A van free at `t` with a route takes its first `capacity` needs as one round, committed whole as the page does.
- `routing="greedy"` is not supported here; the page's own greedy is the reference.

- [ ] **Step 5: Add the endpoint**

Pydantic models in `api/main.py` with bounds: at most 600 households; `needsAt` 0 to 48; 1 to 10 stations; `crewsPerStation` 1 to 10; `cruise > 0`; `serviceH` 0 to 4; `dt` 0.05 to 1; `runHours` 1 to 48; `refillH` 0.5 to 48; `capacity` 1 to 10. The handler returns `run_day(...)`. Import `run_day` at the top of the file so `tests/test_hosted_start.py` proves it needs no numpy.

- [ ] **Step 6: Run the tests and time the day**

Run: `uv run pytest tests/test_day.py tests/test_api.py tests/test_hosted_start.py -q`
Expected: all pass. Then time `run_day` on 400 households (repeat the fixture's 140 to reach 400): under 5 seconds, or lower the iteration count for this caller through a `planner.day_alns_iterations` setting.

**If `test_the_planner_day_waits_no_longer_than_the_pages_greedy` fails:** tune the five settings; if it still fails, stop here, skip Task 6, and tell the user. The page keeps its own routes.

- [ ] **Step 7: Commit**

```bash
git add hearth/sim/day.py api/main.py tests/test_day.py tests/test_api.py tests/fixtures/sim_day.json web/lib/simulation.ts web/lib/simDayFixture.test.ts
git commit -m "feat: the simulation page's day planned by the central planner, behind POST /api/sim/day"
```

---

### Task 6: `/simulation` draws the planner's routes

**Files:**
- Modify: `web/lib/simulation.ts` (`buildCounty`, `vehiclesAt`), `web/lib/simSource.ts` (`loadCounty`, `CountyFeed`), `web/lib/simulation.test.ts`

**Interfaces:**
- Consumes: `POST /api/sim/day`, `DAY_CONSTANTS`.
- Produces:

```ts
export function parseSide(raw: unknown, households: number): SideSim | null   // simulation.ts
export function buildCounty(households: Household[], hearthSide?: SideSim): CountySim
export type CountyFeed = { ...; routes: "planner" | "browser" }               // simSource.ts
```

- [ ] **Step 1: Write the failing tests** in `web/lib/simulation.test.ts`

```ts
describe("a Hearth side from the API", () => {
  const households = drawHouseholds();
  const local = buildCounty(households).sides.hearthAt;
  const wire = JSON.parse(JSON.stringify(local));            // what arrives over HTTP

  it("is used as given", () => {
    const side = parseSide(wire, households.length)!;
    expect(buildCounty(households, side).sides.hearthAt).toBe(side);
  });
  it("draws a parked van facing the way it drove in", () => {
    const county = buildCounty(households, parseSide(wire, households.length)!);
    const reference = buildCounty(households);
    for (const t of steps()) expect(county.vehiclesAt(t, "hearthAt")).toEqual(reference.vehiclesAt(t, "hearthAt"));
  });
  it("is refused when it is not the shape the page draws", () => {
    expect(parseSide({ ...wire, legs: wire.legs.slice(1) }, households.length)).toBeNull();
    expect(parseSide({ ...wire, jobs: [{ ...wire.jobs[0], h: households.length }] }, households.length)).toBeNull();
    expect(parseSide({ ...wire, events: "no" }, households.length)).toBeNull();
    expect(parseSide(null, households.length)).toBeNull();
  });
});
```

- [ ] **Step 2: Run them and see them fail**

Run: `cd web && npm test -- simulation`
Expected: FAIL, `parseSide` is not exported.

- [ ] **Step 3: Implement**

- `vehiclesAt`: a leg is parked when `leg.from[0] === leg.to[0] && leg.from[1] === leg.to[1]`.
- `parseSide`: returns the side only if `legs` has exactly `CREW_COUNT` arrays of legs with finite numbers, `station` has `CREW_COUNT` entries, every job's `h` is an index below `households`, `events` and `calls` are arrays, and the three counters are numbers. Otherwise `null`.
- `buildCounty(households, hearthSide)`: `hearthAt: hearthSide ?? runSide(households, "hearthAt")`.
- `loadCounty`: after `households` is built, POST `{households, constants: DAY_CONSTANTS}` to `/api/sim/day` with `authHeaders()` and the abort signal; `parseSide` the answer; any error or a `null` falls back to no side. Set `routes` and extend `detail`: "… · routes from the central planner" or "… · routes drawn in this browser (greedy)". `FIXTURE_FEED.routes` is `"browser"`.

- [ ] **Step 4: Run the web checks**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 5: Verify on `localhost:3000`**

Commit, check out in `main-preview`, restart `api-main`. On `/simulation`: the source badge reads "routes from the central planner", vans move and return to their stations, households change colour as vans leave, no console errors, and the network tab shows one `POST /api/sim/day` with status 200. Stop `api-main`, reload: the page still works and the badge says the routes are drawn in the browser. Start `api-main` again.

- [ ] **Step 6: Commit**

```bash
git add web/lib/simulation.ts web/lib/simSource.ts web/lib/simulation.test.ts
git commit -m "feat(web): the simulation's Hearth side draws the central planner's routes, with the browser's as fallback"
```

---

### Task 7: The live help loop calls the planner

**Files:**
- Modify: `hearth/dispatch.py` (`run`), `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `routing.plan(..., routing="paired", fits=...)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_dispatch.py`

Use the file's existing `crew`, `home`, `answer` helpers and demo patients.

```python
def test_two_requests_and_two_crews_are_paired_to_cut_total_driving():
    # two crews and two requests placed so that the model's first request is nearer crew B and the second is far from B:
    # both get an offer, and the crews are the pairing's, not nearest-first's
    ...assert {r.patient_id: r.job.org_id for r in dispatch.requests()} == {...}

def test_one_crew_goes_to_the_models_first_request_when_distances_are_equal():
    ...

def test_a_much_closer_request_can_go_before_a_higher_ranked_one():
    # one crew standing in the second-ranked resident's building, the first-ranked far across the county
    ...

def test_a_request_without_a_crew_holds_no_refuge_place_afterwards():
    # one place left, two requests, one crew: the one without an offer has refuge None, and gets the place once the first is done
    ...
```

- [ ] **Step 2: Run them and see which fail**

Run: `uv run pytest tests/test_dispatch.py -q`
Expected: the pairing tests fail; everything else passes.

- [ ] **Step 3: Rewrite the body of `run()`**

Keep the lock, the `people`, `dark`, `taken`, `busy`, `on_duty`, `profiles` setup and every blocked reason. Then:

1. In rank order, for each waiting request: choose its refuge with a per-pass copy of `taken`; set `NO_REFUGE` or `NO_CREW` as today; otherwise clear `blocked`, count the place in the copy, and keep `(request, patient, home, here, refuge)`.
2. One `Need` per kept request: `kind="ride"`, `weight` = number kept minus its position (first gets N, last gets 1), `hours_until_empty=0.0` (see the note below), `lat`/`lon` from `here`, `service_h=0.0`, `dest` = the refuge.
3. `jobs = plan(needs, free, {}, planner.Flags(), 0.0, routing="paired", fits=strict)`, then `plan` again with the loose fit for the needs and crews still unpaired. `fits(n, c)` looks the patient up by `n.patient_id` and calls `_fits` as today.
4. For each job: set `r.job`, `r.refuge`, `eta`, count the place in the real `taken`, add the crew to `busy`, `_enter(r, "offered")`. Save every waiting request.

Note on the deadline: every live request counts as already waiting (`hours_until_empty=0`). The model has already weighed each person's hours when it ordered them; feeding the hours in again would let them overturn its order on their own. The design doc is amended to say so.

- [ ] **Step 4: Run every dispatch and help test**

Run: `uv run pytest tests/test_dispatch.py tests/test_help.py tests/test_api.py tests/messaging -q`
Expected: all pass. If an existing test fails, stop and report which expectation moved; do not edit an existing test to fit.

- [ ] **Step 5: Verify the help loop on `localhost:3000`**

Commit, check out in `main-preview`, restart `api-main`. Open a request for a demo resident, see the offer on the responder page, accept it, and see the tracker lines on the dispatch page as before.

- [ ] **Step 6: Commit**

```bash
git add hearth/dispatch.py tests/test_dispatch.py
git commit -m "feat: the live help loop pairs crews and requests through the central planner"
```

---

### Task 8: Final check

- [ ] **Step 1: Everything green**

Run: `uv run pytest -q && cd web && npm test && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 2: The published rows, once more**

Rerun the row check from Task 3, Step 7.
Expected: `35 rows; first 25 identical`.

- [ ] **Step 3: Report**

Tell the user, with the numbers: what each layer added at 20, 80 and 320 crews; the day's weighted wait against the page's greedy; anything tuned and why; what was not verified. Ask before pushing.
