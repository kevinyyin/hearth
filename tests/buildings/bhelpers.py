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


def patient(**over):
    from hearth.contracts import Patient
    base = dict(patient_id="p1", lat=29.7604, lon=-95.3698, zip="77002", floor=3, device="oxygen", device_detail="concentrator",
                backup_hours_on_hand=6.0, use_rate=1.0, mobility="walks", can_self_relocate=False, temp_sensitive="heat",
                risk_weight=3.0, supplier_id="s1", building_id="B-SAMPLE", phone_status="verified", profile_status="complete")
    return Patient(**base | over)


def seed_pending_proposal(pid, patient_id="p1"):
    from hearth import store
    from hearth.contracts import RefugeOption, RefugeProposal
    opt = RefugeOption(building_id="H-LEVEL", name="Fixture Hotel", lat=29.71, lon=-95.40, reasons=["step-free entrance"], sources=["matterport"], score=1.0)
    store.put("proposal", pid, RefugeProposal(proposal_id=pid, patient_id=patient_id, options=[opt], status="pending", thread_id=f"t-{pid}"))
