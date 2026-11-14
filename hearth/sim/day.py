"""The simulation page's 24-hour day, with the central planner deciding which van goes where.

This is the Hearth half of `runSide` in web/lib/simulation.ts with its dispatch step replaced by `hearth.routing`: the
same households, stations, speeds, rounds and restock rule (the page sends its own constants), and the same shape back,
so the page draws it without knowing where it came from. Plain Python: the hosted API has no numpy.
"""
import math
import random

from hearth.config import a
from hearth.planner import Crew, Flags, Need
from hearth.routing import routes

FIRST, RESTOCK = 2.0, 1.0  # a household that has had nothing yet weighs twice one waiting on a restock


def weighted_wait(side: dict, run_hours: float) -> float:
    """`weightedWait` in web/lib/simulation.ts: hours waited, a visit that never came counted to the end of the day."""
    return sum((RESTOCK if j["refill"] else FIRST) * ((run_hours if j["servedAt"] is None else j["servedAt"]) - j["dueAt"])
               for j in side["jobs"])


def run_day(households: list[dict], k: dict, routing: str = "alns", seed: int = 0) -> dict:
    """One day for the Hearth side, as the page's `SideSim`. `k` is the page's DAY_CONSTANTS."""
    stations, cruise, service, run_hours = k["stations"], k["cruise"], k["serviceH"], k["runHours"]
    vans = len(stations) * k["crewsPerStation"]
    station = [c % len(stations) for c in range(vans)]
    base = [tuple(reversed(stations[s]["at"])) for s in station]  # the page writes [lon, lat]; the planner (lat, lon)
    legs, free_at = [[] for _ in range(vans)], [0.0] * vans
    jobs, events = [], []
    tours = stops = refills = 0

    def travel(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1]) / cruise

    def add_job(h: int, due: float, refill: bool) -> None:
        # Hearth has the registry: the order exists the moment the need does
        jobs.append({"h": h, "dueAt": due, "knownAt": due, "sentAt": None, "servedAt": None, "refill": refill})
        events.append({"t": due, "kind": "call", "text": f"Called household {h + 1} — on the registry, device down"})

    for i, h in enumerate(households):
        add_job(i, h["needsAt"], False)

    for step in range(int(run_hours / k["dt"]) + 1):
        t = step * k["dt"]
        waiting = [i for i, j in enumerate(jobs) if j["sentAt"] is None and j["dueAt"] <= t]
        if not waiting or not any(f <= t for f in free_at):
            continue
        waiting.sort(key=lambda i: (jobs[i]["refill"], jobs[i]["dueAt"], i))  # most urgent first, as the planner expects
        needs = [Need(str(i), "delivery", "", RESTOCK if jobs[i]["refill"] else FIRST, jobs[i]["dueAt"] - t,
                      households[jobs[i]["h"]]["lat"], households[jobs[i]["h"]]["lon"], service, 0.0) for i in waiting]
        crews = [Crew(str(c), "", *base[c], free_at_h=free_at[c], base=base[c], capacity=k["capacity"]) for c in range(vans)]
        planned = routes(needs, crews, {"": 10 ** 9}, Flags(mutual_aid=True), t, routing=routing, travel=travel,
                         rng=random.Random(f"{seed}:{step}"), tune=a("planner.day"))
        for c in range(vans):
            route = [int(n.patient_id) for n in planned.get(str(c), [])][: k["capacity"]]
            if free_at[c] > t or not route:
                continue
            home = stations[station[c]]["at"]
            for i in route:
                jobs[i]["sentAt"] = t
            events.append({"t": t, "kind": "dispatch", "stops": len(route),
                           "text": f"Crew {c + 1} out of {stations[station[c]]['name']} — "
                                   + (f"{len(route)} stops chained" if len(route) > 1 else "1 stop, then back")})
            clock, here = t, home
            for n, i in enumerate(route):
                j = jobs[i]
                hh = households[j["h"]]
                to = [hh["lon"], hh["lat"]]
                drive = math.hypot(here[0] - to[0], here[1] - to[1]) / cruise
                legs[c].append({"from": here, "to": to, "t0": clock, "t1": clock + drive, "departure": n == 0})
                clock += drive
                # parked at the door; the household changes colour when the van pulls away
                legs[c].append({"from": to, "to": to, "t0": clock, "t1": clock + service, "departure": False})
                clock += service
                j["servedAt"] = clock
                stops += 1
                refills += j["refill"]
                events.append({"t": clock, "kind": "restock" if j["refill"] else "arrive",
                               "text": f"Crew {c + 1} {'restocked' if j['refill'] else 'helped'} household {j['h'] + 1}"})
                if hh["repeats"] and clock + k["refillH"] <= run_hours:  # a delivery runs down: another visit later
                    add_job(j["h"], clock + k["refillH"], True)
                here = to
            back = math.hypot(here[0] - home[0], here[1] - home[1]) / cruise
            legs[c].append({"from": here, "to": home, "t0": clock, "t1": clock + back, "departure": False})
            free_at[c] = clock + back
            tours += 1

    events.sort(key=lambda e: e["t"])
    return {"jobs": jobs, "calls": [], "legs": legs, "station": station, "tours": tours, "stops": stops, "refills": refills,
            "events": events}
