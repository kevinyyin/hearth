from bhelpers import patient, profile

from evals.run_layers import rows
from hearth.contracts import Sourced


def test_each_row_adds_one_layer():
    p = profile("H", step_free=True, floors=4)  # step-free from the scan; CoStar lists no elevator for a hotel
    p.elevator_count = Sourced(value=1, source="matterport", confidence=0.5)  # only a scan shows one
    out = rows(p, patient(mobility="wheelchair_manual"), office="the building's office said so by phone at 3:42 PM")
    assert [r[0] for r in out] == ["CoStar", "+ aerial (Vexcel)", "+ scan (Matterport)", "+ building office call"]
    assert [r[1] for r in out] == [False, False, False, True]
    assert out[0][2] == "unverified access" and out[2][2] == "needs a call" and out[3][2] == "step-free entrance (matterport, confidence 0.9)"


def test_without_an_office_answer_the_last_row_says_so():
    out = rows(profile("H", step_free=True, floors=1), patient(mobility="wheelchair_manual"), office=None)
    assert out[3][0] == "+ building office call (no answer recorded)"
