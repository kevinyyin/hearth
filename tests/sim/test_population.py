import numpy as np
import pytest

from hearth import store
from hearth.buildings.profile import default_profile
from hearth.contracts import Sourced

from hearth.contracts import Patient
from hearth.population import inside, load_population


def test_population_is_deterministic():
    assert load_population("beryl_2024", 1) == load_population("beryl_2024", 1)


def test_population_total_matches_empower_within_masking():
    assert 20_000 < len(load_population("beryl_2024", 1)) < 26_000  # county sheet says 23,281


def test_patients_are_synthetic_contract_rows():
    ps = load_population("beryl_2024", 1)
    assert all(isinstance(p, Patient) and p.synthetic for p in ps) and len({p.patient_id for p in ps}) == len(ps)


def test_inside_unit_square():
    sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], float)
    assert inside(np.array([0.5, 1.5, -0.1]), np.array([0.5, 0.5, 0.5]), [sq]).tolist() == [True, False, False]


@pytest.fixture(autouse=True)
def _empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "hearth.db"))


def _surveyed(building_id, kind):
    p = default_profile(building_id, "test", 29.76, -95.37)
    return p.model_copy(update={"property_type": Sourced(value=kind, source="costar", confidence=0.9),
                                "floors": Sourced(value=5, source="costar", confidence=0.9)})


def test_residents_go_to_surveyed_homes_not_refuges():
    store.put("profile", "MF", _surveyed("MF", "multifamily")); store.put("profile", "SH", _surveyed("SH", "senior_housing"))
    homes = {p.building_id for p in load_population("beryl_2024", 1)} - {None}
    assert homes == {"MF"}  # senior housing and hotels are refuges in the simulation, never someone's dark home


def test_synthetic_scenarios_never_use_surveyed_buildings():
    store.put("profile", "MF", _surveyed("MF", "multifamily"))
    assert all(p.building_id is None for p in load_population("sample", 1))  # committed outputs carry no CoStar data
