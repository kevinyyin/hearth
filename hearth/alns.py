"""Route search for the central planner (adaptive large neighbourhood search): several jobs per crew over the look-ahead
window, improved by taking some jobs out of the plan and putting them back better. Plain Python, a fixed number of
iterations and the caller's seeded random stream, so the same inputs always give the same routes.

The score is `plan_cost`: `routing.cost` at the hour each routed need is reached, the end-of-window cost for every need
left out, and a hair per crew-hour to prefer the shorter of two equal plans.
"""
import math
import random
from typing import Callable

from hearth.config import a
from hearth.planner import Crew, Need
from hearth.routing import Travel, _cost

Routes = dict[str, list[Need]]  # crew id -> the needs it serves, in order
TIE = 1e-6  # per crew-hour


def _walk(c: Crew, route: list[Need], now_h: float, travel: Travel):
    """Yields (need, hour reached), then (None, crew-hours used). A crew with a capacity goes back to base when full."""
    t = start = max(now_h, c.free_at_h)
    pos, held = (c.lat, c.lon), 0
    for n in route:
        if c.capacity and held == c.capacity:
            t, pos, held = t + travel(pos, c.base), c.base, 0
        at = (n.lat, n.lon)
        t += travel(pos, at)
        yield n, t
        t += n.service_h
        if n.dest:
            t += travel(at, n.dest)
        pos, held = n.dest or at, held + 1
    yield None, t - start


def reach_times(c: Crew, route: list[Need], now_h: float, travel: Travel) -> list[float]:
    return [t for n, t in _walk(c, route, now_h, travel) if n is not None]


def _route_cost(c: Crew, route: list[Need], now_h: float, travel: Travel, early: float) -> float:
    return sum(TIE * t if n is None else _cost(n, t - now_h, early) for n, t in _walk(c, route, now_h, travel))


def plan_cost(routes: Routes, pool: list[Need], crews: list[Crew], now_h: float, travel: Travel) -> float:
    horizon, early = a("planner.lookahead_h"), a("planner.early_weight")
    routed = {id(n) for r in routes.values() for n in r}
    return (sum(_route_cost(c, routes.get(c.crew_id, []), now_h, travel, early) for c in crews)
            + sum(_cost(n, horizon, early) for n in pool if id(n) not in routed))


def search(start: Routes, pool: list[Need], crews: list[Crew], can: Callable[[Need, Crew], bool], now_h: float, *,
           travel: Travel, rng: random.Random) -> Routes:
    """The best plan found from `start`: never worse than it by `plan_cost`. `pool` is every need in play, most urgent
    first; `crews` are the crews in play; `can(need, crew)` says who may serve whom."""
    horizon, early = a("planner.lookahead_h"), a("planner.early_weight")
    by_id = {c.crew_id: c for c in crews}
    left_out = {id(n): _cost(n, horizon, early) for n in pool}  # what each need costs when no route reaches it
    # speed cut: a need is only tried in the routes of the few nearest crews that can take it (nearest by where each
    # crew starts, in plain degrees: this only prunes, the score uses real travel time)
    k = a("planner.insert_nearest_crews")
    near = {id(n): [c for c in sorted(crews, key=lambda c: ((c.lat - n.lat) ** 2 + (c.lon - n.lon) ** 2, c.crew_id))[: 3 * k]
                    if can(n, c)][:k] for n in pool}

    def rcost(cid: str, route: list[Need]) -> float:
        return _route_cost(by_id[cid], route, now_h, travel, early)

    def places(routes: Routes, costs: dict, n: Need) -> list[tuple[float, str, int]]:
        """Every (change in the score, crew, position) for putting this need into a route, best first."""
        out = []
        for c in near[id(n)]:
            route = routes.get(c.crew_id, [])
            base = costs.get(c.crew_id, 0.0)
            out += [(rcost(c.crew_id, route[:i] + [n] + route[i:]) - base - left_out[id(n)], c.crew_id, i) for i in range(len(route) + 1)]
        return sorted(out)

    def put(routes: Routes, costs: dict, n: Need) -> None:
        """Insert at the best place, if that lowers the score."""
        best = places(routes, costs, n)
        if best and best[0][0] < 0:
            _, cid, i = best[0]
            routes.setdefault(cid, []).insert(i, n)
            costs[cid] = rcost(cid, routes[cid])

    def total(routes: Routes, costs: dict) -> float:
        routed = {id(n) for r in routes.values() for n in r}
        return sum(costs.values()) + sum(v for i, v in left_out.items() if i not in routed)

    routes = {cid: list(r) for cid, r in start.items() if cid in by_id}
    costs = {cid: rcost(cid, r) for cid, r in routes.items()}
    begin = total(routes, costs)
    routed = {id(n) for r in routes.values() for n in r}
    for n in pool:  # shortcut: one pass in urgency order, not the globally best insertion each time; upgrade if the pool stays small
        if id(n) not in routed:
            put(routes, costs, n)

    def take_out(routes: Routes, how: str, q: int) -> list[Need]:
        inside = [(cid, n) for cid, r in routes.items() for n in r]
        if how == "random":
            return [n for _, n in rng.sample(inside, q)]
        if how == "worst":  # the needs paying the most where they sit now
            paid = [(-_cost(n, t - now_h, early), i, n) for i, (cid, r) in enumerate(routes.items())
                    for n, t in _walk(by_id[cid], r, now_h, travel) if n is not None]
            return [n for _, _, n in sorted(paid, key=lambda x: (x[0], x[1], x[2].patient_id))[:q]]
        seed = rng.choice(inside)[1]  # related: one need and the ones nearest to it
        return [n for _, n in sorted(inside, key=lambda cn: math.hypot(cn[1].lat - seed.lat, cn[1].lon - seed.lon))[:q]]

    removes, repairs = ["random", "worst", "related"], ["cheapest", "regret"]
    w_remove, w_repair = [1.0] * 3, [1.0] * 2
    current, current_costs, current_total = routes, costs, total(routes, costs)
    best, best_total = {cid: list(r) for cid, r in routes.items()}, current_total
    temperature = 0.05 * current_total or 1.0
    for _ in range(a("planner.alns_iterations")):
        count = sum(len(r) for r in current.values())
        if not count:
            break
        ri, pi = rng.choices(range(3), w_remove)[0], rng.choices(range(2), w_repair)[0]
        trial, trial_costs = {cid: list(r) for cid, r in current.items()}, dict(current_costs)
        out = take_out(trial, removes[ri], min(count, max(1, round(a("planner.alns_remove_share") * count))))
        gone = {id(n) for n in out}
        for cid in [cid for cid, r in trial.items() if any(id(n) in gone for n in r)]:
            trial[cid] = [n for n in trial[cid] if id(n) not in gone]
            trial_costs[cid] = rcost(cid, trial[cid])
        if repairs[pi] == "regret":  # the need that loses most by not getting its best place goes first
            def regret(n):
                p = places(trial, trial_costs, n)
                return -(p[1][0] - p[0][0]) if len(p) > 1 else 0.0
            out = sorted(out, key=lambda n: (regret(n), n.patient_id))
        else:
            out = sorted(out, key=lambda n: (-left_out[id(n)], n.patient_id))
        for n in out:
            put(trial, trial_costs, n)
        trial_total = total(trial, trial_costs)
        if trial_total < current_total or rng.random() < math.exp((current_total - trial_total) / temperature):
            current, current_costs, current_total = trial, trial_costs, trial_total
        if trial_total < best_total - 1e-12:
            best, best_total = {cid: list(r) for cid, r in trial.items()}, trial_total
            w_remove[ri] += 1.0
            w_repair[pi] += 1.0
        temperature *= 0.95
    if best_total > begin:  # only if the first pass could not help and nothing since did
        best = {cid: list(r) for cid, r in start.items() if cid in by_id}
    return {cid: r for cid, r in best.items() if r}
