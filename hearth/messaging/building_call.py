"""The call to a building's office: does it have power, and is a passenger elevator running? Never names a resident or
says that anyone there uses medical equipment. The number comes only from HEARTH_BUILDING_PHONES; kit numbers are fake.

staff -> power -> [elevator, skipped for a one-story record] -> readback -> close
"""
from hearth.buildings import status
from hearth.messaging.interpreter import Turn

Lines = list[tuple[str, dict]]


def opening(call: dict) -> Lines:
    c = call["ctx"]
    return _go(call, "staff", "bldg_open", county=c["county"], name=c["name"], address=c["address"])


def advance(call: dict, t: Turn) -> Lines:
    step, f = call["step"], call["facts"]
    yes = t.confirms if t.elevator_working is None else {"yes": True, "no": False}.get(t.elevator_working)
    if step == "staff" and t.confirms is not None:
        if not t.confirms:
            call["status"], call["step"] = "done", "close"
            return [("bldg_not_staff", {})]
        return _go(call, "power", "bldg_power")
    if step == "power" and t.confirms is not None:
        f["power"] = t.confirms
        return _readback(call) if call["ctx"].get("one_story") else _go(call, "elevator", "bldg_elevator")
    if step == "elevator" and (yes is not None or t.elevator_working == "unknown"):
        f["elevator"] = "unknown" if yes is None else "yes" if yes else "no"
        return _readback(call)
    if step == "readback" and t.confirms is not None:
        if not t.confirms:
            f.clear()
            return _go(call, "power", "bldg_power")
        status.record(call["ctx"]["building_id"], "building_office", call["call_id"], power=f["power"], elevator=f.get("elevator"))
        call["status"], call["step"] = "done", "close"
        return [("bldg_close", {})]
    if step == "close":
        return [("bldg_close", {})]
    return [tuple(call["last"])] if call.get("last") else opening(call)


def _readback(call: dict) -> Lines:
    f = call["facts"]
    elevator = {"yes": ", and a passenger elevator is running", "no": ", and no passenger elevator is running",
                "unknown": ", and you don't know about the elevator"}.get(f.get("elevator"), "")
    return _go(call, "readback", "bldg_readback", power="has power" if f["power"] else "does not have power", elevator=elevator)


def _go(call: dict, step: str, key: str, **vars) -> Lines:
    call["step"] = step
    return [(key, vars)]
