from conftest import ctx, pat

from hearth.contracts import PlanState
from hearth.decision import decide, with_hysteresis


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
