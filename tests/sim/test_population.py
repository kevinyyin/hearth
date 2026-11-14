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


def test_residents_go_only_to_residential_costar_buildings():
    for bid, kind in [("1001", "multifamily"), ("1002", "senior_housing"), ("1003", "hotel"), ("B-SAMPLE", "multifamily")]:
        store.put("profile", bid, _surveyed(bid, kind))
    homes = {p.building_id for p in load_population("beryl_2024", 1)} - {None}
    assert homes == {"1001", "1002"}  # never hotels; never hand-made fixtures (ids that are not CoStar ids)


def test_device_mix_follows_the_cited_counts():
    from collections import Counter

    from hearth.config import a
    counts = a("population.device_counts")
    ps = load_population("beryl_2024", 1)
    got = Counter(p.device.value for p in ps)
    for device, n in counts.items():
        assert abs(got[device] / len(ps) - n / sum(counts.values())) < 0.01


def test_dialysis_backup_is_the_time_until_the_next_session_is_due():
    from hearth.config import a
    due = [p.backup_hours_on_hand for p in load_population("beryl_2024", 1) if p.device == "home_dialysis"]
    assert due and 0 <= min(due) and max(due) <= 24 * a("population.dialysis_due_within_days")


def test_synthetic_scenarios_never_use_surveyed_buildings():
    store.put("profile", "MF", _surveyed("MF", "multifamily"))
    assert all(p.building_id is None for p in load_population("sample", 1))  # committed outputs carry no CoStar data
