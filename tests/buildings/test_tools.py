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
