"""Greedy crew assignment: the highest risk weight per hour left goes first, to the nearest free crew allowed to serve it."""
from dataclasses import dataclass
from typing import Callable

from hearth.config import a
from hearth.contracts import Job
from hearth.population import km


@dataclass
class Flags:
    use_buildings: bool = True
    allow_moves: bool = True
    mutual_aid: bool = False


@dataclass
class Need:
    patient_id: str
    kind: str  # delivery | ride | welfare_check
    supplier_id: str
    weight: float
    hours_until_empty: float
    lat: float
    lon: float
    service_h: float
    since_h: float  # when the need was raised (first come first served under p0)
    dest: tuple[float, float] | None = None  # rides only


@dataclass
class Crew:
    crew_id: str
    org_id: str  # the supplier the crew works for
    lat: float
    lon: float
    free_at_h: float = 0.0


def travel_h(a_: tuple[float, float], b: tuple[float, float], multiplier: float = 1.0) -> float:
    """Straight-line km times the detour factor, at the configured speed."""
    return float(km(a_[0], a_[1], b[0], b[1])) * a("travel.detour_factor") / a("travel.speed_kmh") * multiplier


def assign(needs: list[Need], crews: list[Crew], stock: dict, flags: Flags, now_h: float, fcfs: bool = False,
           fits: Callable[[Need, Crew], bool] | None = None) -> list[Job]:
    """Accepted jobs for free crews. Mutates the chosen crews (busy until done, at the drop-off) and stock.
    A delivery needs a crew of the patient's supplier (any supplier with mutual aid) and a unit of that crew's stock;
    a need nobody can serve now stays in `needs` for the caller to offer again. `fits` refuses crews that cannot take a need."""
    key = (lambda n: (n.since_h, n.patient_id)) if fcfs else (lambda n: (-n.weight / max(n.hours_until_empty, 0.1), n.patient_id))
    free, jobs = [c for c in crews if c.free_at_h <= now_h], []
    for n in sorted(needs, key=key):
        if not free:
            break
        ok = [c for c in free if (n.kind != "delivery" or ((flags.mutual_aid or c.org_id == n.supplier_id) and stock.get(c.org_id, 0) > 0))
              and (fits is None or fits(n, c))]
        if not ok:
            continue
        c = min(ok, key=lambda c: (travel_h((c.lat, c.lon), (n.lat, n.lon)), c.crew_id))
        done = now_h + travel_h((c.lat, c.lon), (n.lat, n.lon)) + n.service_h + (travel_h((n.lat, n.lon), n.dest) if n.dest else 0.0)
        if n.kind == "delivery":
            stock[c.org_id] -= 1
        c.free_at_h, (c.lat, c.lon) = done, (n.dest or (n.lat, n.lon))
        free.remove(c)
        jobs.append(Job(job_id=f"{n.kind}-{n.patient_id}-{now_h:g}", kind=n.kind, patient_id=n.patient_id, org_id=c.org_id,
                        status="accepted", data={"crew_id": c.crew_id, "done_h": done, **({"dest": list(n.dest)} if n.dest else {})}))
    return jobs
