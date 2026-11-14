# Task A: clocks, decision logic, risk metrics

Self-contained brief for one teammate's coding agent. Pure Python, no network, no API keys.

**Branch:** `task/clocks-decision`. Open a pull request to `main`; do not push to `main`.
**Start after** the commit `feat: contracts, store, config and sample files` is on `main` (it provides `hearth.contracts` and `hearth.config`).
**Setup:** `uv sync`, then `uv run pytest tests/sim -v`.

## What this is for

Hearth tracks two clocks per patient during a power outage: hours of device backup left, and how
fast the home becomes unsafely hot or cold. Each tick, code picks a plan state per patient. You
are writing those clocks, the decision rule, and the function that counts hours at risk.

## Files (create only these)

- `hearth/devices.py`, `hearth/temperature.py`, `hearth/decision.py`, `hearth/metrics.py`
- `tests/sim/conftest.py`, `tests/sim/test_temperature.py`, `tests/sim/test_decision.py`, `tests/sim/test_metrics.py`

Do not edit `hearth/contracts.py`, `hearth/config.py`, `hearth/store.py`, or anything under
`hearth/buildings/`, `hearth/messaging/`, `api/`, `web/`.

## You may import

```python
from hearth.contracts import Patient, PlanState     # PlanState: NOT_AFFECTED OWN_BACKUP RESUPPLY MOVE MOVED URGENT UNREACHABLE RESTORED
from hearth.config import a                          # a("decision.margin_h") -> 12
```

Config values to read with `a(...)`, never hard-code: `decision.margin_h` (12),
`decision.hysteresis_ticks` (2), `temperature.unsafe_heat_index_c` (32),
`temperature.unsafe_cold_c` (16), `temperature.setpoint_c` (22).

## Functions to write

```python
# hearth/temperature.py
def heat_index_c(temp_c, rh)            # float or numpy array in, same out. NWS Rothfusz regression, computed in
                                        # Fahrenheit and converted back. Below 26.7 C return temp_c unchanged.
def step_indoor(indoor_c, outdoor_c, dark, heat_tc, cold_tc, dt_h) -> np.ndarray
    # dark homes: indoor += (outdoor - indoor) * dt_h / tc, with tc = heat_tc when outdoor > indoor, else cold_tc
    # powered homes: indoor = setpoint
def unsafe_temp(indoor_c, rh, sensitivity) -> np.ndarray   # bool per patient; sensitivity is an array of "heat"|"cold"|"both"|"none"
    # heat-unsafe when heat_index_c > unsafe_heat_index_c and sensitivity in (heat, both)
    # cold-unsafe when indoor_c < unsafe_cold_c and sensitivity in (cold, both)

# hearth/devices.py
def drain(backup_h, use_rate, dark, moved, dt_h) -> np.ndarray   # subtract use_rate*dt_h where dark and not moved; never below 0

# hearth/decision.py
@dataclass
class Ctx:
    hours_to_restoration: float
    home_unsafe: bool
    temp_unsafe_before_restoration: bool
    delivery_feasible: bool
    move_feasible: bool
    allow_moves: bool = True
def decide(patient: Patient, backup_h: float, ctx: Ctx) -> PlanState
def with_hysteresis(prev: PlanState, proposed: PlanState, streak: int) -> tuple[PlanState, int]

# hearth/metrics.py
def at_risk(backup_h, dark, moved, temp_unsafe) -> np.ndarray    # ((backup_h <= 0) & dark | temp_unsafe) & ~moved
def summarize(risk_matrix, weights, dt_h) -> dict                # risk_matrix shape (ticks, patients), bool
    # {"risk_hours_unweighted": risk_matrix.sum() * dt_h, "risk_hours_weighted": (risk_matrix * weights).sum() * dt_h}
```

`decide` asks these in order; the first that applies wins. `can_move = ctx.allow_moves and ctx.move_feasible`.

1. `ctx.home_unsafe`: `MOVE` if `can_move`, else `URGENT`.
2. `patient.temp_sensitive != "none"` and `ctx.temp_unsafe_before_restoration`: `MOVE` if `can_move`; else `RESUPPLY` if `ctx.delivery_feasible`; else `URGENT`. Never `OWN_BACKUP` here, however much backup the device has.
3. `patient.device == "home_dialysis"`: `MOVE` if `can_move`, else `URGENT`.
4. `backup_h >= ctx.hours_to_restoration + margin_h`: `OWN_BACKUP`.
5. `ctx.delivery_feasible`: `RESUPPLY`.
6. `can_move`: `MOVE`.
7. Otherwise `URGENT`.

`with_hysteresis`: if `{prev, proposed} == {RESUPPLY, MOVE}`, the switch needs
`hysteresis_ticks` consecutive ticks: return `(prev, streak + 1)` until `streak + 1` reaches the
setting, then `(proposed, 0)`. Every other transition is immediate: `(proposed, 0)`.

## Tests (write these first, watch them fail, then implement)

`tests/sim/conftest.py` defines two helpers used below:
`pat(**overrides) -> Patient` (a valid oxygen patient with `temp_sensitive="none"` unless overridden) and
`ctx(restoration=48, home_unsafe=False, temp_unsafe=False, delivery=False, move=False, allow_moves=True) -> Ctx`.

```python
def test_heat_index_matches_nws_table(): assert heat_index_c(32.2, 70) == pytest.approx(40.6, abs=1.2)   # 90 F at 70% is 105 F
def test_heat_index_below_threshold_is_the_temperature(): assert heat_index_c(20.0, 90) == 20.0
def test_indoor_approaches_outdoor_at_the_time_constant():
    t = np.array([22.0])
    for _ in range(16): t = step_indoor(t, 35.0, np.array([True]), np.array([8.0]), np.array([12.0]), 0.5)
    assert t[0] == pytest.approx(22 + 13 * (1 - math.exp(-1)), abs=0.5)
def test_powered_home_stays_at_setpoint(): assert step_indoor(np.array([30.0]), 35.0, np.array([False]), np.array([8.0]), np.array([12.0]), 0.5)[0] == 22.0
def test_heat_only_patient_is_not_cold_unsafe(): assert not unsafe_temp(np.array([10.0]), np.array([50.0]), np.array(["heat"]))[0]
def test_drain_floors_at_zero(): assert drain(np.array([0.2]), np.array([1.0]), np.array([True]), np.array([False]), 0.5)[0] == 0.0
def test_moved_patient_does_not_drain(): assert drain(np.array([5.0]), np.array([1.0]), np.array([True]), np.array([True]), 0.5)[0] == 5.0

def test_charged_device_in_a_hot_home_is_not_own_backup():
    assert decide(pat(device="feeding_pump", temp_sensitive="heat"), 100.0, ctx(temp_unsafe=True, move=True)) == PlanState.MOVE
def test_hot_home_without_a_move_option_gets_resupply_not_own_backup():
    assert decide(pat(temp_sensitive="heat"), 100.0, ctx(temp_unsafe=True, move=False, delivery=True)) == PlanState.RESUPPLY
def test_unsafe_home_moves_first(): assert decide(pat(), 100.0, ctx(home_unsafe=True, move=True)) == PlanState.MOVE
def test_backup_covers_outage_plus_margin():
    assert decide(pat(), 60.0, ctx(restoration=48)) == PlanState.OWN_BACKUP
    assert decide(pat(), 59.0, ctx(restoration=48, delivery=True)) == PlanState.RESUPPLY
def test_no_delivery_no_move_is_urgent(): assert decide(pat(), 1.0, ctx(restoration=48)) == PlanState.URGENT
def test_moves_disabled_falls_back(): assert decide(pat(), 1.0, ctx(restoration=48, move=True, allow_moves=False)) == PlanState.URGENT
def test_dialysis_moves(): assert decide(pat(device="home_dialysis"), 0.0, ctx(move=True)) == PlanState.MOVE
def test_dialysis_is_never_own_backup(): assert decide(pat(device="home_dialysis"), 500.0, ctx()) == PlanState.URGENT
def test_hysteresis_needs_two_ticks_between_resupply_and_move():
    assert with_hysteresis(PlanState.RESUPPLY, PlanState.MOVE, 0) == (PlanState.RESUPPLY, 1)
    assert with_hysteresis(PlanState.RESUPPLY, PlanState.MOVE, 1) == (PlanState.MOVE, 0)
def test_urgent_is_immediate(): assert with_hysteresis(PlanState.RESUPPLY, PlanState.URGENT, 0) == (PlanState.URGENT, 0)

def test_moved_patient_is_not_at_risk(): assert not at_risk(np.array([0.0]), np.array([True]), np.array([True]), np.array([True]))[0]
def test_charged_but_hot_is_at_risk(): assert at_risk(np.array([50.0]), np.array([True]), np.array([False]), np.array([True]))[0]
def test_weighted_and_unweighted_hours():
    s = summarize(np.array([[True, False], [True, True]]), np.array([5.0, 1.0]), 0.5)
    assert s["risk_hours_unweighted"] == 1.5 and s["risk_hours_weighted"] == 5.5
```

## Done when

`uv run pytest tests/sim/test_temperature.py tests/sim/test_decision.py tests/sim/test_metrics.py -v`
passes, no number from the list above is hard-coded outside `a(...)`, and the pull request is open.
