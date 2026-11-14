"""Per-patient plan state for one tick, and hysteresis between RESUPPLY and MOVE."""
from dataclasses import dataclass

from hearth.config import a
from hearth.contracts import Patient, PlanState


@dataclass
class Ctx:
    hours_to_restoration: float
    home_unsafe: bool
    temp_unsafe_before_restoration: bool
    delivery_feasible: bool
    move_feasible: bool
    allow_moves: bool = True


def decide(patient: Patient, backup_h: float, ctx: Ctx) -> PlanState:
    can_move = ctx.allow_moves and ctx.move_feasible
    move_or_urgent = PlanState.MOVE if can_move else PlanState.URGENT
    if ctx.home_unsafe:
        return move_or_urgent
    if patient.temp_sensitive != "none" and ctx.temp_unsafe_before_restoration:
        # never OWN_BACKUP: a charged device does not make a hot or cold home safe
        if can_move:
            return PlanState.MOVE
        return PlanState.RESUPPLY if ctx.delivery_feasible else PlanState.URGENT
    if patient.device == "home_dialysis":
        return move_or_urgent
    if backup_h >= ctx.hours_to_restoration + a("decision.margin_h"):
        return PlanState.OWN_BACKUP
    if ctx.delivery_feasible:
        return PlanState.RESUPPLY
    return move_or_urgent


def with_hysteresis(prev: PlanState, proposed: PlanState, streak: int) -> tuple[PlanState, int]:
    if {prev, proposed} == {PlanState.RESUPPLY, PlanState.MOVE} and streak + 1 < a("decision.hysteresis_ticks"):
        return prev, streak + 1
    return proposed, 0
