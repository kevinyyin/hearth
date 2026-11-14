import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / "buildings"))
from bhelpers import profile, seed_pending_proposal  # noqa: E402

from api import live  # noqa: E402
from api.main import app  # noqa: E402
from hearth import store  # noqa: E402
from hearth.buildings import refuge  # noqa: E402
from hearth.contracts import Snapshot  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(refuge, "MEMORY_FILE", str(tmp_path / "memory.md"))


def test_runs_lists_the_sample():
    runs = client.get("/api/runs").json()
    assert any(r["run_id"] == "sample__p3__c20__s1" and r["crews"] == 20 for r in runs)


def test_meta_and_snapshot_validate():
    meta = client.get("/api/runs/sample__p3__c20__s1/meta").json()
    assert len(meta["ticks"]) == 2 and meta["center"] == [29.76, -95.37]
    Snapshot.model_validate(client.get("/api/runs/sample__p3__c20__s1/snapshots/0").json())


def test_events_filter_by_patient():
    all_events = client.get("/api/runs/sample__p3__c20__s1/events").json()
    pid = all_events[0]["patient_id"]
    assert all(e["patient_id"] == pid for e in client.get(f"/api/runs/sample__p3__c20__s1/events?patient_id={pid}").json())


def test_path_like_run_ids_are_404():
    assert client.get("/api/runs/..%2F..%2Fetc/meta").status_code == 404
    assert client.get("/api/runs/nope/snapshots/0").status_code == 404


def test_unknown_building_is_404():
    assert client.get("/api/buildings/NOPE").status_code == 404


def test_building_detail_before_and_after_survey():
    d = client.get("/api/buildings/B-SAMPLE").json()
    assert d["profile"] is None and d["image_url"].endswith("/api/buildings/B-SAMPLE/image")
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", floors=8, roof="dark", step_free=True))
    d = client.get("/api/buildings/B-SAMPLE").json()
    assert d["profile"]["floors"]["source"] == "costar" and any("8 stories" in line for line in d["brief"]["to_door"]) and set(d["layer_effects"]) == {"costar", "vexcel", "matterport"}
    assert client.get("/api/buildings/B-SAMPLE/image").headers["content-type"] == "image/png"


def test_buildings_list_marks_scans_and_surveys():
    rows = {r["building_id"]: r for r in client.get("/api/buildings").json()}
    assert rows["B-SAMPLE"]["has_scan"] and not rows["B-NOSCAN"]["has_scan"] and not rows["B-SAMPLE"]["surveyed"]


def test_consent_call_blocked_without_approval():
    assert client.post("/api/calls", json={"patient_id": "p1", "kind": "move_consent"}).status_code == 409


def test_reject_places_no_call(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "start_call", lambda *a, **k: calls.append(a) or "c1")
    seed_pending_proposal("P1")
    r = client.post("/api/proposals/P1/decision", json={"decision": "reject", "reason": "too far"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and calls == []


def test_approve_places_exactly_one_call(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "start_call", lambda *a, **k: calls.append(a) or "c1")
    seed_pending_proposal("P2")
    r = client.post("/api/proposals/P2/decision", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and len(calls) == 1 and calls[0][1] == "move_consent"
    assert client.post("/api/calls", json={"patient_id": "p1", "kind": "move_consent"}).status_code == 200


def test_deciding_twice_is_409():
    seed_pending_proposal("P3")
    client.post("/api/proposals/P3/decision", json={"decision": "reject", "reason": "no generator"})
    assert client.post("/api/proposals/P3/decision", json={"decision": "approve"}).status_code == 409
    assert client.post("/api/proposals/NOPE/decision", json={"decision": "approve"}).status_code == 404


def test_survey_streams_server_sent_events():
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", floors=8))
    with client.stream("GET", "/api/buildings/B-SAMPLE/survey") as r:
        body = "".join(r.iter_text())
    assert r.headers["content-type"].startswith("text/event-stream")
    assert body.startswith("data: ") and '"kind":"done"' in body and '"cached":true' in body


def test_propose_for_unknown_patient_is_404():
    assert client.post("/api/patients/nobody/propose").status_code == 404


def test_snapshots_are_served_gzipped():
    r = client.get("/api/runs/sample__p3__c20__s1/snapshots/0", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_stored_profile_is_labeled_cached_in_building_detail():
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", floors=8))
    assert client.get("/api/buildings/B-SAMPLE").json()["profile"]["cached"] is True


def test_profiles_stored_before_new_fields_get_them_as_unknown():
    old = profile("B-SAMPLE", floors=8).model_dump(mode="json")
    for f in ("unit_type", "unit_rooms", "hallway_width_m", "interior_steps"):
        old.pop(f)
    store.put("profile", "B-SAMPLE", old)
    d = client.get("/api/buildings/B-SAMPLE").json()
    assert d["profile"]["unit_type"]["source"] == "default" and d["profile"]["cached"] is True
