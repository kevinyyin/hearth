"""Crew access brief: a one-screen summary for a delivery, ride or welfare check.

Built only from fields whose source is not `default`. The layout comes from the scan; with no scan the brief
says so instead of guessing. Scans show common areas, never a specific resident's unit.
"""
from pydantic import BaseModel

from hearth.buildings.profile import FIELDS
from hearth.contracts import BuildingProfile, Evidence


class AccessBrief(BaseModel):
    stop_at: str | None
    entrance: str | None
    route: list[str]
    widths: str | None
    frames: list[Evidence]
    missing: list[str]


def access_brief(profile: BuildingProfile) -> AccessBrief:
    known = lambda f: getattr(profile, f).source != "default" and getattr(profile, f).value is not None
    note = lambda f: next((f" ({e.note})" for e in profile.evidence if e.field == f), "")

    stop_at = f"{profile.van_dropoff.value}{note('van_dropoff')}" if known("van_dropoff") else None
    entrance = None
    if known("step_free_entrance"):
        entrance = ("Step-free entrance" if profile.step_free_entrance.value else "No step-free entrance found") + note("step_free_entrance")
        if not profile.step_free_entrance.value and known("entrance_steps"):
            entrance += f"; {profile.entrance_steps.value} steps"
    widths = "; ".join(s for s in (
        f"narrowest door {profile.min_door_width_m.value} m" if known("min_door_width_m") else "",
        f"stairs {profile.stair_width_m.value} m wide" if known("stair_width_m") else "") if s) or None
    return AccessBrief(
        stop_at=stop_at, entrance=entrance, widths=widths,
        route=[f"{e.note} [{e.ref}]" for e in profile.evidence if e.layer == "matterport"],
        frames=[e for e in profile.evidence if e.layer in ("matterport", "vexcel")],
        missing=[layer for layer in ("vexcel", "matterport") if not any(getattr(profile, f).source == layer for f in FIELDS)],
    )
