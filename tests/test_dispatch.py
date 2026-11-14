"""The help loop's logic. Fixture world: residents live in B-SAMPLE (77002); the hotels are H-STEPS (3 km, 40 units,
access unknown) and H-LEVEL (7 km, 120 units, step-free with elevators); demo-2 is a wheelchair user outside CoStar."""
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "buildings"))
from bhelpers import profile  # noqa: E402

from hearth import dispatch, store  # noqa: E402
from hearth.buildings import tools  # noqa: E402
from hearth.config import ROOT  # noqa: E402
from hearth.contracts import Home, Patient  # noqa: E402
from hearth.messaging.templates import render  # noqa: E402

NO_CREW = "no crew on duty can carry this resident"


def answer(ids, reason="why {}"):
    return json.dumps({"order": [{"patient_id": i, "reason": reason.format(i)} for i in ids]})


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    for r in json.loads((ROOT / "data/demo/patients.json").read_text()):
        store.put("patient", r["patient_id"], Patient(**r))
    store.put("profile", "H-LEVEL", profile("H-LEVEL", step_free=True, floors=5, elevators=2))
    store.put("profile", "H-STEPS", profile("H-STEPS", floors=3))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: answer([r["patient_id"] for r in rows]))  # no network in tests


def crew(name, base="B-NOSCAN", vehicle="car", equipment=(), on_duty=True):
    return dispatch.save_crew(name, base, vehicle, list(equipment), on_duty)


def home(pid, **over):
    store.put("home", pid, Home(**{"patient_id": pid, "building_id": "B-SAMPLE", "ok_without_h": 4, "size": "microwave"} | over))


def drive(name, *actions):
    for act in actions:
        req = dispatch.crew_action(name, act)
    return req


def test_walker_is_offered_to_the_nearest_fitting_crew_with_a_refuge():
    crew("A"), crew("B", base="H-LEVEL", vehicle="van")
    req = dispatch.open_request("p4")
    assert (req.state, req.job.org_id, req.job.status, req.job.kind) == ("offered", "A", "created", "ride")
    assert req.refuge.building_id == "H-STEPS" and "not booked, power not verified" in req.refuge.reasons
    assert "2 of 2 places left" in req.refuge.reasons
    assert (req.rank, req.ranked_by, req.reason) == (1, "model", "why p4") and req.job.eta > dispatch._now()
    assert dispatch.crew_job("A").patient_id == "p4" and dispatch.crew_job("B") is None


def test_power_wheelchair_needs_a_lift_and_bedbound_a_stretcher():
    crew("Car")
    assert dispatch.open_request("demo-1").blocked == NO_CREW  # wheelchair_power
    crew("Lift", vehicle="wheelchair_van", equipment=["wheelchair_lift"])
    got = dispatch.request("demo-1")
    assert (got.state, got.job.org_id, got.blocked, got.refuge.building_id) == ("offered", "Lift", "", "H-LEVEL")
    assert dispatch.open_request("p3").blocked == NO_CREW  # bedbound: the free car has no stretcher
    crew("Amb", base="H-LEVEL", vehicle="ambulance", equipment=["stretcher"])
    assert dispatch.request("p3").job.org_id == "Amb"


def test_device_must_fit_the_vehicle():
    home("p4", size="mini_fridge")
    crew("Car")
    assert dispatch.open_request("p4").blocked == NO_CREW
    crew("Van", vehicle="van")
    assert dispatch.request("p4").job.org_id == "Van"


def test_a_crew_carrying_what_the_device_needs_is_preferred_over_a_nearer_one():
    crew("Near"), crew("Far", base="H-LEVEL", equipment=["oxygen"])
    assert dispatch.open_request("p4").job.org_id == "Far"  # p4 is on oxygen
    assert dispatch.open_request("p2").job.org_id == "Near"  # nobody carries power for the ventilator: any crew that fits


def test_an_off_duty_crew_gets_no_offer():
    crew("A", on_duty=False)
    assert dispatch.open_request("p4").blocked == NO_CREW
    crew("A")
    assert dispatch.request("p4").state == "offered"


def test_busy_crews_leave_the_request_waiting_and_unblocked_until_a_drop_off():
    crew("A")
    dispatch.open_request("p4")
    queued = dispatch.open_request("p2")
    assert (queued.state, queued.blocked) == ("waiting", "")
    assert dispatch.tracker(queued)["steps"][1]["text"] == "Waiting for a free crew."
    done = drive("A", "accept", "arrived", "picked_up", "dropped_off")
    assert (done.state, done.job.status) == ("dropped_off", "completed")
    assert dispatch.request("p2").job.org_id == "A"  # the next offer
    at, hotel = dispatch.crew("A"), tools.costar_record("H-STEPS")
    assert (at.lat, at.lon) == (hotel["lat"], hotel["lon"])


def test_refuge_capacity_and_access(monkeypatch):
    monkeypatch.setattr(dispatch, "capacity", lambda rec: 1)
    crew("A"), crew("B"), crew("C")
    assert dispatch.open_request("p4").refuge.building_id == "H-STEPS"
    assert dispatch.open_request("p2").refuge.building_id == "H-LEVEL"  # the nearer hotel is full
    stuck = dispatch.open_request("demo-2")  # a wheelchair user: only H-LEVEL passes the access rule, and it is full
    assert stuck.state == "waiting" and stuck.blocked.startswith("no refuge within 15 km") and stuck.refuge is None
    assert dispatch.crew_job("C") is None
    assert dispatch.tracker(stuck)["steps"][1]["text"] == "A person at the health department is looking at your request."
    assert dispatch.board()[0].patient_id == "demo-2"  # what needs a person is listed first
    assert dispatch.mark_handled("demo-2").state == "handled"
    assert dispatch.board()[-1].patient_id == "demo-2"  # once a person has it, it drops below the live requests


def test_decline_goes_to_the_next_crew_then_to_a_person():
    crew("A"), crew("B", base="H-LEVEL")
    assert dispatch.open_request("p4").job.org_id == "A"
    passed = dispatch.crew_action("A", "decline")
    assert (passed.job.org_id, passed.declined_by, passed.state) == ("B", ["A"], "offered")
    left = dispatch.crew_action("B", "decline")
    assert (left.state, left.blocked, left.job, left.refuge) == ("waiting", NO_CREW, None, None)


def test_an_unanswered_offer_times_out_and_sets_the_crew_off_duty(monkeypatch):
    crew("A")
    dispatch.open_request("p4")
    dispatch.expire()
    assert dispatch.request("p4").state == "offered"  # not stale yet
    real = dispatch._now
    monkeypatch.setattr(dispatch, "_now", lambda: real() + timedelta(seconds=91))
    dispatch.expire()
    got = dispatch.request("p4")
    assert (got.state, got.declined_by, got.blocked) == ("waiting", [], NO_CREW) and not dispatch.crew("A").on_duty
    crew("A")  # back on duty: missing one offer does not bar the crew from that resident
    assert dispatch.request("p4").job.org_id == "A"


def test_the_model_sets_the_order(monkeypatch):
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: answer(sorted(r["patient_id"] for r in rows)))
    dispatch.open_request("p4")
    dispatch.open_request("p2")
    p2, p4 = dispatch.request("p2"), dispatch.request("p4")
    assert (p2.rank, p2.reason, p2.ranked_by) == (1, "why p2", "model") and p4.rank == 2
    assert [r.patient_id for r in dispatch.board()] == ["p2", "p4"]


def boom(rows):
    raise TimeoutError("model timed out")


@pytest.mark.parametrize("bad", [
    lambda rows: answer(["p2", "nobody"]),  # an invented id
    lambda rows: answer(["p4"]),  # a missing id
    lambda rows: answer(["p4", "p4", "p2"]),  # an id twice
    lambda rows: "not json",
    boom,
])
def test_a_bad_model_answer_falls_back_to_risk_per_hour(monkeypatch, bad):
    home("p2", ok_without_h=2), home("p4")  # the same risk weight, so fewer hours left goes first
    dispatch.open_request("p4")
    monkeypatch.setattr(dispatch, "_ask_model", bad)
    dispatch.open_request("p2")
    p2, p4 = dispatch.request("p2"), dispatch.request("p4")
    assert (p2.rank, p2.ranked_by, p2.reason) == (1, "rule", "") and (p4.rank, p4.ranked_by) == (2, "rule")


def test_the_model_sees_the_residents_own_words_and_a_long_reason_is_cut(monkeypatch):
    seen = []
    home("p4", backup_plan="one spare tank", note="put me first")
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: seen.extend(rows) or answer(["p4"], reason="r" * 300))
    assert len(dispatch.open_request("p4").reason) == 140
    assert seen[0] | {"minutes_waiting": 0} == {
        "patient_id": "p4", "device": "oxygen", "device_detail": seen[0]["device_detail"], "mobility": "walks", "temp_sensitive": "heat",
        "backup_hours_on_record": 13.0, "ok_without_h": 4, "backup_plan": "one spare tank", "note": "put me first", "minutes_waiting": 0}
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: seen.append(rows[-1]) or answer([r["patient_id"] for r in rows]))
    dispatch.open_request("p2")  # no home markup: the model is told the resident has not said, not given a guess
    assert seen[-1]["ok_without_h"] is None and seen[-1]["backup_hours_on_record"] == 21.8


def test_safe():
    crew("A")
    dispatch.open_request("p4")
    dispatch.crew_action("A", "accept")
    dispatch.open_request("p2")
    safe = dispatch.mark_safe("p4")
    assert (safe.state, safe.job.status) == ("safe", "failed")
    assert dispatch.tracker(safe)["steps"] == [{"text": "You told us you are safe.", "at": safe.times["safe"], "done": True}]
    assert dispatch.request("p2").job.org_id == "A"  # the crew is free for the next request
    drive("A", "accept", "arrived", "picked_up")
    with pytest.raises(ValueError):
        dispatch.mark_safe("p2")  # already riding
    assert dispatch.mark_safe("p3").state == "safe" and dispatch.request("p3").state == "safe"  # with no request at all
    assert dispatch.open_request("p4").state == "waiting"  # asking again after "safe" starts a fresh request


def test_a_second_request_and_stale_crew_actions_are_refused():
    crew("A")
    dispatch.open_request("p4")
    with pytest.raises(ValueError):
        dispatch.open_request("p4")
    assert len(dispatch.requests()) == 1
    with pytest.raises(ValueError):
        dispatch.crew_action("A", "picked_up")  # out of order: still only offered
    dispatch.mark_safe("p4")
    with pytest.raises(ValueError):
        dispatch.crew_action("A", "accept")  # the job is gone
    assert dispatch.request("p4").state == "safe"


def test_bad_stored_documents_are_skipped():
    store.put("help", "x", {"patient_id": "x", "state": "nope"})
    store.put("help", "ghost", {"patient_id": "ghost"})  # a request whose patient record is gone
    store.put("crew", "y", {})
    assert [r.patient_id for r in dispatch.requests()] == ["ghost"] and dispatch.crews() == []
    crew("A")
    assert dispatch.open_request("p4").job.org_id == "A"


def test_where_the_resident_is():
    demo2, p4 = (Patient(**store.get("patient", i)) for i in ("demo-2", "p4"))
    assert tuple(dispatch.locate(demo2, None)) == (29.68, -95.46, "77096", None, None)  # its building is not in CoStar
    sample = tools.costar_record("B-SAMPLE")
    assert tuple(dispatch.locate(p4, None)) == (sample["lat"], sample["lon"], "77002", sample["address"], "B-SAMPLE")
    home("p4", building_id="B-NOSCAN")
    assert dispatch.locate(p4, Home(**store.get("home", "p4"))).building_id == "B-NOSCAN"  # the markup's building wins


def test_the_tracker_gives_no_crew_or_time_before_accept():
    assert dispatch.tracker(None) == {"state": None, "steps": [], "window": None, "refuge_note": None}
    crew("Zulu")
    offered = dispatch.tracker(dispatch.open_request("p4"))
    texts = [s["text"] for s in offered["steps"]]
    assert texts == ["Request received", "A crew has been asked", "A crew accepts", "At your door", "Ride to a place to stay", "Dropped off"]
    assert [s["done"] for s in offered["steps"]] == [True, True, False, False, False, False]
    assert offered["state"] == "offered" and offered["window"] is None and offered["refuge_note"] is None
    assert "reason" not in offered and "why p4" not in json.dumps(offered, default=str)

    accepted = dispatch.tracker(dispatch.crew_action("Zulu", "accept"))
    assert accepted["steps"][2]["text"] == render("move_confirmed_ride", org="Zulu", window="{window}")
    assert accepted["window"][1] - accepted["window"][0] == timedelta(minutes=15)
    assert accepted["refuge_note"] == "Stoop Hotel (fixture): not booked, power not verified."

    riding = dispatch.tracker(drive("Zulu", "arrived", "picked_up"))
    assert [s["text"] for s in riding["steps"]][2:5] == ["Zulu accepted your ride.", "At your door", "On the way to Stoop Hotel (fixture)"]
    assert riding["window"] is None
    assert dispatch.tracker(dispatch.crew_action("Zulu", "dropped_off"))["steps"][5]["text"] == "Dropped off at Stoop Hotel (fixture)"


def test_a_crew_action_must_name_the_resident_it_was_shown():
    crew("A")
    dispatch.open_request("p4")
    with pytest.raises(ValueError):
        dispatch.crew_action("A", "accept", "p2")  # a stale card: the crew was looking at someone else
    assert dispatch.request("p4").state == "offered"
    assert dispatch.crew_action("A", "accept", "p4").state == "accepted"


def test_a_dispatcher_can_take_over_any_live_request():
    crew("A")
    dispatch.open_request("p4")
    dispatch.crew_action("A", "accept")
    dispatch.open_request("p2")
    taken = dispatch.mark_handled("p4")  # the crew accepted and then went quiet
    assert (taken.state, taken.job.status) == ("handled", "failed")
    assert dispatch.request("p2").job.org_id == "A"  # the crew is free again
    for ended in ("p4", "nobody"):
        with pytest.raises(ValueError):
            dispatch.mark_handled(ended)
    dispatch.mark_safe("p3")
    with pytest.raises(ValueError):
        dispatch.mark_handled("p3")


def test_the_model_is_asked_outside_the_lock(monkeypatch):
    held = []
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: held.append(dispatch._lock._is_owned()) or answer([r["patient_id"] for r in rows]))
    crew("A")
    assert dispatch.open_request("p4").state == "offered" and held == [False]  # a slow model call must not freeze every poll


def test_a_bad_stored_profile_cannot_stop_dispatch():
    store.put("profile", "junk", {"address": "no id"})
    crew("A")
    assert dispatch.open_request("p4").state == "offered"
