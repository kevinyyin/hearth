"""Agent runs the dispatch page starts on its own: stored records, the in-progress guard, and what to start next."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / "buildings"))
from bhelpers import profile, seed_pending_proposal  # noqa: E402

from api.main import app  # noqa: E402
from hearth import agents, dispatch, store  # noqa: E402
from hearth.contracts import HelpRequest, Home, TraceEvent  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps({"order": [{"patient_id": r["patient_id"], "reason": "r"} for r in rows]}))


def ev(kind, agent, text, t, **data):
    return TraceEvent(seq=0, t=t, kind=kind, agent=agent, text=text, data=data)


def survey_run():
    return agents.claim("survey", building_id="B-SAMPLE", patient_id="R-1", address="1200 Fixture St")


def test_second_start_while_running_is_refused():
    survey_run()
    with pytest.raises(ValueError):
        survey_run()


def test_a_stale_run_may_start_again(monkeypatch):
    run = survey_run()
    store.put("agent_run", run["run_id"], run | {"updated_at": time.time() - agents.a("agents.stale_after_s") - 1})
    assert agents.runs()[0]["status"] == "stopped"
    assert survey_run()["status"] == "running"


def test_track_stores_survey_layer_steps_and_places_again(monkeypatch):
    placed = []
    monkeypatch.setattr(dispatch, "place_again", lambda pid: placed.append(pid))
    events = [ev("subagent", "costar", "read", 1), ev("subagent", "interior", "scan", 1), ev("tool", "costar", "costar_record(building_id=B)", 2),
              ev("file", "costar", "/B/costar.md", 4), ev("tool", "interior", "matterport_rooms(building_id=B)", 5)]
    run = survey_run()
    out = agents.track(run, iter(events + [ev("profile", "surveyor", "writing", 20), ev("done", "surveyor", "profile written", 23, profile={"error": None})]))
    for e in out:
        if e.t == 5:  # mid-run, as another tab reads it
            mid = store.get("agent_run", run["run_id"])["steps"]
    assert mid == [{"text": "CoStar records", "t0": 1, "t1": 4}, {"text": "Matterport scan, reading rooms", "t0": 1, "t1": None}]
    done = store.get("agent_run", run["run_id"])
    assert done["status"] == "done" and [s["t1"] for s in done["steps"]] == [4, 23, 23]
    assert done["steps"][1]["text"] == "Matterport scan" and placed == ["R-1"]


def test_track_stores_refuge_steps_and_shelter_leads():
    run = agents.claim("refuge", building_id="B-SAMPLE", patient_id="p1", address="1200 Fixture St")
    sites = [{"lat": 29.7, "lon": -95.4, "looks_like": "school"}]
    list(agents.track(run, iter([ev("tool", "refuge", "search_refuges(patient_id=p1)", 1), ev("tool", "refuge", "check_access(patient_id=p1, building_id=H-STEPS)", 3),
                                 ev("tool", "refuge", "search_shelter_sites(patient_id=p1)", 9), ev("done", "refuge", "no eligible refuge found", 11, error=None, shelter_sites=sites)])))
    done = store.get("agent_run", run["run_id"])
    assert [(s["text"], s["t0"], s["t1"]) for s in done["steps"]] == [
        ("Hotels and senior housing nearby", 1, 3), ("Access checked: Stoop Hotel (fixture)", 3, 9), ("Aerial search: 1 shelter lead", 9, 11)]
    assert done["status"] == "done" and done["result"]["shelter_sites"] == sites


def test_a_proposal_ends_the_run_with_its_id():
    run = agents.claim("refuge", building_id="B-SAMPLE", patient_id="p1", address="x")
    list(agents.track(run, iter([ev("tool", "refuge", "submit_proposal(patient_id=p1)", 2), ev("interrupt", "dispatcher", "waiting", 3, proposal_id="P-1")])))
    done = store.get("agent_run", run["run_id"])
    assert done["status"] == "done" and done["result"] == {"proposal_id": "P-1"} and done["steps"][-1]["text"] == "Proposal sent for approval"


def test_a_stream_closed_early_is_stopped():
    run = survey_run()
    gen = agents.track(run, iter([ev("subagent", "costar", "read", 1), ev("subagent", "aerial", "read", 1)]))
    next(gen)
    gen.close()
    assert store.get("agent_run", run["run_id"])["status"] == "stopped"


def test_survey_endpoint_is_409_while_running():
    survey_run()
    assert client.get("/api/buildings/B-SAMPLE/survey?fresh=true").status_code == 409


def test_a_cached_survey_is_not_a_run():
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", floors=8))
    with client.stream("GET", "/api/buildings/B-SAMPLE/survey") as r:
        assert "cached profile" in "".join(r.iter_text())
    assert agents.runs() == []


def register(pid, building_id="B-SAMPLE"):
    store.put("patient", pid, client.get("/api/patients/p4/home").json()["patient"] | {"patient_id": pid})
    store.put("home", pid, Home(patient_id=pid, building_id=building_id, ok_without_h=3, source="phone", said_at=datetime.now(timezone.utc)))


def test_to_start_lists_unsurveyed_registrations_once():
    register("R-1")
    register("R-2")  # same building: one survey
    store.put("profile", "B-NOSCAN", profile("B-NOSCAN", floors=2))
    register("R-3", "B-NOSCAN")  # already surveyed
    assert [(s["kind"], s["building_id"], s["patient_id"]) for s in agents.to_start()] == [("survey", "B-SAMPLE", "R-1")]
    list(agents.track(survey_run(), iter([ev("done", "surveyor", "failed", 1, profile={"error": "boom"})])))
    assert agents.to_start() == []  # a finished survey is not retried, even a failed one


def blocked(pid="p1"):
    r = HelpRequest(patient_id=pid, blocked=dispatch.NO_REFUGE.format(km=agents.a("refuge.search_radius_km")), times={"waiting": datetime.now(timezone.utc)})
    client.get(f"/api/patients/{pid}/home")  # stores the patient record
    store.put("help", pid, r)
    return r


def test_blocked_request_starts_one_refuge_search():
    blocked()
    store.put("help", "p2", HelpRequest(patient_id="p2", blocked=dispatch.NO_CREW, times={"waiting": datetime.now(timezone.utc)}))
    first = agents.to_start()
    assert [(s["kind"], s["patient_id"]) for s in first] == [("refuge", "p1")]
    run = agents.claim("refuge", building_id="B-SAMPLE", patient_id="p1", address="x", request_at=agents.request_at(dispatch.request("p1")))
    assert agents.to_start() == []  # running
    list(agents.track(run, iter([ev("done", "refuge", "none", 2, error=None)])))
    assert agents.to_start() == []  # once per request


def test_rejected_proposal_starts_the_search_again():
    blocked()
    run = agents.claim("refuge", building_id="B-SAMPLE", patient_id="p1", address="x", request_at=agents.request_at(dispatch.request("p1")))
    seed_pending_proposal("P-1")
    list(agents.track(run, iter([ev("interrupt", "dispatcher", "waiting", 3, proposal_id="P-1")])))
    assert agents.to_start() == []
    store.put("proposal", "P-1", store.get("proposal", "P-1") | {"status": "rejected", "reason": "too far"})
    again = agents.to_start()
    assert [s["patient_id"] for s in again] == ["p1"] and again[0]["key"] != "refuge-p1@0"


def test_to_start_is_capped(monkeypatch):
    for pid, b in (("R-1", "B-SAMPLE"), ("R-2", "B-NOSCAN"), ("R-3", "H-LEVEL")):
        register(pid, b)
    assert len(agents.to_start()) == agents.a("agents.max_running")
    survey_run()
    assert len(agents.to_start()) == agents.a("agents.max_running") - 1


def test_dispatch_view_carries_positions_runs_and_what_to_start():
    register("R-1")
    blocked("p3")
    view = client.get("/api/dispatch").json()
    row = view["requests"][0]
    assert row["building_id"] == "B-SAMPLE" and row["lat"] and row["lon"] and row["patient"]["mobility"] == "bedbound"
    assert {s["kind"] for s in view["to_start"]} == {"survey", "refuge"} and view["agents"] == [] and view["proposals"] == []
    assert view["storm"] == {"placed": {}, "last": None}


def test_old_finished_requests_leave_the_board():
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.put("help", "p2", HelpRequest(patient_id="p2", state="safe", times={"waiting": old, "safe": old}))
    client.get("/api/patients/p2/home")
    assert client.get("/api/dispatch").json()["requests"] == []


def test_simulated_dots_are_a_sample():
    dots = client.get("/api/dispatch/simulated").json()
    assert 0 < len(dots) <= agents.a("dispatch_page.simulated_dots") and all(-96 < lon < -95 and 29 < lat < 31 for lon, lat in dots)

