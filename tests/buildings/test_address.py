import pytest

from hearth.buildings import tools
from hearth.buildings.address import match_address, match_unit, norm_unit


@pytest.fixture(autouse=True)
def fixtures_on(monkeypatch):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")


def test_matches_a_spoken_address():
    assert match_address("1200", "Fixture Street")["building_id"] == "B-SAMPLE"
    assert match_address("1200", "fixture")["building_id"] == "B-SAMPLE"


def test_a_wrong_number_or_zip_matches_nothing():
    assert match_address("1201", "Fixture St") is None and match_address("1200", "Fixture St", "77003") is None


def test_several_matches_count_as_none(monkeypatch):
    two = [{"building_id": i, "address": "1200 Fixture St, Houston, TX 77002", "zip": "77002"} for i in "ab"]
    monkeypatch.setattr(tools, "costar_all", lambda: two)
    assert match_address("1200", "Fixture St") is None


@pytest.mark.parametrize("said,want", [("00-1410", "1410"), ("Apt 14-10", "1410"), ("#1410", "1410"), ("b12", "B12"), ("unit 0310", "310")])
def test_norm_unit(said, want):
    assert norm_unit(said) == want


def test_match_unit_finds_the_plan_and_building():
    rec = tools.costar_record("B-SAMPLE")
    assert match_unit(rec, "310") == {"unit": "00-0310", "plan": "1BR, 1BA - 700SF (fixture)", "beds": 1, "scan_ids": ["fixture-B-SAMPLE"], "building": "A"}
    assert match_unit(rec, "999") is None and match_unit({}, "1") is None
