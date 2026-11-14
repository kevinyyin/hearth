import numpy as np

from hearth.metrics import at_risk, summarize


def test_moved_patient_is_not_at_risk(): assert not at_risk(np.array([0.0]), np.array([True]), np.array([True]), np.array([True]))[0]
def test_charged_but_hot_is_at_risk(): assert at_risk(np.array([50.0]), np.array([True]), np.array([False]), np.array([True]))[0]
def test_weighted_and_unweighted_hours():
    s = summarize(np.array([[True, False], [True, True]]), np.array([5.0, 1.0]), 0.5)
    assert s["risk_hours_unweighted"] == 1.5 and s["risk_hours_weighted"] == 5.5
