import pytest
from fastapi.testclient import TestClient

from api.main import app
from hearth import store
from hearth.buildings import tools

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))


HOME = {"patient_id": "demo-1", "building_id": "B-SAMPLE", "ok_without_h": 4, "backup_plan": "spare battery", "size": "microwave",
        "scan_id": None, "note": "bedroom at the back",
        "outside": [{"kind": "park", "x": 0.25, "y": 0.5}, {"kind": "route", "x": 0.3, "y": 0.6}], "inside": []}
INSIDE = [{"kind": "machine", "position": {"x": 2.9, "y": 0.7, "z": 0.16}, "normal": {"x": 0, "y": 1, "z": 0}}]
put = lambda body, pid="demo-1": client.put(f"/api/patients/{pid}/home", json=body)


def test_home_round_trip_and_replace():
    assert client.get("/api/patients/demo-1/home").json()["home"] is None
    assert put(HOME).status_code == 200
    got = client.get("/api/patients/demo-1/home").json()
    assert got["home"]["outside"][1] == {"kind": "route", "x": 0.3, "y": 0.6} and got["patient"]["device"] == "feeding_pump"
    put(HOME | {"note": "moved to the den"})
    assert client.get("/api/patients/demo-1/home").json()["home"]["note"] == "moved to the den"
    assert store.get("patient", "demo-1")["backup_hours_on_hand"] == 4.0  # the patient record is untouched


@pytest.mark.parametrize("bad", [
    {"outside": [{"kind": "park", "x": 1.2, "y": 0.5}]},
    {"outside": [{"kind": "door", "x": 0.2, "y": 0.5}]},
    {"outside": [{"kind": "park", "x": 0.1, "y": 0.1}] * 51},
    {"size": "custom"},
    {"size": "custom", "size_cm": [40, 0, 30]},
    {"inside": INSIDE},  # inside pins with no scan chosen
    {"ok_without_h": -1},
])
def test_home_validation(bad):
    assert put(HOME | bad).status_code == 422


def test_scan_must_belong_to_the_building(monkeypatch):
    monkeypatch.setattr(tools, "matterport_scan_ids", lambda b: ["m1", "m2"])
    assert put(HOME | {"scan_id": "zzz"}).status_code == 422
    far = [{"kind": "machine", "position": {"x": 4344.1, "y": -6955.9, "z": 0}, "normal": {"x": 0, "y": 1, "z": 0}}]
    assert put(HOME | {"scan_id": "m2", "inside": far}).status_code == 422
    assert put(HOME | {"scan_id": "m2", "inside": INSIDE}).json()["inside"][0]["kind"] == "machine"


def test_unknown_patient_building_and_mismatched_id():
    assert put(HOME | {"patient_id": "nobody"}, pid="nobody").status_code == 404
    assert put(HOME | {"building_id": "NOPE"}).status_code == 422
    assert put(HOME, pid="demo-2").status_code == 400


def test_homes_list_demo_patients_and_building_detail():
    put(HOME)
    row = client.get("/api/homes").json()[0]
    assert row["home"]["patient_id"] == "demo-1" and row["patient"]["mobility"] == "wheelchair_power"
    assert row["address"] == client.get("/api/buildings/B-SAMPLE").json()["address"]
    demo = client.get("/api/demo-patients").json()
    ids = {p["patient_id"] for p in demo}
    # only personas whose building exists in the data being served: demo-2 lives in a real building, not a fixture
    assert "demo-1" in ids and "demo-2" not in ids and all(p["synthetic"] for p in demo)
    d = client.get("/api/buildings/B-SAMPLE").json()
    assert d["scan_ids"] == [] and "scan_sdk_key" in d


def test_a_size_that_is_not_a_number_is_refused_and_not_stored():
    quiet = TestClient(app, raise_server_exceptions=False)  # the error reply cannot carry NaN, so it may be a 500
    body = '{"patient_id": "demo-1", "building_id": "B-SAMPLE", "ok_without_h": 4, "size": "microwave", "size_cm": [NaN, Infinity, -5]}'
    r = quiet.put("/api/patients/demo-1/home", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code >= 400
    assert store.get("home", "demo-1") is None
    assert put(HOME | {"size_cm": [40, 0, 30]}).status_code == 422  # checked for every size, not only custom


def test_a_stored_home_that_no_longer_validates_is_skipped():
    put(HOME)
    store.put("home", "demo-2", {"patient_id": "demo-2", "building_id": "B-SAMPLE"})  # e.g. saved before a field became required
    assert [r["home"]["patient_id"] for r in client.get("/api/homes").json()] == ["demo-1"]
    assert client.get("/api/patients/demo-2/home").json()["home"] is None


PERSON = {"name": "Sam Rivera", "relation": "daughter", "phone": "555-0100", "note": "has a key"}  # invented, like the resident
BAD_PEOPLE = [[{"name": "  "}], [{"name": "Sam", "phone": "call me maybe"}], [PERSON] * 6, [{"name": "x" * 81}]]


def test_contacts_round_trip_and_reach_the_responder():
    assert put(HOME | {"contacts": [PERSON]}).status_code == 200
    assert client.get("/api/patients/demo-1/home").json()["home"]["contacts"] == [PERSON]
    assert client.get("/api/homes").json()[0]["home"]["contacts"][0]["name"] == "Sam Rivera"
    put(HOME)  # a home saved without the field has none
    assert client.get("/api/patients/demo-1/home").json()["home"]["contacts"] == []


@pytest.mark.parametrize("bad", BAD_PEOPLE)
def test_contact_validation(bad):
    assert put(HOME | {"contacts": bad}).status_code == 422


def test_the_resident_names_their_device_and_says_whether_it_can_be_moved():
    assert put(HOME | {"device_name": "Inogen One G5 concentrator", "movable": False}).status_code == 200
    home = client.get("/api/patients/demo-1/home").json()["home"]
    assert home["device_name"] == "Inogen One G5 concentrator" and home["movable"] is False
    put(HOME)  # a home saved before these fields existed
    home = client.get("/api/patients/demo-1/home").json()["home"]
    assert home["device_name"] == "" and home["movable"] is None
    assert put(HOME | {"device_name": "x" * 121}).status_code == 422


HELPER = {"name": "Jo Rivera", "relation": "husband", "phone": "", "note": "can swap the oxygen tank"}


def test_people_at_home_round_trip_and_reach_the_responder():
    assert put(HOME | {"helpers": [HELPER], "contacts": [PERSON]}).status_code == 200
    home = client.get("/api/homes").json()[0]["home"]
    assert home["helpers"] == [HELPER] and home["contacts"] == [PERSON]  # two separate lists
    put(HOME)
    assert client.get("/api/patients/demo-1/home").json()["home"]["helpers"] == []


@pytest.mark.parametrize("bad", BAD_PEOPLE)
def test_people_at_home_validation(bad):
    assert put(HOME | {"helpers": bad}).status_code == 422
