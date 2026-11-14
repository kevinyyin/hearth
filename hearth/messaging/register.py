"""Registration and check calls, as code. The CoStar record decides which home questions are asked.

register: equipment -> device -> address (read back) -> hours (read back) -> the record's home questions -> home read-back
check:    what is registered, read back ("Is that still right?"); a "no" clears that part and the same flow asks it again

Answers to the home questions wait in call["answers"] until the home read-back confirms them; registry.save writes the
records only once device, address, hours and floor are confirmed. Every line is a template key; nothing a model wrote
(including the survey's van_dropoff sentence) is read out.
"""
import logging
import re
import threading

from hearth import store
from hearth.buildings import tools
from hearth.buildings.address import match_address, match_unit, norm_unit
from hearth.config import a
from hearth.messaging import registry
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import say_hours

log = logging.getLogger(__name__)
Lines = list[tuple[str, dict]]
ADDRESS_FACTS = ("building_id", "address", "unit", "plan", "scan_id", "complex_building", "floor", "has_elevator", "door",
                 "door_from_aerial", "room", "scan_room", "home_confirmed")  # a new address makes every home answer stale
PART = {"building": ("complex_building",), "floor": ("floor", "has_elevator"), "door": ("door", "door_from_aerial"), "room": ("room", "scan_room")}
_SIDE = re.compile(r"\b(north|south|east|west)\b", re.I)


def side(van_dropoff: str | None) -> str | None:
    """The compass side the survey's drop-off note names, if any. The note itself is a model's hedged guess."""
    m = _SIDE.search(van_dropoff or "")
    return m.group(1).lower() if m else None


def questions(rec: dict | None, facts: dict) -> list[str]:
    """The home questions this caller's CoStar record leaves open, in the order they are asked."""
    rec = rec or {}
    out = []
    if facts.get("unit") is None and any(p["units"] for p in rec.get("floor_plans") or []):
        out.append("unit")
    if (rec.get("num_buildings") or 1) > 1:
        out.append("building")
    if rec.get("floors") != 1:
        out.append("floor")
    if rec.get("elevator_count") is None and not rec.get("walkup") and (facts.get("floor") or 0) > 1:
        out.append("elevator")
    return out + ["door", "room"]


def opening(call: dict) -> Lines:
    c = call["ctx"]
    if call["kind"] == "check":
        call["facts"] = registry.facts_for(call["patient_id"])
        call["to_confirm"] = ["address", "hours", "home"]
        return [("check_open_storm" if c.get("storm") else "check_open", {})] + _next(call)
    call["step"] = "equipment"
    return [("reg_open", {"county": c["county"]})]


def advance(call: dict, t: Turn) -> Lines:
    """Mutates the call (step, facts, answers, status) and returns what to say next."""
    step, f, ans = call["step"], call["facts"], call.setdefault("answers", {})
    if step == "equipment":
        if t.confirms is False:
            return _done(call, "reg_no_equipment")
        if t.confirms or t.device:
            f["has_equipment"] = True
            return _device(call, t.device) if t.device else _next(call)
    elif step == "device" and t.device:
        return _device(call, t.device)
    elif step == "address" and t.house_number and t.street:
        return _address(call, t)
    elif step == "address_readback":
        if t.house_number and t.street:
            return _address(call, t)
        if t.confirms:
            return _confirm_address(call)
        if t.confirms is False:
            return _address_miss(call)
    elif step == "hours" and t.backup_hours is not None:
        return _hours_readback(call, t.backup_hours)
    elif step == "hours_readback":
        if t.backup_hours is not None and abs(t.backup_hours - call["pending"]) > 0.01:
            return _hours_readback(call, t.backup_hours)
        if t.confirms:
            f["backup_hours"] = call.pop("pending")
            registry.save(call)
            return _next(call)
        if t.confirms is False:
            call.pop("pending")
            return _next(call)
    elif step == "unit" and t.unit:
        if (m := match_unit(_rec(call), t.unit)) or call.get("unit_tries"):
            _set_unit(call, m, t.unit)
            return _next(call)
        call["unit_tries"] = 1
    elif step == "building_confirm" and t.confirms is not None:
        if t.confirms:
            ans["complex_building"] = call["unit_building"]
        call["unit_building"] = None  # a "no" asks which building
        return _next(call)
    elif step == "building" and t.building:
        ans["complex_building"] = t.building
        return _next(call)
    elif step == "floor" and t.floor is not None:
        ans["floor"] = t.floor
        return _next(call)
    elif step == "elevator" and (t.has_elevator is not None or t.confirms is not None):
        ans["has_elevator"] = t.has_elevator if t.has_elevator is not None else t.confirms
        return _next(call)
    elif step == "door_aerial" and (t.confirms is not None or t.door):
        if t.door:
            ans |= {"door": t.door, "door_from_aerial": False}
            return _next(call)
        if t.confirms:
            ans |= {"door": f"the door on the {call['side']} side, near the parking", "door_from_aerial": True}
            return _next(call)
        return _go(call, "door", "ask_door")
    elif step == "door" and t.door:
        ans |= {"door": t.door, "door_from_aerial": False}
        return _next(call)
    elif step == "room" and (t.room or t.room_label):
        label = t.room_label if t.room_label in call["ctx"].get("room_names", []) else None
        ans |= {"room": t.room or label, "scan_room": label}
        return _next(call)
    elif step == "home_readback":
        if t.confirms:
            f.update(ans | {"home_confirmed": True})
            call["answers"] = {}
            registry.save(call)
            return _next(call)
        if t.confirms is False or t.which_part:
            return _which_part(call, t.which_part)
    elif step == "which_part" and t.which_part:
        return _which_part(call, t.which_part)
    elif step in ("check_address", "check_hours", "check_home") and (t.confirms is not None or t.which_part):
        part = step.removeprefix("check_")
        call["to_confirm"].remove(part)
        if t.confirms and not t.which_part:
            return _next(call)
        if part == "address":
            for k in ADDRESS_FACTS:
                f.pop(k, None)
            if "home" in call["to_confirm"]:
                call["to_confirm"].remove("home")
        elif part == "hours":
            f.pop("backup_hours", None)
        else:
            return _which_part(call, t.which_part)
        return _next(call)
    elif step == "close":
        return [("close_no_promise", {})]
    return [tuple(call["last"])] if call.get("last") else _next(call)  # not an answer to the question: ask it again


# ---- what to ask next: the first thing still missing ----
def _next(call: dict) -> Lines:
    f, ans, c = call["facts"], call.setdefault("answers", {}), call["ctx"]
    have = f | ans
    if call["kind"] == "register" and not f.get("has_equipment"):
        return _go(call, "equipment", "reg_open", county=c["county"])
    if not f.get("device"):
        return _go(call, "device", "ask_device")
    if "address" in call.get("to_confirm", []):
        return _go(call, "check_address", "check_address", address=_spoken(f["address"]), unit=_unit_words(f.get("unit")))
    if not f.get("building_id"):
        return _go(call, "address", "ask_address")
    if "hours" in call.get("to_confirm", []):
        return _go(call, "check_hours", "check_hours", hours=say_hours(f["backup_hours"]), device=_device_words(f))
    if f.get("backup_hours") is None:
        return _go(call, "hours", "reg_ask_hours", device=_device_words(f))
    rec = _rec(call)
    if rec.get("floors") == 1 and have.get("floor") is None:
        ans["floor"] = 1
        have["floor"] = 1
    for row in questions(rec, have):
        if row == "unit" and "unit" not in have:
            return _go(call, "unit", "ask_unit")
        if row == "building" and not have.get("complex_building"):
            if call.get("unit_building"):
                return _go(call, "building_confirm", "confirm_building", b=call["unit_building"])
            return _go(call, "building", "ask_building", n=rec["num_buildings"])
        if row == "floor" and have.get("floor") is None:
            if rec.get("floors"):
                return _go(call, "floor", "ask_floor_building", floors=rec["floors"], walkup=", and no elevator" if rec.get("walkup") else "")
            return _go(call, "floor", "ask_floor")
        if row == "elevator" and have.get("has_elevator") is None:
            return _go(call, "elevator", "ask_elevator")
        if row == "door" and not have.get("door"):
            if s := side(_van_dropoff(f["building_id"])):
                call["side"] = s
                return _go(call, "door_aerial", "ask_door_aerial", side=s)
            return _go(call, "door", "ask_door")
        if row == "room" and not have.get("room"):
            return _go(call, "room", "ask_room" if c.get("room_names") else "ask_room_beds")
    if "home" in call.get("to_confirm", []):
        return _go(call, "check_home", "check_home", parts=_parts(have))
    if not f.get("home_confirmed"):
        return _go(call, "home_readback", "readback_home", parts=_parts(have))
    return _done(call, "reg_close")


def _go(call: dict, step: str, key: str, **vars) -> Lines:
    call["step"] = step
    return [(key, vars)]


def _done(call: dict, key: str) -> Lines:
    call["status"], call["step"] = "done", "close"
    return [(key, {})]


def _handoff(call: dict, why: str, *keys: str) -> Lines:
    call["status"], call["step"] = "handoff", "close"
    call["events"].append({"type": "handoff", "text": why})
    return [(k, {}) for k in keys] + [("human_handoff", {})]


def _device(call: dict, device: str) -> Lines:
    if device == "other":
        return _handoff(call, "equipment Hearth does not cover")
    call["facts"] |= {"device": device, "device_words": device.replace("_", " ")}
    return _next(call)


def _address(call: dict, t: Turn) -> Lines:
    rec = match_address(t.house_number, t.street, t.zip)
    if rec is None:
        return _address_miss(call)
    call["pending_address"] = {"building_id": rec["building_id"], "address": rec["address"], "unit_said": t.unit}
    return _go(call, "address_readback", "readback_address", address=_spoken(rec["address"]), unit=_unit_words(t.unit))


def _address_miss(call: dict) -> Lines:
    """A first miss (no single match, or a "no" to the read-back) asks once more; a second goes to a person."""
    call["address_tries"] = call.get("address_tries", 0) + 1
    if call["address_tries"] >= 2:
        return _handoff(call, "address not found", "address_not_found")
    return _go(call, "address", "ask_address")


def _confirm_address(call: dict) -> Lines:
    p = call.pop("pending_address")
    call["facts"] |= {"building_id": p["building_id"], "address": p["address"]}
    if p["unit_said"]:
        _set_unit(call, match_unit(_rec(call), p["unit_said"]), p["unit_said"])
    else:
        call["ctx"]["room_names"] = _room_names(p["building_id"], None)
    registry.save(call)
    return _next(call)


def _set_unit(call: dict, m: dict | None, said: str) -> None:
    """A unit in CoStar's list gives the floor plan, its scan and maybe its building; otherwise the caller's words stay."""
    f = call["facts"]
    if m:
        f |= {"unit": m["unit"], "plan": m["plan"], "scan_id": (m["scan_ids"] or [None])[0]}
        call["unit_building"] = m["building"]
    else:
        f["unit"] = said
    call["ctx"]["room_names"] = _room_names(f["building_id"], m["scan_ids"] if m and m["scan_ids"] else None)


def _hours_readback(call: dict, hours: float) -> Lines:
    call["pending"] = hours
    return _go(call, "hours_readback", "readback_hours", hours=say_hours(hours), supply="time without power")


def _which_part(call: dict, part: str | None) -> Lines:
    if part not in PART:
        return _go(call, "which_part", "ask_which_part")
    for k in PART[part] + ("home_confirmed",):
        call["facts"].pop(k, None)
        call["answers"].pop(k, None)
    if part == "building":
        call["unit_building"] = None
    return _next(call)


# ---- small readers ----
def _rec(call: dict) -> dict:
    return tools.costar_record(call["facts"]["building_id"]) or {}


def _van_dropoff(building_id: str) -> str | None:
    v = (store.get("profile", building_id) or {}).get("van_dropoff") or {}
    return v.get("value") if v.get("source") not in (None, "default") and isinstance(v.get("value"), str) else None


def _room_names(building_id: str, scan_ids: list[str] | None) -> list[str]:
    """The scan's room names, waiting at most voice.room_lookup_timeout_s; none on a timeout or an error."""
    # shortcut: fetched once per call, not cached; cache per building if Matterport latency shows on calls
    out: list[str] = []

    def fetch():
        try:
            out.extend(r["room"] for u in tools.matterport_rooms(building_id, scan_ids) for r in u.get("rooms", []) if r.get("room"))
        except Exception as e:  # Matterport down or a bad answer: the room question uses the bedroom wording
            log.warning("room names for %s failed: %r", building_id, e)
            out.clear()

    th = threading.Thread(target=fetch, daemon=True)
    th.start()
    th.join(a("voice.room_lookup_timeout_s"))
    return [] if th.is_alive() else sorted(set(out))


def _spoken(address: str) -> str:
    """"1200 Fixture St, Houston, TX 77002" -> "1200 Fixture St, Houston"."""
    return ", ".join(address.split(", ")[:2])


def _unit_words(unit: str | None) -> str:
    return f", apartment {norm_unit(unit) or unit}" if unit else ""


def _device_words(f: dict) -> str:
    return f.get("device_words") or f["device"].replace("_", " ")


def _parts(have: dict) -> str:
    parts = []
    if have.get("unit"):
        parts.append(f"in apartment {norm_unit(have['unit']) or have['unit']}")
    if have.get("complex_building"):
        parts.append(f"in building {have['complex_building']}")
    if have.get("floor") is not None:
        parts.append(f"on floor {have['floor']}")
    if have.get("door"):
        parts.append(f"using {have['door']}")
    if room := have.get("room"):
        parts.append(f"with the machine in {room if re.match(r'(the|my|a|an|our|his|her) ', room, re.I) else 'the ' + room}")
    return ", ".join(parts[:-1]) + (", and " if len(parts) > 1 else "") + (parts[-1] if parts else "")
