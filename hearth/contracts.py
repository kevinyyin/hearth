"""Shared contracts. Every lane reads and writes these shapes; change them only through lane M."""
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanState(StrEnum):
    NOT_AFFECTED = "NOT_AFFECTED"
    OWN_BACKUP = "OWN_BACKUP"
    RESUPPLY = "RESUPPLY"
    MOVE = "MOVE"
    MOVED = "MOVED"
    URGENT = "URGENT"
    UNREACHABLE = "UNREACHABLE"
    RESTORED = "RESTORED"


class Device(StrEnum):
    oxygen = "oxygen"
    ventilator = "ventilator"
    home_dialysis = "home_dialysis"
    feeding_pump = "feeding_pump"


class Mobility(StrEnum):
    walks = "walks"
    walks_with_help = "walks_with_help"
    wheelchair_manual = "wheelchair_manual"
    wheelchair_power = "wheelchair_power"
    bedbound = "bedbound"


class Patient(BaseModel):
    patient_id: str
    synthetic: Literal[True] = True
    lat: float
    lon: float
    zip: str
    floor: int
    device: Device
    device_detail: str
    backup_hours_on_hand: float
    use_rate: float
    mobility: Mobility
    can_self_relocate: bool
    temp_sensitive: Literal["heat", "cold", "both", "none"]
    risk_weight: float
    supplier_id: str
    building_id: str | None
    phone_status: Literal["verified", "unverified", "missing"]
    profile_status: Literal["complete", "partial", "none"]
    phone: str | None = None


class Sourced(BaseModel):
    value: Any
    source: Literal["costar", "matterport", "vexcel", "default"]
    confidence: float = Field(ge=0, le=1)


class Evidence(BaseModel):
    field: str
    layer: str
    ref: str  # image path or panorama id
    note: str


class BuildingProfile(BaseModel):
    building_id: str
    address: str
    lat: float
    lon: float
    floors: Sourced
    units: Sourced
    year_built: Sourced
    construction: Sourced
    property_type: Sourced
    elevator_count: Sourced
    roof_tone: Sourced
    tree_cover_fraction: Sourced
    step_free_entrance: Sourced
    entrance_steps: Sourced
    stair_width_m: Sourced
    min_door_width_m: Sourced
    van_dropoff: Sourced
    heat_time_constant_h: float
    cold_time_constant_h: float
    layers_missing: list[str]
    evidence: list[Evidence]
    conflicts: list[str]
    cached: bool = False
    error: str | None = None


class PatientSnap(BaseModel):
    id: str
    lat: float
    lon: float
    device: Device
    state: PlanState
    backup_hours: float
    indoor_temp_c: float
    unpowered: bool
    building_id: str | None


class Snapshot(BaseModel):
    t: datetime
    patients: list[PatientSnap]
    crews: list[dict]
    depots: list[dict]


class Event(BaseModel):
    t: datetime
    type: str
    patient_id: str | None = None
    data: dict = {}


class Job(BaseModel):
    job_id: str
    kind: Literal["delivery", "ride", "welfare_check"]
    patient_id: str
    org_id: str
    status: Literal["created", "accepted", "completed", "failed"]
    eta: datetime | None = None
    data: dict = {}


class RefugeOption(BaseModel):
    building_id: str
    name: str
    lat: float
    lon: float
    reasons: list[str]
    sources: list[str]
    score: float


class RefugeProposal(BaseModel):
    proposal_id: str
    patient_id: str
    options: list[RefugeOption]
    status: Literal["pending", "approved", "rejected"]
    reason: str | None = None
    thread_id: str


class TraceEvent(BaseModel):
    seq: int
    t: float
    kind: Literal["todo", "subagent", "tool", "file", "conflict", "profile", "interrupt", "done"]
    agent: str
    text: str
    data: dict = {}


def run_id(scenario: str, policy: str, crews: int, seed: int) -> str:
    return f"{scenario}__{policy}__c{crews}__s{seed}"
