"""Staging lots. Fixture world: every p* and demo-1 resident lives in B-SAMPLE (ZIP 77002)."""
import json

import pytest

from hearth import dispatch, staging, store
from hearth.buildings import tools
from hearth.config import ROOT
from hearth.contracts import Home, Patient

CENTER = (29.76, -95.37)


def lot(i, t="retail", spaces=300, zip="77027", lat=29.74, lon=-95.45, name=None):
    return {"building_id": i, "name": name, "address": f"{i} Lot St, Houston, TX {zip}", "zip": zip, "lat": lat, "lon": lon,
            "property_type": t, "surface_spaces": spaces, "lot_acres": 4.0}


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    for r in json.loads((ROOT / "data/demo/patients.json").read_text()):
        store.put("patient", r["patient_id"], Patient(**r))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps({"order": [{"patient_id": r["patient_id"], "reason": "x"} for r in rows]}))
    monkeypatch.setattr(tools, "costar_all", lambda: [lot("L1"), lot("L2", zip="77002")])


def test_only_big_non_apartment_lots_outside_the_dark_zips_qualify():
    rows = [lot("ok"), lot("apt", t="multifamily"), lot("senior", t="senior_housing"), lot("small", spaces=99),
            lot("unknown", spaces=None), lot("dark", zip="77002"), lot("nozip", zip=None), {"building_id": "old-fixture", "property_type": "hotel"}]
    assert [o["building_id"] for o in staging.candidates(rows, {"77002"}, CENTER)] == ["ok"]


def test_nearest_three_first_with_distance_and_a_name():
    rows = [lot("far", lat=29.95), lot("near", lat=29.77, lon=-95.37, name="Target"), lot("mid", lat=29.80), lot("farthest", lat=30.02)]
    out = staging.candidates(rows, set(), CENTER)
    assert [o["building_id"] for o in out] == ["near", "mid", "far"]
    assert (out[0]["name"], out[0]["km"]) == ("Target", 1.1)
    assert out[1]["name"] == "mid Lot St, Houston, TX 77027"  # no building name: the address stands in
    assert set(out[0]) == {"building_id", "name", "address", "zip", "property_type", "surface_spaces", "lot_acres", "km"}


def test_nothing_to_centre_on_means_no_options():
    assert staging.scene() is None and staging.options() == []


def test_with_no_open_request_registered_homes_set_the_centre_and_no_zip_is_dark():
    store.put("home", "p1", Home(patient_id="p1", building_id="B-SAMPLE", ok_without_h=4))
    assert [o["building_id"] for o in staging.options()] == ["L1", "L2"]


def test_options_avoid_a_requesters_zip_and_the_choice_is_kept():
    dispatch.open_request("demo-1")
    assert [o["building_id"] for o in staging.options()] == ["L1"]
    assert staging.choose("L1")["building_id"] == "L1"
    assert staging.chosen()["stale"] is False
    with pytest.raises(ValueError):
        staging.choose("L2")
    staging.clear()
    assert staging.chosen() is None


def test_a_chosen_lot_whose_zip_gets_a_request_is_marked_stale():
    store.put("staging", "current", lot("L2", zip="77002") | {"km": 1.0})
    dispatch.open_request("demo-1")
    assert staging.chosen()["stale"] is True


def test_no_chosen_lot_costs_no_scene_and_a_view_reads_the_scene_once(monkeypatch):
    calls, real = [], staging.scene
    monkeypatch.setattr(staging, "scene", lambda: calls.append(1) or real())
    assert staging.chosen() is None and calls == []  # crew pages poll this every 3 seconds
    staging.view()
    assert len(calls) == 1


def test_the_view_says_what_the_distance_is_measured_from():
    assert staging.view() == {"chosen": None, "options": [], "basis": None}
    store.put("home", "p1", Home(patient_id="p1", building_id="B-SAMPLE", ok_without_h=4))
    assert staging.view()["basis"] == "registered homes"
    dispatch.open_request("demo-1")
    view = staging.view()
    assert (view["basis"], [o["building_id"] for o in view["options"]]) == ("open requests", ["L1"])
