"""Plan states as small ints, and hearth.decision's rules over whole arrays (tests keep the two identical)."""
import numpy as np

from hearth.config import a
from hearth.contracts import PlanState

STATES = list(PlanState)
CODE = {s: i for i, s in enumerate(STATES)}
NA, OWN, RES, MOVE, MOVED, URG, UNR, RESTORED = (CODE[s] for s in STATES)
WHY = {OWN: "backup covers the horizon plus margin",
       RES: "backup short of the horizon plus margin, or home forecast unsafe and no move possible",
       MOVE: "home unsafe or forecast unsafe, or no delivery possible", URG: "no delivery or move possible",
       UNR: "not reached yet; silence is not treated as safe", MOVED: "ride completed", RESTORED: "power restored", NA: "power on"}


def decide_vec(device, sens, backup, hours_to_restoration, home_unsafe, temp_unsafe, delivery, move, allow_moves) -> np.ndarray:
    """hearth.decision.decide for every patient at once; the first rule that applies wins."""
    can_move = move & allow_moves
    mou = np.where(can_move, MOVE, URG)
    conds = [home_unsafe, (sens != "none") & temp_unsafe, device == "home_dialysis",
             backup >= hours_to_restoration + a("decision.margin_h"), delivery]
    picks = [mou, np.where(can_move, MOVE, np.where(delivery, RES, URG)), mou, OWN, RES]
    return np.select(conds, picks, mou).astype(np.int8)


def hysteresis_vec(prev, proposed, streak):
    """hearth.decision.with_hysteresis for every patient at once: (state, streak)."""
    pair = ((prev == RES) & (proposed == MOVE)) | ((prev == MOVE) & (proposed == RES))
    hold = pair & (streak + 1 < a("decision.hysteresis_ticks"))
    return np.where(hold, prev, proposed).astype(np.int8), np.where(hold, streak + 1, 0)
