"""Call scripts as code. Each step reads the interpreted turn and returns template keys; voice.py renders and stores.

impact:       open -> ask -> readback -> [elevator_now] -> temperature -> close
move_consent: open -> move_offer -> consent_readback -> close
register, check: see register.py
"""
from hearth import store
from hearth.buildings import status, tools
from hearth.messaging import register
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import say_hours

Lines = list[tuple[str, dict]]


def opening(call: dict) -> Lines:
    if call["kind"] in ("register", "check", "menu"):
        return register.opening(call)
    c = call["ctx"]
    if call["kind"] == "move_consent":
        call["step"] = "move_offer"
        return [("open_automated", {"county": c["county"]}), ("move_offer", {"place": c["place"]})]
    call["step"] = "ask"
    if c.get("dialysis"):
        return [("open_automated", {"county": c["county"]}), ("dialysis_check", {})]
    if c.get("hours") is None:
        return [("open_automated", {"county": c["county"]}), ("ask_hours", {})]
    return [("open_automated", {"county": c["county"]}), ("impact_check", {"device": c["device"], "hours": say_hours(c["hours"])})]


def advance(call: dict, t: Turn) -> Lines:
    """Mutates call (step, pending, facts, status) and returns what to say next."""
    if call["kind"] in ("register", "check", "menu") or call["step"] in ("walk", "wheelchair"):
        return register.advance(call, t)
    if t.intent == "help" and call["patient_id"]:  # asking for help on an impact or move call opens the same request
        return register.help_branch(call)
    step, c, facts = call["step"], call["ctx"], call["facts"]
    # plain statements; only confident turns reach here. Never "safe": on a call, keypad 1 means "yes" to the question
    for k in ("device_running", "can_move"):
        if getattr(t, k) is not None:
            facts[k] = getattr(t, k)

    if step == "ask":
        if t.backup_hours is not None:
            return _readback(call, t.backup_hours)
        if call["last"][0] == "impact_check" and t.confirms:
            facts["backup_hours"] = c["hours"]  # caller agreed with the profile value we read to them
            return _after_hours(call)
        return _go(call, "ask", "dialysis_check" if c.get("dialysis") else "ask_hours")

    if step == "readback":
        if t.backup_hours is not None and abs(t.backup_hours - call["pending"]) > 0.01:
            return _readback(call, t.backup_hours)  # a correction gets its own read-back
        if t.confirms:
            facts["backup_hours"] = call.pop("pending")
            return _after_hours(call)
        if t.confirms is False:
            call.pop("pending")
            return _go(call, "ask", "dialysis_check" if c.get("dialysis") else "ask_hours")
        return _readback(call, call["pending"])

    if step == "elevator_now":
        said = t.elevator_working or {True: "yes", False: "no"}.get(t.confirms)
        if said is None:
            return _go(call, "elevator_now", "ask_elevator_working")
        facts["elevator_working"] = said
        status.record(call["ctx"]["building_id"], "resident", call["call_id"], elevator=said)
        return _go(call, "temperature", "ask_temperature")

    if step == "temperature":
        if t.confirms is None:
            return _go(call, "temperature", "ask_temperature")
        facts["home_too_hot_or_cold"] = t.confirms
        return _close(call)

    if step == "move_offer":
        yes = t.consents_to_move if t.consents_to_move is not None else t.confirms
        if yes:
            return _go(call, "consent_readback", "consent_readback", place=c["place"])
        if yes is False:
            facts["consents_to_move"] = False
            call["status"] = "handoff"
            call["events"].append({"type": "declined_move"})
            return [("human_handoff", {})]
        return _go(call, "move_offer", "move_offer", place=c["place"])

    if step == "consent_readback":
        yes = t.confirms if t.confirms is not None else t.consents_to_move
        if yes:
            facts["consents_to_move"] = True
            ride = c.get("ride")  # set by voice.py only when a ride job is accepted
            return ([("move_confirmed_ride", ride)] if ride else []) + _close(call)
        if yes is False:
            return _go(call, "move_offer", "move_offer", place=c["place"])
        return _go(call, "consent_readback", "consent_readback", place=c["place"])

    return [("close_no_promise", {})]  # closed call


def _after_hours(call: dict) -> Lines:
    """Whether an elevator runs is a fact about today: asked when the power is out, of someone above floor 1 in a building
    with an elevator (on record, or by their own statement)."""
    p, h = store.get("patient", call["patient_id"]) or {}, store.get("home", call["patient_id"]) or {}
    building_id = h.get("building_id") or p.get("building_id")
    rec = (tools.costar_record(building_id) if building_id else None) or {}
    if (p.get("floor") or 0) > 1 and ((rec.get("elevator_count") or 0) > 0 or h.get("has_elevator")):
        call["ctx"]["building_id"] = building_id
        return _go(call, "elevator_now", "ask_elevator_working")
    return _go(call, "temperature", "ask_temperature")


def _go(call: dict, step: str, key: str, **vars) -> Lines:
    call["step"] = step
    return [(key, vars)]


def _readback(call: dict, hours: float) -> Lines:
    call["pending"] = hours
    return _go(call, "readback", "readback_hours", hours=say_hours(hours), supply=call["ctx"]["supply"])


def _close(call: dict) -> Lines:
    call["status"], call["step"] = "done", "close"
    return [("close_no_promise", {})]
