"""The call to a building's office: power and a running elevator, never a word about any resident."""
import re

import pytest

from hearth import store
from hearth.buildings import status
from hearth.messaging import scripts
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import render

YES, NO = Turn(confirms=True, confidence=1.0), Turn(confirms=False, confidence=1.0)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))


def new_call(one_story=False):
    return {"call_id": "C-B", "patient_id": None, "kind": "building_check", "status": "active", "step": "open", "last": None, "facts": {},
            "events": [], "ctx": {"county": "Harris County", "building_id": "H-LEVEL", "name": "Level Hotel", "address": "1 Fixture Ave, Houston",
                                  "one_story": one_story}}


def talk(call, *turns):
    said = [render(k, **v) for k, v in scripts.opening(call)]
    for t in turns:
        lines = scripts.advance(call, t)
        said += [render(k, **v) for k, v in lines]
        call["last"] = list(lines[-1])
    return said


def test_the_office_answers_are_recorded():
    c = new_call()
    said = talk(c, YES, YES, YES, YES)
    assert said[0].startswith("This is an automated call from Hearth") and "Level Hotel at 1 Fixture Ave, Houston" in said[0]
    assert said[-1] == render("bldg_close") and c["status"] == "done"
    s = status.latest("H-LEVEL")
    assert (s["power"], s["elevator"], s["said_by"], s["call_id"]) == (True, "yes", "building_office", "C-B")


def test_someone_who_does_not_work_there_ends_the_call():
    c = new_call()
    assert talk(c, NO)[-1] == render("bldg_not_staff") and c["status"] == "done" and status.latest("H-LEVEL") is None


def test_a_one_story_building_skips_the_elevator():
    said = talk(new_call(one_story=True), YES, NO, YES)
    assert render("bldg_elevator") not in said and status.latest("H-LEVEL")["power"] is False


def test_a_no_to_the_readback_asks_again():
    said = talk(new_call(), YES, YES, NO, NO)
    assert said[-1] == render("bldg_power") and status.latest("H-LEVEL") is None


def test_no_line_mentions_a_resident():
    lines = talk(new_call(), YES, YES, YES, NO, YES, YES, YES) + talk(new_call(), NO)
    for line in lines:
        assert not re.search(r"resident|patient|medical|equipment|oxygen|ventilator|dialysis", line, re.I), line
