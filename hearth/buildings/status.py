"""What someone said about a building today: power and a running elevator, with who said it and when.

One document per building, the latest answer. A resident answers on the impact call; a building's office on the
building call. Both are one person's word at one time, and every screen shows it that way.
"""
import time
from typing import Literal

from hearth import store


def record(building_id: str, said_by: Literal["resident", "building_office"], call_id: str, power: bool | None = None,
           elevator: Literal["yes", "no", "unknown"] | None = None) -> None:
    store.put("building_status", building_id, {"building_id": building_id, "said_by": said_by, "call_id": call_id,
                                               "power": power, "elevator": elevator, "t": time.time()})


def latest(building_id: str) -> dict | None:
    return store.get("building_status", building_id)
