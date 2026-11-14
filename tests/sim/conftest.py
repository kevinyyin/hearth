"""Test-only builders for patients and decision contexts."""
from hearth.contracts import Patient
from hearth.decision import Ctx

_PATIENT = dict(
    patient_id="p1", lat=29.76, lon=-95.37, zip="77002", floor=3, device="oxygen",
    device_detail="concentrator", backup_hours_on_hand=6.0, use_rate=1.0, mobility="walks",
    can_self_relocate=True, temp_sensitive="none", risk_weight=3.0, supplier_id="s1",
    building_id=None, phone_status="verified", profile_status="complete",
)


def pat(**overrides) -> Patient:
    return Patient(**{**_PATIENT, **overrides})


def ctx(restoration=48, home_unsafe=False, temp_unsafe=False, delivery=False, move=False, allow_moves=True) -> Ctx:
    return Ctx(restoration, home_unsafe, temp_unsafe, delivery, move, allow_moves)
