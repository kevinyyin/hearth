from bhelpers import profile

from hearth.buildings.brief import access_brief
from hearth.buildings.profile import default_profile, finalize
from hearth.contracts import Evidence


def profile_with_evidence():
    p = profile(floors=8, elevators=0, van="curb on the south side, 12 m from the building", step_free=False, steps=3,
                unit_type="2BR, 1BA - 900SF", rooms=[{"room": "bedroom", "width_m": 3.0, "length_m": 3.4, "area_m2": 10.2}],
                hallway_w=1.0, door_w=0.8, int_steps=0)
    p.evidence = [
        Evidence(field="floors", layer="costar", ref="costar", note="8 stories"),
        Evidence(field="van_dropoff", layer="vexcel", ref="vexcel.png", note="driveway detected south, conf 0.68"),
        Evidence(field="hallway_width_m", layer="matterport", ref="M1-loc2", note="hallway from the front door to the bedroom"),
    ]
    return finalize(p)


def test_brief_never_invents_layout():
    b = access_brief(finalize(default_profile("B", "x", 0, 0)))
    assert b.to_door == [] and b.inside_unit == [] and b.frames == [] and b.unit_type is None
    assert set(b.missing) == {"costar", "vexcel", "matterport"}


def test_brief_has_two_parts_from_the_right_layers():
    b = access_brief(profile_with_evidence())
    door = " ".join(b.to_door)
    assert "8 stories" in door and "walk-up" in door.lower() and "south side" in door and "3 steps" in door
    assert b.inside_unit[0].startswith("Floor plan of this unit type: 2BR, 1BA - 900SF") and "not the patient's own" in b.inside_unit[0]
    inside = " ".join(b.inside_unit)
    assert "bedroom 3.0 x 3.4 m" in inside and "hallway 1.0 m" in inside.lower() and "0.8 m" in inside
    assert b.frames and all(f.layer in ("matterport", "vexcel") for f in b.frames) and b.missing == []


def test_no_scan_means_no_inside_part():
    b = access_brief(finalize(profile(floors=3, elevators=1)))
    assert b.inside_unit == [] and "matterport" in b.missing and any("elevator" in line for line in b.to_door)
