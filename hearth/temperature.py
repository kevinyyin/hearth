"""Indoor temperature clock: heat index, dark-home drift toward outdoor, and per-patient unsafe check."""
import numpy as np

from hearth.config import a


def heat_index_c(temp_c, rh):
    t = temp_c * 9 / 5 + 32
    hi_f = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
            - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    # [()] turns a 0-d result back into a scalar so a float in gives a float out
    return np.where(temp_c < 26.7, temp_c, (hi_f - 32) * 5 / 9)[()]


def step_indoor(indoor_c, outdoor_c, dark, heat_tc, cold_tc, dt_h) -> np.ndarray:
    tc = np.where(outdoor_c > indoor_c, heat_tc, cold_tc)
    return np.where(dark, indoor_c + (outdoor_c - indoor_c) * dt_h / tc, a("temperature.setpoint_c"))


def unsafe_temp(indoor_c, rh, sensitivity) -> np.ndarray:
    heat = (heat_index_c(indoor_c, rh) > a("temperature.unsafe_heat_index_c")) & np.isin(sensitivity, ["heat", "both"])
    cold = (indoor_c < a("temperature.unsafe_cold_c")) & np.isin(sensitivity, ["cold", "both"])
    return heat | cold
