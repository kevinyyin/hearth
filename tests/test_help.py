"""The help loop through the API, on the fixture buildings, with the model call patched out."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / "buildings"))
from bhelpers import profile  # noqa: E402

from api.main import app  # noqa: E402
from hearth import dispatch, store  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    store.put("profile", "H-LEVEL", profile("H-LEVEL", step_free=True, floors=5, elevators=2))
    store.put("profile", "H-STEPS", profile("H-STEPS", floors=3))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps(
        {"order": [{"patient_id": r["patient_id"], "reason": f"model says {r['patient_id']}"} for r in rows]}))


def crew(name, **over):
    return client.put(f"/api/crews/{name}", json={"base_building_id": "B-NOSCAN", "vehicle": "car", "equipment": []} | over)


job = lambda name: client.get(f"/api/crews/{name}/job").json()["job"]


def act(name, action, patient_id=None):
    """A crew's button press names the resident on the card it was shown."""
    patient_id = patient_id or (job(name) or {"request": {"patient_id": "nobody"}})["request"]["patient_id"]
    return client.post(f"/api/crews/{name}/job", json={"action": action, "patient_id": patient_id})


def test_the_loop_end_to_end():
    assert client.get("/api/crews/Alpha/job").json() == {"crew": None, "job": None, "staging": None}
    assert crew("Alpha").json()["lat"] == 29.753 and crew("Bravo", base_building_id="H-LEVEL", vehicle="van").status_code == 200
    assert client.get("/api/patients/p4/help").json() == {"state": None, "steps": [], "window": None, "refuge_note": None}

    assert client.post("/api/patients/p4/help").json()["state"] == "offered"
    assert client.post("/api/patients/p2/help").json()["state"] == "offered"
    mine = job("Alpha")
    assert mine["request"]["patient_id"] == "p4" and mine["request"]["reason"] == "model says p4"
    assert mine["patient"]["device"] == "oxygen" and mine["home"] is None and mine["building_id"] == "B-SAMPLE"
    assert mine["address"] == client.get("/api/buildings/B-SAMPLE").json()["address"] and 0 < mine["km"] < 3
    assert mine["request"]["refuge"]["building_id"] == "H-STEPS" and job("Bravo")["request"]["patient_id"] == "p2"

    assert act("Alpha", "accept").json()["job"]["request"]["state"] == "accepted"
    seen = client.get("/api/patients/p4/help").json()
    assert seen["state"] == "accepted" and "Alpha has accepted your ride" in seen["steps"][2]["text"] and len(seen["window"]) == 2
    for step in ("arrived", "picked_up"):
        assert act("Alpha", step).status_code == 200
    assert act("Alpha", "dropped_off").json()["job"] is None  # nothing else is waiting for this crew
    assert client.get("/api/patients/p4/help").json()["state"] == "dropped_off"

    assert client.post("/api/patients/p3/help").json()["state"] == "waiting"  # bedbound: no stretcher on duty
    assert client.post("/api/patients/demo-1/help").json()["state"] == "waiting"  # power wheelchair: no lift on duty
    view = client.get("/api/dispatch").json()
    assert [(r["request"]["patient_id"], r["request"]["blocked"] != "") for r in view["requests"]] == [
        ("p3", True), ("demo-1", True), ("p2", False), ("p4", False)]  # needs a person first, then live, then ended
    assert view["requests"][1]["mobility"] == "wheelchair_power" and view["requests"][1]["address"]
    assert {c["crew"]["crew_id"]: c["patient_id"] for c in view["crews"]} == {"Alpha": None, "Bravo": "p2"}
    assert client.post("/api/dispatch/p3/handled").json()["state"] == "handled"
    assert client.get("/api/patients/p3/help").json()["steps"][1]["text"] == "A person at the health department has taken over your request."

    assert client.post("/api/patients/p2/safe").json()["state"] == "safe" and job("Bravo") is None


def test_resident_routes_never_carry_the_models_reason():
    crew("Alpha")
    for r in (client.post("/api/patients/p4/help"), client.get("/api/patients/p4/help"), client.post("/api/patients/p4/safe")):
        assert r.status_code == 200 and "reason" not in r.text and "model says" not in r.text
    assert dispatch.request("p4").reason == "model says p4"


def test_status_codes():
    crew("Alpha")
    assert client.post("/api/patients/nobody/help").status_code == 404 and client.get("/api/patients/nobody/help").status_code == 404
    assert client.post("/api/patients/p4/help").status_code == 200
    assert client.post("/api/patients/p4/help").status_code == 409  # a double press
    assert act("Alpha", "picked_up").status_code == 409  # out of order
    assert act("Alpha", "fly").status_code == 422
    assert act("Alpha", "accept", patient_id="p2").status_code == 409  # a stale card naming another resident
    assert client.post("/api/crews/Alpha/job", json={"action": "accept"}).status_code == 422  # the resident must be named
    assert client.post("/api/dispatch/nobody/handled").status_code == 409  # no live request to take over
    for step in ("accept", "arrived", "picked_up"):
        act("Alpha", step)
    assert client.post("/api/patients/p4/safe").status_code == 409  # already riding
    assert crew("Alpha", base_building_id="NOPE").status_code == 422
    assert crew("Alpha", vehicle="bike").status_code == 422 and crew("Alpha", equipment=["laser"]).status_code == 422
    assert crew("a$b").status_code == 422 and client.get("/api/crews/a$b/job").status_code == 422
    assert job("Alpha")["request"]["state"] == "riding"  # none of the refused calls changed anything


def test_polling_the_tracker_does_not_rewrite_the_patient_record(monkeypatch):
    client.get("/api/patients/p4/help")
    writes = []
    real = store.put
    monkeypatch.setattr(store, "put", lambda kind, id, obj: writes.append(kind) or real(kind, id, obj))
    assert client.get("/api/patients/p4/help").status_code == 200 and "patient" not in writes


def test_approving_a_refuge_proposal_makes_it_the_drop_off_and_offers_a_crew(monkeypatch):
    from api import live
    from bhelpers import seed_pending_proposal

    monkeypatch.setattr(live, "start_call", lambda *a, **k: "c1")
    monkeypatch.setattr(live, "dial", lambda call_id: None)
    store.delete("profile", "H-LEVEL")  # the only step-free refuge is unknown to code
    crew("Alpha", vehicle="wheelchair_van", equipment=["wheelchair_lift"])
    assert client.post("/api/patients/p1/help").json()["state"] == "waiting"
    assert dispatch.request("p1").blocked.startswith("no refuge")
    seed_pending_proposal("P-1", "p1")  # the refuge agent found H-LEVEL
    assert client.post("/api/proposals/P-1/decision", json={"decision": "approve"}).status_code == 200
    r = dispatch.request("p1")
    assert r.state == "offered" and r.refuge.building_id == "H-LEVEL" and r.blocked == "" and job("Alpha")["request"]["patient_id"] == "p1"
