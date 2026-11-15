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
    # .env may hold the hosted settings; tests run as the local API, with no password and no Supabase
    for k in ("HEARTH_PASSWORD", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "HEARTH_DATABASE_URL", "HEARTH_WEB_ORIGIN_REGEX"):
        monkeypatch.delenv(k, raising=False)
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
    assert client.get("/api/buildings/B-SAMPLE/entrance").status_code == 404  # fixtures ask no vision model


def test_buildings_list_marks_scans_and_surveys():
    rows = {r["building_id"]: r for r in client.get("/api/buildings").json()}
    assert rows["B-SAMPLE"]["has_scan"] and not rows["B-NOSCAN"]["has_scan"] and not rows["B-SAMPLE"]["surveyed"]


def test_consent_call_blocked_without_approval():
    assert client.post("/api/calls", json={"patient_id": "p1", "kind": "move_consent"}).status_code == 409


def test_reject_places_no_call(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "start_call", lambda *a, **k: calls.append(a) or "c1")
    monkeypatch.setattr(live, "dial", lambda call_id: calls.append(call_id))
    seed_pending_proposal("P1")
    r = client.post("/api/proposals/P1/decision", json={"decision": "reject", "reason": "too far"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and calls == []


def test_approve_places_exactly_one_call(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "start_call", lambda *a, **k: calls.append(a) or "c1")
    monkeypatch.setattr(live, "dial", lambda call_id: calls.append(("dial", call_id)) or "conv1")
    seed_pending_proposal("P2")
    r = client.post("/api/proposals/P2/decision", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["phone_call"] == "conv1"
    assert len(calls) == 2 and calls[0][1] == "move_consent" and calls[1] == ("dial", "c1")
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


def test_a_finished_live_survey_is_recorded_for_replay(monkeypatch):
    from api import main
    from hearth.contracts import TraceEvent

    events = [TraceEvent(seq=0, t=0.5, kind="tool", agent="costar", text="costar_record(building_id=B-SAMPLE)"),
              TraceEvent(seq=1, t=2.0, kind="done", agent="surveyor", text="profile written", data={"profile": {"error": None}})]
    monkeypatch.setattr(main, "survey", lambda *a, **k: iter(events))
    assert client.get("/api/buildings/B-SAMPLE/survey/recording").status_code == 404
    with client.stream("GET", "/api/buildings/B-SAMPLE/survey?fresh=true") as r:
        "".join(r.iter_text())
    assert [e["t"] for e in client.get("/api/buildings/B-SAMPLE/survey/recording").json()["events"]] == [0.5, 2.0]


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


def test_loaded_patients_are_stored_for_the_voice_lane():
    from api.main import _patient
    _patient("demo-1")
    assert store.get("patient", "demo-1")["mobility"] == "wheelchair_power"


def test_records_only_profiles_do_not_count_as_surveyed():
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", floors=8).model_copy(update={"method": "fields"}))
    rows = {r["building_id"]: r for r in client.get("/api/buildings").json()}
    assert rows["B-SAMPLE"]["surveyed"] is False and rows["B-SAMPLE"]["records_only"] is True
    assert client.get("/api/buildings/B-SAMPLE").json()["profile"]["method"] == "fields"


def test_tunneled_requests_reach_only_the_voice_route():
    seed_pending_proposal("P9")
    for h in ({"x-forwarded-for": "203.0.113.7"}, {"cf-connecting-ip": "203.0.113.7"}):
        assert client.post("/api/proposals/P9/decision", json={"decision": "approve"}, headers=h).status_code == 403
    assert store.get("proposal", "P9")["status"] == "pending"
    r = client.post("/voice/v1/chat/completions", json={"messages": []}, headers={"x-forwarded-for": "203.0.113.7"})
    assert r.status_code == 200


def test_a_run_that_lives_only_in_storage_is_served(monkeypatch, tmp_path):
    from hearth import remote
    src = tmp_path / "remote" / "results" / "cloud_run"
    (src / "snapshots").mkdir(parents=True)
    (src / "meta.json").write_text('{"run_id": "cloud_run", "scenario": "beryl_2024", "policy": "p3", "crews": 20, "seed": 1, "ticks": [], "center": [29.76, -95.37]}')
    (src / "snapshots" / "0.json").write_text('{"t": "2024-07-08T06:00:00Z", "patients": [], "crews": [], "depots": []}')
    (src / "events.jsonl").write_text('{"t": "2024-07-08T06:00:00Z", "type": "power_lost", "patient_id": "x", "data": {}}\n')
    monkeypatch.setattr(remote, "listdir", lambda prefix: ["cloud_run"] if prefix == "results" else [])
    monkeypatch.setattr(remote, "fetch", lambda path: (tmp_path / "remote" / path) if (tmp_path / "remote" / path).exists() else None)
    assert any(r["run_id"] == "cloud_run" for r in client.get("/api/runs").json())
    assert client.get("/api/runs/cloud_run/meta").json()["policy"] == "p3"
    Snapshot.model_validate(client.get("/api/runs/cloud_run/snapshots/0").json())
    assert client.get("/api/runs/cloud_run/events?patient_id=x").json()[0]["type"] == "power_lost"
    assert client.get("/api/runs/cloud_run/snapshots/5").status_code == 404


def test_hosted_api_needs_the_shared_password(monkeypatch):
    monkeypatch.setenv("HEARTH_PASSWORD", "open sesame")
    origin = {"Origin": "http://localhost:3000"}
    r = client.get("/api/runs", headers=origin)
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "http://localhost:3000"  # the browser can read it
    assert client.get("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer open sesame", "x-forwarded-for": "203.0.113.7"}).status_code == 200
    assert client.options("/api/runs", headers=origin | {"Access-Control-Request-Method": "GET"}).status_code == 200
    assert client.post("/voice/v1/chat/completions", json={"messages": []}).status_code == 200  # its own secret
    assert client.post("/photon/webhook", content=b"{}").json()["detail"] == "bad or missing webhook signature"  # its own check


def test_county_patients_come_from_a_json_copy_in_storage(monkeypatch, tmp_path):
    import json
    import api.main as m
    from bhelpers import patient as make_patient
    from hearth import remote
    copy = tmp_path / "patients.json"
    copy.write_text(json.dumps([make_patient(patient_id="SIM-77002-0001").model_dump(mode="json")]))
    monkeypatch.setattr(m, "PATIENTS_FILE", tmp_path / "absent.parquet")
    monkeypatch.setattr(remote, "fetch", lambda path: copy if path == "processed/patients_beryl_2024_s1.json" else None)
    assert m._patient("SIM-77002-0001").patient_id == "SIM-77002-0001"


def test_web_origins_can_be_a_pattern_for_preview_deployments():
    import importlib
    import api.main as m
    os_env = {"HEARTH_WEB_ORIGIN_REGEX": r"https://hearth[a-z0-9-]*\.vercel\.app"}
    import os
    old = {k: os.environ.get(k) for k in os_env}
    os.environ.update(os_env)
    try:
        fresh = TestClient(importlib.reload(m).app)
        r = fresh.get("/api/runs", headers={"Origin": "https://hearth-abc123-kyin.vercel.app"})
        assert r.headers.get("access-control-allow-origin") == "https://hearth-abc123-kyin.vercel.app"
        assert "access-control-allow-origin" not in fresh.get("/api/runs", headers={"Origin": "https://evil.example"}).headers
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
        importlib.reload(m)


PHONE_FACTS = {"device": "oxygen", "device_words": "oxygen", "building_id": "B-SAMPLE", "address": "1200 Fixture St, Houston, TX 77002",
               "backup_hours": 4.0, "floor": 3, "unit": "00-0310"}


def phone_registrant(phone="+15550100002"):
    from hearth.messaging import registry
    return registry.save({"patient_id": None, "ctx": {"phone": phone}, "facts": dict(PHONE_FACTS)})


def test_a_phone_registrant_is_found_by_the_patient_routes():
    pid = phone_registrant()
    r = client.get(f"/api/patients/{pid}/home")
    assert r.status_code == 200 and r.json()["home"]["source"] == "phone" and r.json()["patient"]["patient_id"] == pid


def test_registrations_lists_phone_homes_and_calls_that_need_a_person():
    pid = phone_registrant()
    store.put("call", "C-9", {"call_id": "C-9", "kind": "register", "patient_id": None, "status": "handoff", "ctx": {"phone": "+15550100009"},
                              "facts": {"device": "oxygen"}, "started_at": 1.0})
    out = client.get("/api/registrations").json()
    assert [r["patient"]["patient_id"] for r in out["registered"]] == [pid] and out["registered"][0]["address"].startswith("1200 Fixture St")
    assert out["needs_person"] == [{"call_id": "C-9", "phone": "+15550100009", "facts": {"device": "oxygen"}, "status": "handoff", "started_at": 1.0}]


def test_a_browser_register_call_needs_a_listed_phone(monkeypatch):
    assert client.post("/api/calls", json={"kind": "register", "phone": "+15550100002"}).status_code == 403
    monkeypatch.setenv("HEARTH_DEMO_CALLERS", "+15550100002")
    r = client.post("/api/calls", json={"kind": "register", "phone": "+15550100002"})
    assert r.status_code == 200 and store.get("call", r.json()["call_id"])["kind"] == "register"


def test_storm_route_takes_a_round_and_defaults_to_a_week_out(monkeypatch):
    assert client.post("/api/storm").json() == {"dialed": [], "failed": []}  # an old client sends no body
    rounds = []
    monkeypatch.setattr("hearth.messaging.registry.storm", lambda round: rounds.append(round) or {"dialed": [], "failed": []})
    assert [client.post("/api/storm", **kw).status_code for kw in ({}, {"json": {"round": "outage"}}, {"json": {"round": "never"}})] == [200, 200, 422]
    assert rounds == ["week", "outage"]


def test_calling_an_unlisted_building_is_refused(monkeypatch):
    assert client.post("/api/buildings/H-LEVEL/call").status_code == 403
    assert client.get("/api/buildings/H-LEVEL").json()["can_call"] is False
    monkeypatch.setenv("HEARTH_BUILDING_PHONES", "H-LEVEL=+15551230000")
    r = client.post("/api/buildings/H-LEVEL/call")
    assert r.status_code == 200 and store.get("call", r.json()["call_id"])["kind"] == "building_check" and r.json()["conversation_id"] is None
    assert client.get("/api/buildings/H-LEVEL").json()["can_call"] is True


def test_sim_day_returns_a_side_and_refuses_runaway_requests():
    import json
    from hearth.config import ROOT
    fx = json.loads((ROOT / "tests/fixtures/sim_day.json").read_text())
    r = client.post("/api/sim/day", json={"households": fx["households"][:20], "constants": fx["constants"]})
    assert r.status_code == 200 and len(r.json()["legs"]) == 15 and r.json()["stops"] >= 20
    big = [fx["households"][0]] * 100_000
    assert client.post("/api/sim/day", json={"households": big, "constants": fx["constants"]}).status_code == 422
    for bad in ({"dt": 0}, {"runHours": 10_000}, {"capacity": 0}, {"cruise": 0}, {"stations": []}, {"crewsPerStation": 99}):
        assert client.post("/api/sim/day", json={"households": [], "constants": {**fx["constants"], **bad}}).status_code == 422, bad
    odd = {**fx["households"][0], "needsAt": float("1e9")}
    assert client.post("/api/sim/day", json={"households": [odd], "constants": fx["constants"]}).status_code == 422
    assert client.post("/api/sim/day", json={"households": [{"lon": "x"}], "constants": fx["constants"]}).status_code == 422


def test_sim_day_bounds_the_work_not_only_each_field():
    import json
    from hearth.config import ROOT
    fx = json.loads((ROOT / "tests/fixtures/sim_day.json").read_text())
    post = lambda **k: client.post("/api/sim/day", json={"households": [], "constants": {**fx["constants"], **k}}).status_code  # noqa: E731
    assert post() == 200
    ten = [{"name": f"S{i}", "at": [-95.37, 29.76]} for i in range(10)]
    assert post(stations=ten, crewsPerStation=10) == 422  # 100 vans: each field is legal, the fleet is not
    assert post(stations=ten, crewsPerStation=3) == 200  # 30 vans is the most
    assert post(dt=0.05, runHours=48) == 422  # 960 steps
    assert post(dt=0.25, runHours=48) == 200  # 192 steps
    assert post(stations=[{"name": "far", "at": [1e308, 29.76]}]) == 422  # not a place on Earth


def test_staging_options_choice_and_clear(monkeypatch):
    from hearth import staging
    opt = {"building_id": "B-SAMPLE", "name": "Lot", "address": "1 Lot St", "zip": "77027", "property_type": "retail",
           "surface_spaces": 300, "lot_acres": 4.0, "km": 1.1}
    from hearth.buildings import tools
    monkeypatch.setattr(tools, "costar_all", lambda: [opt | {"lat": 29.77, "lon": -95.37}])
    monkeypatch.setattr(staging, "scene", lambda: ((29.76, -95.37), set(), "open requests"))
    assert client.get("/api/staging").json() == {"chosen": None, "options": [opt | {"lat": 29.77, "lon": -95.37}], "basis": "open requests"}
    assert client.post("/api/staging", json={"building_id": "NOPE"}).status_code == 409
    assert client.post("/api/staging", json={"building_id": "B-SAMPLE"}).json()["chosen"]["building_id"] == "B-SAMPLE"
    assert client.get("/api/staging").json()["chosen"]["stale"] is False
    assert client.get("/api/crews/c1/job").json()["staging"]["building_id"] == "B-SAMPLE"
    assert client.post("/api/staging", json={"building_id": None}).json() == {"chosen": None}
    assert client.get("/api/staging").json()["chosen"] is None


def test_a_shelter_tile_is_asked_for_by_coordinates():
    assert client.get("/api/shelter-tile?lat=29.705&lon=-95.46").status_code == 404  # fixtures hold no shelter tile
    assert client.get("/api/shelter-tile?lat=north&lon=-95.46").status_code == 422
    assert client.get("/api/shelter-tile?lat=129.705&lon=-95.46").status_code == 422  # not a place on Earth


def test_a_lot_without_a_tile_or_reading_is_404_not_an_error():
    assert client.get("/api/buildings/B-SAMPLE/lot-image").status_code == 404  # fixtures hold no lot tile
    assert client.get("/api/buildings/B-SAMPLE/lot-reading").status_code == 404  # fixtures ask no vision model
    assert client.get("/api/buildings/NOPE/lot-image").status_code == 404


def test_a_storage_failure_is_an_error_the_browser_can_read(monkeypatch):
    # unhandled, it would leave as a bare 500 outside CORS, which a browser shows only as "Failed to fetch"
    import httpx
    from hearth import remote

    def broken(path):
        req = httpx.Request("GET", "https://project.supabase.co/storage/v1/object/x")
        raise httpx.HTTPStatusError("boom", request=req, response=httpx.Response(503, request=req))

    monkeypatch.setattr(remote, "fetch", broken)
    r = TestClient(app, raise_server_exceptions=False).get("/api/runs/cloud_run/meta", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 502 and r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "503" in r.json()["detail"] and "supabase" not in r.json()["detail"]  # says what failed, not where it lives


def test_any_other_crash_is_readable_too(monkeypatch):
    from hearth import remote
    monkeypatch.setattr(remote, "fetch", lambda path: 1 / 0)
    r = TestClient(app, raise_server_exceptions=False).get("/api/runs/cloud_run/meta", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500 and r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert r.json()["detail"] == "server error (ZeroDivisionError)"
