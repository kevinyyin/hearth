import pytest

from hearth import store
from hearth.buildings import agent
from hearth.buildings.bulk import profile_from_fields

REC = {"building_id": "123", "address": "1 Main St, Houston, TX 77002", "lat": 29.76, "lon": -95.37, "property_type": "multifamily",
       "floors": 9, "units": 200, "year_built": 1965, "construction": "masonry", "elevator_count": 5, "elevator_note": "passenger elevators listed"}
ATTRS = {"roof_material": "membrane", "tree_cover_fraction": 0.02, "capture_date": "2025-09-03T00:00:00"}


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("HEARTH_FIXTURES", "1")


def test_fields_profile_uses_costar_and_vexcel_with_sources():
    p = profile_from_fields(REC, ATTRS)
    assert p.method == "fields" and p.floors.value == 9 and p.floors.source == "costar" and p.elevator_count.value == 5
    assert p.tree_cover_fraction.source == "vexcel" and p.roof_tone.source == "vexcel" and p.roof_tone.value is not None
    assert any(e.field == "roof_tone" and "material class" in e.note for e in p.evidence)
    assert p.unit_type.source == "default" and p.step_free_entrance.source == "default" and p.layers_missing == ["matterport"]
    assert p.heat_time_constant_h != 8.0  # derived by code from the fields


def test_missing_vexcel_and_unknown_material_stay_unknown():
    p = profile_from_fields(REC | {"elevator_count": None}, None)
    assert set(p.layers_missing) == {"vexcel", "matterport"} and p.roof_tone.source == "default" and p.elevator_count.source == "default"
    assert profile_from_fields(REC, ATTRS | {"roof_material": "something new"}).roof_tone.source == "default"


class ExplodingGraph:
    def stream(self, *a, **k):
        raise RuntimeError("live survey ran")


def test_a_fields_profile_is_not_a_cache_hit_for_a_live_survey(monkeypatch):
    store.put("profile", "123", profile_from_fields(REC, ATTRS))
    monkeypatch.setattr(agent, "build_surveyor", lambda model=None: ExplodingGraph())
    last = list(agent.survey("123", REC["address"], REC["lat"], REC["lon"]))[-1]
    assert "live survey ran" in last.data["profile"]["error"]  # it tried the agent instead of returning the bulk profile
