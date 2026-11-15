import pytest

from hearth.contracts import PlanState
from hearth.messaging.templates import ALLOWED, KEYS, PROMISE_KEYS, TEMPLATES, allowed, render, say_hours


def test_ride_confirmation_needs_an_accepted_job():
    assert not allowed("move_confirmed_ride", PlanState.MOVE, "created")
    assert allowed("move_confirmed_ride", PlanState.MOVE, "accepted")
    assert not allowed("move_confirmed_ride", PlanState.RESUPPLY, "accepted")


def test_delivery_confirmation_needs_an_accepted_delivery():
    assert allowed("delivery_confirmed", PlanState.RESUPPLY, "accepted") and not allowed("delivery_confirmed", PlanState.RESUPPLY, "none")


def test_move_offer_only_in_move():
    assert allowed("move_offer", PlanState.MOVE, "none") and not allowed("move_offer", PlanState.OWN_BACKUP, "none")


def test_every_template_key_is_reachable():
    assert set(KEYS) == set().union(*ALLOWED.values())


def test_only_promise_keys_mention_acceptance():
    assert {k for k, t in TEMPLATES.items() if "accepted" in t} == PROMISE_KEYS


def test_open_line_says_automated():
    assert "automated" in render("open_automated", county="Harris County")


def test_voicemail_has_no_health_details():
    assert not any(w in render("voicemail", county="Harris County").lower() for w in ("oxygen", "ventilator", "dialysis", "backup", "power"))


def test_render_rejects_missing_placeholder():
    with pytest.raises(KeyError):
        render("readback_hours", hours="forty minutes")


def test_say_hours():
    assert say_hours(1.5) == "one and a half hours, that's ninety minutes"
    assert say_hours(0.67) == "forty minutes"
    assert say_hours(3.0) == "three hours, that's one hundred eighty minutes"
    assert say_hours(12.2) == "about twelve hours"


NEW = ["reg_open", "ask_address", "readback_address", "reg_ask_hours", "ask_floor_building", "ask_door_aerial", "readback_home",
       "reg_close", "menu", "help_opened", "safe_noted", "check_address", "ask_elevator_working", "bldg_open", "storm_week", "storm_day", "storm_outage", "ask_equipment"]


@pytest.mark.parametrize("key", NEW)
def test_new_keys_are_allowed_outside_moves(key):
    assert allowed(key, PlanState.OWN_BACKUP, "none")


def test_no_new_line_promises_a_crew():
    import re
    for key in NEW:
        assert not re.search(r"\b(on (its|the) way|will arrive|is coming)\b", TEMPLATES[key], re.I)
