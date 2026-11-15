"""The registration and check scripts, driven turn by turn with interpreted turns (no model, no voice endpoint)."""
import pytest

from hearth import store
from hearth.buildings import tools
from hearth.contracts import Home, Patient
from hearth.messaging import register, registry
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import render

PHONE = "+15550001111"
YES, NO = Turn(confirms=True), Turn(confirms=False)
ADDRESS = Turn(house_number="1200", street="Fixture Street", unit="310")


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
    talk(c, YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
         YES, Turn(floor=3), Turn(door="the side door"), Turn(room="bedroom", room_label="bedroom"), YES)
    return c


def test_a_full_registration_writes_records_and_closes():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
                YES, Turn(floor=3), Turn(door="the side door"), Turn(room="bedroom", room_label="bedroom"), YES)
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
    assert talk(c, YES, Turn(device="other"))[-1] == render("human_handoff") and c["status"] == "handoff"


def test_an_address_not_found_hands_off_after_the_second_try():
    c = new_call()
    nowhere = Turn(house_number="9", street="Nowhere Lane")
    said = talk(c, YES, Turn(device="oxygen"), nowhere)
    assert said[-1] == render("ask_address") and c["status"] == "active"
    said = talk(c := new_call(), YES, Turn(device="oxygen"), nowhere, nowhere)
    assert said[-2:] == [render("address_not_found"), render("human_handoff")] and c["status"] == "handoff"


def test_a_second_no_to_the_address_hands_off():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen"), ADDRESS, NO, ADDRESS, NO)
    assert said[-2:] == [render("address_not_found"), render("human_handoff")] and c["status"] == "handoff"


def test_a_correction_at_each_readback():
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen"), ADDRESS, NO)
    assert said[-1] == render("ask_address")
    said = talk(c := new_call(), YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4),
                Turn(backup_hours=6))
    assert "six hours" in said[-1]
    said = talk(c := new_call(), YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
                YES, Turn(floor=3), Turn(door="the side door"), Turn(room="bedroom"),
                NO, Turn(which_part="floor"), Turn(floor=4))
    assert said[-3:-1] == [render("ask_which_part"), "Your building has 8 floors. Which floor are you on?"]
    assert "on floor 4" in said[-1] and said[-1].endswith("Is that right?")
    assert registry.patient_for_phone(PHONE) is None  # nothing written before the home read-back is confirmed


def test_a_one_story_building_skips_the_floor(monkeypatch):
    rec = tools.costar_record("B-SAMPLE") | {"floors": 1, "num_buildings": 1}
    monkeypatch.setattr(tools, "costar_record", lambda bid: rec if bid == "B-SAMPLE" else None)
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
                Turn(door="front"), Turn(room="bedroom"), YES)
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
    said = talk(new_call(), YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES)
    assert said[-1] == "Your building has 8 floors, and no elevator. Which floor are you on?"


def test_side():
    assert register.side("likely in paved lot south of buildings") == "south"
    assert register.side("by the front") is None and register.side(None) is None


def test_the_survey_sentence_is_never_spoken():
    store.put("profile", "B-SAMPLE", {"building_id": "B-SAMPLE", "van_dropoff": {"value": "likely in paved lot south of buildings", "source": "vexcel"}})
    said = talk(new_call(), YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
                YES, Turn(floor=3))
    assert said[-1] == render("ask_door_aerial", side="south") and not any("paved lot" in s for s in said)


def test_a_room_label_must_be_a_room_name():
    c = new_call()
    talk(c, YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
         YES, Turn(floor=3), Turn(door="side"), Turn(room="the kitchen", room_label="Kitchen"), YES)
    h = Home(**store.get("home", registry.patient_for_phone(PHONE)))
    assert h.scan_room is None and h.room == "the kitchen"


def test_room_lookup_failure_falls_back_to_bedrooms(monkeypatch):
    def down(*a, **k):
        raise RuntimeError("matterport down")
    monkeypatch.setattr(tools, "matterport_rooms", down)
    c = new_call()
    said = talk(c, YES, Turn(device="oxygen"), ADDRESS, YES, Turn(backup_hours=4), YES,
                YES, Turn(floor=3), Turn(door="side"))
    assert c["ctx"]["room_names"] == [] and said[-1] == render("ask_room_beds")


STORM = {"week": "A hurricane is forecast to reach your area in about a week.", "day": "A hurricane is forecast to reach your area today.",
         "outage": "The power is out in your area."}
WHO = "This is an automated call from Hearth for the Harris County health department."


@pytest.mark.parametrize("round", ["week", "day"])
def test_a_check_call_reads_back_what_is_known(round):
    pid = registered()["patient_id"]
    c = new_call("check", pid, storm=round)
    said = talk(c)
    assert said[:3] == [WHO, STORM[round], render("check_open")]  # an outbound call says who is calling and why
    assert said[3].startswith("We have you at 1200 Fixture St") and said[3].endswith("Is that still right?")
    said = talk(new_call("check", pid, storm=round), YES, YES, YES)
    assert said[-1] == render("reg_close")


@pytest.mark.parametrize("round", STORM)
def test_a_storm_call_to_an_unregistered_number_screens_first(round):
    question = "Does someone at home use powered medical equipment, like oxygen, a ventilator, home dialysis or a feeding pump?"
    assert talk(c := new_call(storm=round)) == [WHO, STORM[round], question] and render("reg_open", county="Harris County") == f"{WHO} {question}"
    said = talk(c, NO)
    assert "In an emergency, call 911." in said[-1] and c["status"] == "done" and store.all("patient") == store.all("contact") == []
    assert talk(new_call(storm=round), YES)[-1] == render("ask_device")


def test_a_check_call_correction_asks_again():
    pid = registered()["patient_id"]
    said = talk(new_call("check", pid), YES, NO, Turn(backup_hours=2), YES, YES)
    assert said[0] == render("check_open") and said[-1] == render("reg_close")
    assert Home(**store.get("home", pid)).ok_without_h == 2


def test_an_apartment_asked_on_its_own_can_be_corrected():
    said = talk(new_call(), YES, Turn(device="oxygen"), Turn(house_number="1200", street="Fixture Street"), YES,
                Turn(backup_hours=4), YES, Turn(unit="310"), YES, Turn(floor=3),
                Turn(door="side"), Turn(room="bedroom"), NO, Turn(which_part="unit"))
    assert render("ask_unit") in said[:-1] and "in apartment 310" in said[-3] and said[-2:] == [render("ask_which_part"), render("ask_unit")]
