"""The registration and check scripts, driven turn by turn with interpreted turns (no model, no voice endpoint)."""
import pytest

from hearth import store
from hearth.buildings import tools
from hearth.contracts import Home, Patient
from hearth.messaging import register, registry
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import render

PHONE = "+15550001111"
YES, NO = Turn(confirms=True, confidence=1.0), Turn(confirms=False, confidence=1.0)
ADDRESS = Turn(house_number="1200", street="Fixture Street", unit="310", confidence=0.9)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("HEARTH_FIXTURES", "1")


def new_call(kind="register", patient_id=None, **ctx):
    return {"call_id": "C-1", "patient_id": patient_id, "kind": kind, "status": "active", "step": "open", "last": None,
            "ctx": {"county": "Harris County", "phone": PHONE} | ctx, "facts": {}, "events": []}


def talk(call, *turns):
    """Every line the agent says, the opening first."""
    lines = register.opening(call)
    said = [render(k, **v) for k, v in lines]
    for t in turns:
        lines = register.advance(call, t)
        said += [render(k, **v) for k, v in lines]
        call["last"] = list(lines[-1])
    return said


def registered(call=None):
    c = call or new_call()
    talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
         YES, Turn(floor=3, confidence=0.9), Turn(door="the side door", confidence=0.9), Turn(room="bedroom", room_label="bedroom", confidence=0.9), YES)
    return c


def test_a_full_registration_writes_records_and_closes():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
                YES, Turn(floor=3, confidence=0.9), Turn(door="the side door", confidence=0.9), Turn(room="bedroom", room_label="bedroom", confidence=0.9), YES)
    assert said[-1] == render("reg_close") and c["status"] == "done"
    assert "That's in building A. Is that right?" in said and "Your building has 8 floors. Which floor are you on?" in said
    pid = registry.patient_for_phone(PHONE)
    h, p = Home(**store.get("home", pid)), Patient(**store.get("patient", pid))
    assert (h.unit, h.complex_building, h.door, h.room, h.scan_room, h.source, p.floor) == ("00-0310", "A", "the side door", "bedroom", "bedroom", "phone", 3)
    assert h.scan_id == "fixture-B-SAMPLE"


def test_no_equipment_closes_and_stores_nothing():
    c = new_call()
    assert talk(c, NO)[-1] == render("reg_no_equipment") and c["status"] == "done" and store.all("patient") == []


def test_another_device_hands_off():
    c = new_call()
    assert talk(c, YES, Turn(device="other", confidence=0.9))[-1] == render("human_handoff") and c["status"] == "handoff"


def test_an_address_not_found_hands_off_after_the_second_try():
    c = new_call()
    nowhere = Turn(house_number="9", street="Nowhere Lane", confidence=0.9)
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), nowhere)
    assert said[-1] == render("ask_address") and c["status"] == "active"
    said = talk(c := new_call(), YES, Turn(device="oxygen", confidence=0.9), nowhere, nowhere)
    assert said[-2:] == [render("address_not_found"), render("human_handoff")] and c["status"] == "handoff"


def test_a_second_no_to_the_address_hands_off():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, NO, ADDRESS, NO)
    assert said[-2:] == [render("address_not_found"), render("human_handoff")] and c["status"] == "handoff"


def test_a_correction_at_each_readback():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, NO)
    assert said[-1] == render("ask_address")
    said = talk(c := new_call(), YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9),
                Turn(backup_hours=6, confidence=0.9))
    assert "six hours" in said[-1]
    said = talk(c := new_call(), YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
                YES, Turn(floor=3, confidence=0.9), Turn(door="the side door", confidence=0.9), Turn(room="bedroom", confidence=0.9),
                NO, Turn(which_part="floor", confidence=0.9), Turn(floor=4, confidence=0.9))
    assert said[-3:-1] == [render("ask_which_part"), "Your building has 8 floors. Which floor are you on?"]
    assert "on floor 4" in said[-1] and said[-1].endswith("Is that right?")
    assert registry.patient_for_phone(PHONE) is None  # nothing written before the home read-back is confirmed


def test_a_one_story_building_skips_the_floor(monkeypatch):
    rec = tools.costar_record("B-SAMPLE") | {"floors": 1, "num_buildings": 1}
    monkeypatch.setattr(tools, "costar_record", lambda bid: rec if bid == "B-SAMPLE" else None)
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
                Turn(door="front", confidence=0.9), Turn(room="bedroom", confidence=0.9), YES)
    assert not any("floor are you on" in s for s in said) and said[-1] == render("reg_close")
    assert Patient(**store.get("patient", registry.patient_for_phone(PHONE))).floor == 1


def test_questions_follow_the_record():
    plans = [{"name": "p", "beds": 1, "scan_ids": [], "units": [{"number": "1", "building": None}]}]
    assert register.questions({"floors": 8, "elevator_count": 1, "num_buildings": 2, "walkup": False, "floor_plans": plans}, {}) == \
        ["unit", "building", "floor", "door", "room"]
    assert "elevator" in register.questions({"floors": 4, "elevator_count": None, "walkup": None}, {"floor": 3})
    assert "elevator" not in register.questions({"floors": 4, "elevator_count": 0, "walkup": True}, {"floor": 3})
    assert "floor" not in register.questions({"floors": 1}, {})
    assert "unit" not in register.questions({"floors": 8, "floor_plans": plans}, {"unit": "1"})


def test_a_walkup_is_named_in_the_floor_question(monkeypatch):
    rec = tools.costar_record("B-SAMPLE") | {"walkup": True, "elevator_count": 0, "num_buildings": 1}
    monkeypatch.setattr(tools, "costar_record", lambda bid: rec if bid == "B-SAMPLE" else None)
    said = talk(new_call(), YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES)
    assert said[-1] == "Your building has 8 floors, and no elevator. Which floor are you on?"


def test_side():
    assert register.side("likely in paved lot south of buildings") == "south"
    assert register.side("by the front") is None and register.side(None) is None


def test_the_survey_sentence_is_never_spoken():
    store.put("profile", "B-SAMPLE", {"building_id": "B-SAMPLE", "van_dropoff": {"value": "likely in paved lot south of buildings", "source": "vexcel", "confidence": 0.35}})
    said = talk(new_call(), YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
                YES, Turn(floor=3, confidence=0.9))
    assert said[-1] == render("ask_door_aerial", side="south") and not any("paved lot" in s for s in said)


def test_a_room_label_must_be_a_room_name():
    c = new_call()
    talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
         YES, Turn(floor=3, confidence=0.9), Turn(door="side", confidence=0.9), Turn(room="the kitchen", room_label="Kitchen", confidence=0.9), YES)
    h = Home(**store.get("home", registry.patient_for_phone(PHONE)))
    assert h.scan_room is None and h.room == "the kitchen"


def test_room_lookup_failure_falls_back_to_bedrooms(monkeypatch):
    def down(*a, **k):
        raise RuntimeError("matterport down")
    monkeypatch.setattr(tools, "matterport_rooms", down)
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen", confidence=0.9), ADDRESS, YES, Turn(backup_hours=4, confidence=0.9), YES,
                YES, Turn(floor=3, confidence=0.9), Turn(door="side", confidence=0.9))
    assert c["ctx"]["room_names"] == [] and said[-1] == render("ask_room_beds")


def test_a_check_call_reads_back_what_is_known():
    pid = registered()["patient_id"]
    c = new_call("check", pid, storm=True)
    said = talk(c)
    assert said[0] == render("check_open_storm") and said[1].startswith("We have you at 1200 Fixture St") and said[1].endswith("Is that still right?")
    said = talk(new_call("check", pid, storm=True), YES, YES, YES)
    assert said[-1] == render("reg_close")


def test_a_check_call_correction_asks_again():
    pid = registered()["patient_id"]
    said = talk(new_call("check", pid), YES, NO, Turn(backup_hours=2, confidence=0.9), YES, YES)
    assert said[0] == render("check_open") and said[-1] == render("reg_close")
    assert Home(**store.get("home", pid)).ok_without_h == 2
