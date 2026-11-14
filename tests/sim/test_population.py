import numpy as np

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
