import math

import pytest
from bhelpers import fields, profile

from hearth.buildings.profile import (default_profile, finalize, hours_to_unsafe, layer_effects, service_minutes,
                                      time_constants)


def test_default_profile_gives_default_constants():
    p = finalize(default_profile("B", "x", 0, 0))
    assert (p.heat_time_constant_h, p.cold_time_constant_h) == (8.0, 12.0)
    assert all(getattr(p, f).source == "default" for f in ("floors", "roof_tone", "step_free_entrance"))
    assert set(p.layers_missing) == {"costar", "vexcel", "matterport"}


def test_dark_old_unshaded_heats_faster_than_light_new_shaded():
    assert time_constants(fields(roof="dark", year=1974, tree=0.05))[0] < time_constants(fields(roof="light", year=2010, tree=0.6))[0]


def test_heat_constant_is_clamped():
    assert 3 <= time_constants(fields(roof="dark", year=1950, construction="wood"))[0] <= 24
    assert time_constants(fields(roof="light", year=2020, construction="masonry", tree=1.0))[0] <= 24


def test_masonry_holds_temperature_longer_in_cold_too():
    assert time_constants(fields(construction="masonry"))[1] > time_constants(fields(construction="wood"))[1]


def test_service_minutes_grow_with_floor_when_elevator_out():
    p = profile(elevators=1)
    assert service_minutes(p, 3, False) == 22 and service_minutes(p, 3, True) == 10
    assert service_minutes(profile(elevators=0), 3, True) == 22


def test_hours_to_unsafe_matches_closed_form():
    assert hours_to_unsafe(8.0) == pytest.approx(8.0 * math.log((35 - 22) / (35 - 32)), rel=1e-6)
    assert hours_to_unsafe(8.0, outdoor_c=30.0) == math.inf


def test_layer_effects_show_what_vexcel_changed():
    p = finalize(profile(roof="dark", tree=0.0))
    fx = layer_effects(p)
    assert fx["vexcel"] > hours_to_unsafe(p.heat_time_constant_h) and set(fx) == {"costar", "vexcel", "matterport"}
    assert fx["matterport"] == pytest.approx(hours_to_unsafe(p.heat_time_constant_h))
