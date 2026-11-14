"""Derived numbers are code, not model: time constants, service minutes, hours to unsafe.

The time-constant formula is a published heuristic (coefficients in config/assumptions.yaml under building.tc).
"""
import math

from hearth.config import a
from hearth.contracts import BuildingProfile, Sourced

FIELDS = ["floors", "units", "year_built", "construction", "property_type", "elevator_count", "roof_tone",
          "tree_cover_fraction", "step_free_entrance", "entrance_steps", "stair_width_m", "min_door_width_m", "van_dropoff",
          "unit_type", "unit_rooms", "hallway_width_m", "interior_steps"]
LAYERS = ("costar", "vexcel", "matterport")
UNKNOWN = Sourced(value=None, source="default", confidence=0.0)


def default_profile(building_id: str, address: str, lat: float, lon: float) -> BuildingProfile:
    return BuildingProfile(building_id=building_id, address=address, lat=lat, lon=lon, **{f: UNKNOWN for f in FIELDS},
                           heat_time_constant_h=float(a("temperature.default_heat_tc_h")),
                           cold_time_constant_h=float(a("temperature.default_cold_tc_h")),
                           layers_missing=list(LAYERS), evidence=[], conflicts=[])


def _age_factor(year) -> float:
    age = a("building.tc.age")
    if not isinstance(year, (int, float)):
        return 1.0
    return age["before_1980"] if year < 1980 else age["from_1980"] if year < 2000 else age["from_2000"]


def time_constants(fields: dict[str, Sourced]) -> tuple[float, float]:
    """(heat_h, cold_h). Unknown values contribute a factor of 1."""
    v = lambda f: fields[f].value if f in fields else None
    construction = a("building.tc.construction").get(str(v("construction")).lower(), 1.0)
    roof = a("building.tc.roof").get(str(v("roof_tone")).lower(), 1.0)
    tree = v("tree_cover_fraction")
    shade = 1 + a("building.tc.shade_per_tree_cover") * (tree if isinstance(tree, (int, float)) else 0.0)
    age = _age_factor(v("year_built"))
    lo, hi = a("building.tc.clamp_h")
    clamp = lambda h: float(min(hi, max(lo, h)))
    return (clamp(a("temperature.default_heat_tc_h") * construction * roof * shade * age),
            clamp(a("temperature.default_cold_tc_h") * construction * age))


def finalize(profile: BuildingProfile) -> BuildingProfile:
    heat, cold = time_constants({f: getattr(profile, f) for f in FIELDS})
    return profile.model_copy(update={"heat_time_constant_h": heat, "cold_time_constant_h": cold})


def service_minutes(profile: BuildingProfile, patient_floor: int, elevator_working: bool) -> float:
    base = a("building.service_base_min")
    if not elevator_working or profile.elevator_count.value == 0:
        return base + a("building.service_min_per_floor_no_elevator") * patient_floor
    return base


def hours_to_unsafe(heat_tc_h: float, outdoor_c: float = 35.0) -> float:
    """First-order rise from the setpoint to the unsafe threshold; inf if the outdoors never gets there."""
    setpoint, unsafe = a("temperature.setpoint_c"), a("temperature.unsafe_heat_index_c")
    if outdoor_c <= unsafe:
        return math.inf
    return heat_tc_h * math.log((outdoor_c - setpoint) / (outdoor_c - unsafe))


def layer_effects(profile: BuildingProfile) -> dict[str, float]:
    """layer -> hours_to_unsafe if that layer's fields were reset to default (what the layer changed)."""
    out = {}
    for layer in LAYERS:
        fields = {f: UNKNOWN if getattr(profile, f).source == layer else getattr(profile, f) for f in FIELDS}
        out[layer] = hours_to_unsafe(time_constants(fields)[0])
    return out
