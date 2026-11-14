"""Crew access brief: one screen for a delivery, ride or welfare check, in two parts (design amendment Nov 13).

Getting to the door: stories, walk-up or elevator (CoStar), where to stop and the entrance side (aerial).
Inside the unit: the floor plan of this unit type from the scan: rooms, hallway and door widths, steps.
Built only from fields whose source is not `default`. Scans show a unit type, never the patient's own rooms.
"""
from pydantic import BaseModel

from hearth.buildings.profile import FIELDS
from hearth.contracts import BuildingProfile, Evidence


class AccessBrief(BaseModel):
    unit_type: str | None
    to_door: list[str]
    inside_unit: list[str]
    frames: list[Evidence]
    missing: list[str]


def _room(r) -> str:
    if not isinstance(r, dict):
        return str(r)
    size = f" {r['width_m']} x {r['length_m']} m" if r.get("width_m") and r.get("length_m") else ""
    return f"{r.get('room', 'room')}{size}"


def access_brief(profile: BuildingProfile) -> AccessBrief:
    p = profile
    known = lambda f: getattr(p, f).source != "default" and getattr(p, f).value is not None
    v = lambda f: getattr(p, f).value
    src = lambda f: f" ({getattr(p, f).source})"
    note = lambda f: next((f": {e.note}" for e in p.evidence if e.field == f), "")

    to_door = []
    if known("floors"):
        to_door.append(f"{v('floors')} stories{src('floors')}")
    if known("elevator_count"):
        to_door.append(f"Walk-up: no passenger elevator{src('elevator_count')}" if v("elevator_count") == 0 else
                       f"{v('elevator_count')} passenger elevator(s); check it runs on backup power{src('elevator_count')}")
    if known("van_dropoff"):
        to_door.append(f"Stop: {v('van_dropoff')}{note('van_dropoff')}{src('van_dropoff')}")
    if known("step_free_entrance"):
        to_door.append(("Building entrance: step-free" if v("step_free_entrance") else "Building entrance: not step-free")
                       + (f", {v('entrance_steps')} steps" if known("entrance_steps") else "") + src("step_free_entrance"))
    if known("stair_width_m"):
        to_door.append(f"Stairs {v('stair_width_m')} m wide{src('stair_width_m')}")

    inside = []
    if known("unit_type"):
        inside.append(f"Floor plan of this unit type: {v('unit_type')} (a model unit, not the patient's own rooms)")
        if known("unit_rooms"):
            inside.append("Rooms: " + ", ".join(_room(r) for r in v("unit_rooms")))
        if known("hallway_width_m"):
            inside.append(f"Hallway {v('hallway_width_m')} m wide{note('hallway_width_m')}")
        if known("min_door_width_m"):
            inside.append(f"Narrowest door {v('min_door_width_m')} m")
        if known("interior_steps"):
            inside.append("No steps inside" if v("interior_steps") == 0 else f"{v('interior_steps')} steps inside")
    return AccessBrief(
        unit_type=v("unit_type") if known("unit_type") else None, to_door=to_door, inside_unit=inside,
        frames=[e for e in p.evidence if e.layer in ("matterport", "vexcel")],
        missing=[layer for layer in ("costar", "vexcel", "matterport") if not any(getattr(p, f).source == layer for f in FIELDS)],
    )
