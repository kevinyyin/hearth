"""Help, "I'm safe" and "details" by phone, on the help loop's own queue. Fixture world as in tests/test_dispatch.py."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "buildings"))
from bhelpers import profile  # noqa: E402

from hearth import dispatch, store  # noqa: E402
from hearth.config import ROOT  # noqa: E402
from hearth.contracts import Home, Patient  # noqa: E402
from hearth.messaging import register, registry, voice  # noqa: E402
from hearth.messaging.interpreter import Turn  # noqa: E402
from hearth.messaging.templates import render  # noqa: E402

PHONE = "+15550001111"
YES, NO = Turn(confirms=True, confidence=1.0), Turn(confirms=False, confidence=1.0)
HELP, SAFE = Turn(intent="help", confidence=0.9), Turn(intent="safe", confidence=0.9)
KEYPAD_1 = Turn(safe=True, confirms=True, confidence=1.0)


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    for r in json.loads((ROOT / "data/demo/patients.json").read_text()):
        store.put("patient", r["patient_id"], Patient(**r))
    store.put("profile", "H-LEVEL", profile("H-LEVEL", step_free=True, floors=5, elevators=2))
    store.put("profile", "H-STEPS", profile("H-STEPS", floors=3))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps({"order": [{"patient_id": r["patient_id"], "reason": "x"} for r in rows]}))
    dispatch.save_crew("A", "B-NOSCAN", "car", [], True)


def registrant() -> str:
    return registry.save({"patient_id": None, "ctx": {"phone": PHONE}, "facts": {
        "device": "oxygen", "device_words": "oxygen", "building_id": "B-SAMPLE", "address": "1200 Fixture St, Houston, TX 77002",
        "backup_hours": 4.0, "floor": 3, "home_confirmed": True}})


def menu_call(pid):
    return {"call_id": "C-1", "patient_id": pid, "kind": "menu", "status": "active", "step": "open", "last": None,
            "ctx": {"county": "Harris County", "phone": PHONE}, "facts": {}, "events": []}


def talk(call, *turns):
    lines = register.opening(call)
    said = [render(k, **v) for k, v in lines]
    for t in turns:
        lines = register.advance(call, t)
        said += [render(k, **v) for k, v in lines]
        call["last"] = list(lines[-1])
    return said


def mobility(pid):
    return Patient(**store.get("patient", pid)).mobility


def test_help_asks_how_they_move_then_opens_a_request():
    pid = registrant()
    c = menu_call(pid)
    said = talk(c, HELP, YES)
    assert said[-2:] == [render("ask_walk"), render("help_opened")] and c["status"] == "done"
    assert dispatch.request(pid).state in ("waiting", "offered") and mobility(pid) == "walks_with_help"
    assert Home(**store.get("home", pid)).mobility_asked


@pytest.mark.parametrize("answer,want", [(Turn(mobility="wheelchair", confidence=0.9), "wheelchair_power"),
                                         (Turn(mobility="bed", confidence=0.9), "bedbound"), (Turn(confidence=0.9), "bedbound")])
def test_the_more_careful_mobility_is_recorded(answer, want):
    pid = registrant()
    said = talk(menu_call(pid), HELP, NO, answer)
    assert render("ask_wheelchair") in said and said[-1] == render("help_opened") and mobility(pid) == want


def test_a_demo_patient_is_not_asked_how_they_move():
    said = talk(menu_call("p4"), HELP)
    assert said[-1] == render("help_opened") and mobility("p4") == "walks"


def test_needs_help_now_opens_a_request_without_questions_and_flags_the_call(monkeypatch):
    pid = registrant()
    monkeypatch.setattr(voice, "interpret_turn", lambda *a: Turn(needs_help_now=True, wants_human=True, confidence=0.9))
    c = voice.start_call(pid, "menu", phone=PHONE)
    voice.respond(c, "")  # the opening
    assert render("help_opened") in voice.respond(c, "my oxygen stopped, I can't breathe")
    assert store.get("call", c)["status"] == "escalated" and dispatch.request(pid).state in ("waiting", "offered") and mobility(pid) == "bedbound"


def test_a_live_request_is_already_in_and_read_back():
    pid = registrant()
    dispatch.open_request(pid)
    said = talk(menu_call(pid), HELP)
    assert said[1].startswith("Your request: ") and said[-2] == render("help_already") and said[-1].startswith("Your request: ")


def test_spoken_safe_marks_safe_but_keypad_1_does_not():
    pid = registrant()
    assert talk(menu_call(pid), KEYPAD_1)[-1] == render("menu") and dispatch.request(pid) is None
    assert talk(menu_call(pid), SAFE)[-1] == render("safe_noted") and dispatch.request(pid).state == "safe"


def test_safe_while_riding_reads_the_latest_line():
    pid = registrant()
    p = store.get("patient", pid) | {"mobility": "walks"}
    store.put("patient", pid, p)
    dispatch.open_request(pid)
    for act in ("accept", "arrived", "picked_up"):
        dispatch.crew_action("A", act)
    said = talk(menu_call(pid), SAFE)
    assert said[-1].startswith("Your request: On the way to") and dispatch.request(pid).state == "riding"


def test_details_turns_the_call_into_a_check():
    pid = registrant()
    c = menu_call(pid)
    said = talk(c, Turn(intent="details", confidence=0.9))
    assert c["kind"] == "check" and said[-2] == render("check_open") and said[-1].startswith("We have you at 1200 Fixture St")


def test_an_impact_call_can_open_a_request(monkeypatch):
    turns = {"": Turn(), "I need help": HELP}
    monkeypatch.setattr(voice, "interpret_turn", lambda text, *a: turns[text])
    c = voice.start_call("p4", "impact")
    voice.respond(c, "")
    assert voice.respond(c, "I need help") == render("help_opened") and dispatch.request("p4").state in ("waiting", "offered")


def test_tracker_lines_fill_the_window_in_houston_time():
    dispatch.open_request("p4")
    dispatch.crew_action("A", "accept")
    lines = dispatch.tracker_lines(dispatch.request("p4"))
    assert "{window}" not in lines[-1] and " between " in lines[-1] and ("AM" in lines[-1] or "PM" in lines[-1])
    assert dispatch.latest_line("p4") == lines[-1]
