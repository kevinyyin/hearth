import pytest

from hearth.buildings import tools
from hearth.buildings.tools import (cached, costar_record, costar_search, matterport_embed_url,
                                    matterport_panoramas, vexcel_attributes, vexcel_image)


@pytest.fixture(autouse=True)
def fixtures_on(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setattr(tools, "CACHE_ROOT", tmp_path)


def test_missing_building_returns_none_not_error():
    assert costar_record("NOPE") is None and matterport_panoramas("NOPE") == [] and matterport_embed_url("NOPE") is None
    assert vexcel_image("NOPE", 0, 0) is None and vexcel_attributes(0.0, 0.0) is None


def test_cache_hit_skips_fetch():
    calls = []
    f = lambda: calls.append(1) or {"a": 1}
    assert cached("B1", "costar", f) == ({"a": 1}, False)
    assert cached("B1", "costar", f) == ({"a": 1}, True) and len(calls) == 1


def test_cache_never_stores_none():
    calls = []
    f = lambda: calls.append(1)
    assert cached("B1", "vexcel", f) == (None, False) and cached("B1", "vexcel", f) == (None, False) and len(calls) == 2


def test_fixture_building_has_three_layers():
    assert costar_record("B-SAMPLE")["floors"] == 8 and vexcel_image("B-SAMPLE", 0, 0).exists() and matterport_panoramas("B-SAMPLE")
    assert vexcel_attributes(29.7604, -95.3698)["roof_tone"] == "dark"
    assert matterport_panoramas("B-NOSCAN") == []


def test_search_filters_type_and_radius():
    ids = [r["building_id"] for r in costar_search(["multifamily"], (29.7604, -95.3698), 0.5)]
    assert "B-SAMPLE" in ids and "B-NOSCAN" not in ids          # B-NOSCAN is ~1.2 km away
    assert costar_search(["hotel"], (29.7604, -95.3698), 0.5) == []


def test_path_like_ids_are_rejected():
    with pytest.raises(ValueError):
        costar_record("../../etc")


def raw(**over):
    return {"id": 1, "propertyType": 11, "constructionStatus": 1, "primaryAddress": {
        "streetNumber": "1", "streetName": "Main", "city": "Houston", "state": "TX", "postcode": "77002", "latitude": 29.7, "longitude": -95.3}} | over


def test_normalize_reads_buildings_walkup_and_floor_plans():
    n = tools.normalize_costar(raw(propertyApartment={"numBuildings": 3, "isWalkup": False, "models": [
        {"modelName": "The Avondale", "numBeds": 1, "units": [{"unitNumber": "00-1410", "buildingName": None}],
         "attachments": [{"videoExternalReferenceType": 36, "videoKey": "vkx"}]},
        {"modelName": "Empty", "numBeds": 2, "units": [], "attachments": []}]}))
    assert (n["num_buildings"], n["walkup"]) == (3, False)
    assert n["floor_plans"] == [{"name": "The Avondale", "beds": 1, "scan_ids": ["vkx"], "units": [{"number": "00-1410", "building": None}]}]


@pytest.mark.parametrize("status,existing", [(1, True), (2, False), (3, False), (None, True)])
def test_a_closed_hotel_is_not_existing(status, existing):
    assert tools.normalize_costar(raw(propertyType=1, propertyHospitality={"operatingStatus": status}))["existing"] is existing


def test_matterport_rooms_can_be_limited_to_some_scans(monkeypatch):
    monkeypatch.delenv("HEARTH_FIXTURES")
    monkeypatch.setenv("MATTERPORT_API_KEY", "k"), monkeypatch.setenv("MATTERPORT_API_TOKEN", "t")
    asked = []

    class R:
        def raise_for_status(self): pass
        def json(self): return {"data": {"model": None}}

    monkeypatch.setattr(tools.httpx, "post", lambda url, json, **kw: asked.append(json["variables"]["id"]) or R())
    tools.matterport_rooms("anything", model_ids=["m1", "m2"])
    assert asked == ["m1", "m2"]
