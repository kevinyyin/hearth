"""Phone registrations: a call's confirmed facts become the patient, contact and home documents the help loop reads.

Only numbers in HEARTH_DEMO_CALLERS may register (a stranger's real details never reach the store). Every number here
comes from the environment; a phone number in the CoStar kit is fake and is never dialed.
"""
import os
import time
import uuid
from datetime import datetime, timezone

from hearth import store
from hearth.buildings import tools
from hearth.config import a
from hearth.contracts import Home, Patient

NEEDED = ("device", "building_id", "backup_hours", "floor")  # every required patient field the call asks
KINDS = ("patient", "contact", "home", "help")


def _env_list(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


def demo_callers() -> set[str]:
    return set(_env_list("HEARTH_DEMO_CALLERS"))


def alert_phones() -> list[str]:
    return _env_list("HEARTH_ALERT_PHONES")


def building_phones() -> dict[str, str]:
    return {k.strip(): v.strip() for k, _, v in (x.partition("=") for x in _env_list("HEARTH_BUILDING_PHONES")) if v.strip()}


def save(call: dict) -> str | None:
    """Writes or updates the records once every asked required field is confirmed; until then nothing is written."""
    f = call["facts"]
    if any(f.get(k) is None for k in NEEDED) or (rec := tools.costar_record(f["building_id"])) is None:
        return None
    pid = call["patient_id"] or f"R-{uuid.uuid4().hex[:8]}"
    old = store.get("patient", pid) or {}
    d = a("registration.defaults")
    patient = Patient(**(d | {"mobility": old.get("mobility", d["mobility"])}), patient_id=pid, lat=rec["lat"], lon=rec["lon"],
                      zip=rec.get("zip") or "", floor=f["floor"], device=f["device"], backup_hours_on_hand=f["backup_hours"],
                      building_id=f["building_id"], phone_status="unverified", profile_status="complete")
    cut = lambda v, n: v[:n] if isinstance(v, str) else v  # noqa: E731  a long answer is cut to fit, never a reason to lose the call
    home = Home(**(store.get("home", pid) or {}) | {
        "patient_id": pid, "building_id": f["building_id"], "ok_without_h": f["backup_hours"], "device_name": cut(f.get("device_words") or "", 120),
        "source": "phone", "unit": cut(f.get("unit"), 20), "complex_building": cut(f.get("complex_building"), 40), "scan_id": f.get("scan_id"),
        "door": cut(f.get("door") or "", 200), "door_from_aerial": bool(f.get("door_from_aerial")), "room": cut(f.get("room") or "", 120),
        "scan_room": cut(f.get("scan_room"), 80), "has_elevator": f.get("has_elevator"), "said_at": datetime.now(timezone.utc)})
    # a check call placed by the storm button carries no phone in its context: the registration's own contact stands
    phone = call["ctx"].get("phone") or (store.get("contact", pid) or {}).get("phone")
    store.put("patient", pid, patient)
    if phone:
        store.put("contact", pid, {"patient_id": pid, "phone": phone})
    store.put("home", pid, home)
    call["patient_id"] = pid
    return pid


def _phone_homes() -> list[str]:
    """Patient ids with a phone registration, oldest write first."""
    return [h["patient_id"] for h in store.all("home") if h.get("source") == "phone"]


def patient_for_phone(phone: str) -> str | None:
    """The newest phone registration for this number. Contacts made for synthetic demo patients do not count."""
    mine = [pid for pid in _phone_homes() if (store.get("contact", pid) or {}).get("phone") == phone]
    return max(mine, key=lambda pid: store.get("home", pid).get("said_at") or "", default=None)


def registrations() -> dict:
    """For the dispatch page: phone registrations, and registration calls that ended before any record was written."""
    calls = [c for c in store.all("call") if c.get("kind") == "register"]
    last = {c["patient_id"]: c for c in sorted(calls, key=lambda c: c.get("started_at", 0)) if c.get("patient_id")}
    registered = []
    for pid in _phone_homes():
        if not (p := store.get("patient", pid)):
            continue
        home, c = Home(**store.get("home", pid)), last.get(pid)
        registered.append({"patient": Patient(**p), "home": home, "address": (tools.costar_record(home.building_id) or {}).get("address"),
                           "call_id": c and c["call_id"], "call_status": c and c["status"]})
    registered.sort(key=lambda r: r["home"].said_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    quiet = time.time() - a("voice.unfinished_after_min") * 60  # the server is not told about a hang-up: a call that went quiet counts
    last = lambda c: max([m.get("t", 0) for m in c.get("transcript") or []] + [c.get("started_at") or 0])  # noqa: E731
    needs = [{"call_id": c["call_id"], "phone": c["ctx"].get("phone"), "facts": c["facts"], "started_at": c.get("started_at"),
              "status": "unfinished" if c["status"] == "active" else c["status"]}
             for c in calls if not c.get("patient_id") and (c["status"] in ("handoff", "escalated") or (c["status"] == "active" and last(c) < quiet))]
    needs.sort(key=lambda r: r["started_at"] or 0, reverse=True)
    return {"registered": registered, "needs_person": needs}


def reset(phone: str) -> int:
    """Removes every registration this number made, so a rehearsal starts clean."""
    mine = [pid for pid in _phone_homes() if (store.get("contact", pid) or {}).get("phone") == phone]
    for pid in mine:
        for kind in KINDS:
            store.delete(kind, pid)
    return len(mine)


def facts_for(patient_id: str) -> dict:
    """A registration's answers in the facts shape the call scripts use, all of them already confirmed."""
    p, h = store.get("patient", patient_id) or {}, store.get("home", patient_id) or {}
    return {"has_equipment": True, "home_confirmed": True, "device": p.get("device"), "device_words": h.get("device_name"),
            "building_id": h.get("building_id"), "address": (tools.costar_record(h.get("building_id") or "") or {}).get("address"),
            "unit": h.get("unit"), "scan_id": h.get("scan_id"), "complex_building": h.get("complex_building"),
            "backup_hours": h.get("ok_without_h"), "floor": p.get("floor"), "has_elevator": h.get("has_elevator"),
            "door": h.get("door"), "door_from_aerial": h.get("door_from_aerial"), "room": h.get("room"), "scan_room": h.get("scan_room")}


def storm() -> dict:
    """The simulated storm: the county alert text to each alert phone, and a check call to every phone registrant whose
    ZIP is in the forecast area. Every failure is listed, never raised, so one bad number does not stop the rest."""
    from hearth.messaging import photon, voice  # late: voice imports this module
    from hearth.messaging.templates import render

    out = {"alerted": [], "dialed": [], "failed": []}
    line = os.environ.get("HEARTH_LINE_NUMBER")
    for phone in alert_phones():
        try:
            if not line:
                raise LookupError("HEARTH_LINE_NUMBER is not set, so the alert cannot say what to call")
            photon._send(phone, render("alert_text", line=line))
            out["alerted"].append(phone)
        except Exception as e:
            out["failed"].append(f"{phone}: {e}")
    zips = set(a("storm.forecast_zips"))
    for pid in dict.fromkeys(_phone_homes()):
        if (store.get("patient", pid) or {}).get("zip") not in zips:
            continue
        try:
            if voice.dial(voice.start_call(pid, "check", storm=True)):
                out["dialed"].append(pid)
            else:
                out["failed"].append(f"{pid}: not dialed (the phone line is not set up)")
        except Exception as e:
            out["failed"].append(f"{pid}: {e}")
    return out
