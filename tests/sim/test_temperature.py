import math

import numpy as np
import pytest

from hearth.devices import drain
from hearth.temperature import heat_index_c, step_indoor, unsafe_temp


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
