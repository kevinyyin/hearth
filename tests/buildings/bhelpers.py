"""Test-only builders for building profiles."""
from hearth.buildings.profile import FIELDS, default_profile
from hearth.contracts import Sourced

_MAP = {  # short name -> (profile field, layer)
    "floors": ("floors", "costar"), "year": ("year_built", "costar"), "construction": ("construction", "costar"),
    "elevators": ("elevator_count", "costar"), "property_type": ("property_type", "costar"),
    "roof": ("roof_tone", "vexcel"), "tree": ("tree_cover_fraction", "vexcel"), "van": ("van_dropoff", "vexcel"),
    "step_free": ("step_free_entrance", "matterport"), "steps": ("entrance_steps", "matterport"),
    "stair_w": ("stair_width_m", "matterport"), "door_w": ("min_door_width_m", "matterport"),
}


def profile(building_id="B", **kw):
    p = default_profile(building_id, "1 Test St", 29.76, -95.37)
    for short, value in kw.items():
        field, layer = _MAP[short]
        setattr(p, field, Sourced(value=value, source=layer, confidence=0.9))
    p.layers_missing = sorted({"costar", "vexcel", "matterport"} - {_MAP[k][1] for k in kw})
    return p


def fields(**kw):
    p = profile(**kw)
    return {f: getattr(p, f) for f in FIELDS}
