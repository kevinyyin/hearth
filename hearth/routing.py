"""Central planner: every free crew and every open need looked at together, instead of each need taking its nearest crew.

Two layers. `pair` matches free crews to needs so the total value is the best possible among the candidates. With
routing="alns", `hearth.alns.search` then builds a route of several jobs per crew over the look-ahead window. Both
minimize one score: weighted hours people spend at risk waiting for a crew, with a light pull toward reaching everyone
sooner (`cost`). `planner.assign` (greedy) is untouched and stays the default everywhere.
"""
import random
from typing import Callable

from hearth.config import a
from hearth.contracts import Job
from hearth.planner import Crew, Flags, Need, travel_h

try:  # the replay has these; the hosted API does not, and the plain-Python paths below give the same answers
    import numpy as _np
    from scipy.optimize import linear_sum_assignment as _lsa

    from hearth.population import km as _km
except ImportError:
    _np = _lsa = _km = None

Point = tuple[float, float]
Travel = Callable[[Point, Point], float]  # hours between two points
Fits = Callable[[Need, Crew], bool] | None


def _cost(n: Need, wait_h: float, early: float) -> float:
    return n.weight * max(0.0, wait_h - n.hours_until_empty) + early * n.weight / max(n.hours_until_empty, 0.1) * wait_h


def cost(n: Need, reach_h: float, now_h: float) -> float:
    """What it costs to reach this person at reach_h: weighted hours past the moment they start being at risk, plus a
    small term (today's urgency key times the wait) so a need that is not late yet is still worth a crew."""
    return _cost(n, reach_h - now_h, a("planner.early_weight"))


def allowed(n: Need, c: Crew, stock: dict, flags: Flags, fits: Fits) -> bool:
    """The rule inside `planner.assign`: a delivery needs the patient's supplier (any, with mutual aid) and a unit."""
    return ((n.kind != "delivery" or ((flags.mutual_aid or c.org_id == n.supplier_id) and stock.get(c.org_id, 0) > 0))
            and (fits is None or fits(n, c)))


def job_hours(n: Need, c: Crew, travel: Travel) -> tuple[float, float]:
    """(hours until the crew reaches the person, crew-hours the whole job uses), for a crew that leaves now."""
    t = travel((c.lat, c.lon), (n.lat, n.lon))
    return t, t + n.service_h + (travel((n.lat, n.lon), n.dest) if n.dest else 0.0)


def value(n: Need, c: Crew, travel: Travel, horizon: float, early: float) -> float:
    """The drop in the score from sending this crew now rather than not at all in the window, per crew-hour spent."""
    t, hours = job_hours(n, c, travel)
    return max((_cost(n, horizon, early) - _cost(n, t, early)) / max(hours, 0.01), 0.0)


def _values(needs: list[Need], free: list[Crew], stock: dict, flags: Flags, fits: Fits, travel: Travel):
    """Rows are free crews, columns are needs; 0 where the crew may not serve the need."""
    horizon, early = a("planner.lookahead_h"), a("planner.early_weight")
    if _np is None or travel is not travel_h:
        return [[value(n, c, travel, horizon, early) if allowed(n, c, stock, flags, fits) else 0.0 for n in needs] for c in free]
    col = lambda f: _np.array([f(n) for n in needs], float)  # noqa: E731
    w, h, service = col(lambda n: n.weight), col(lambda n: n.hours_until_empty), col(lambda n: n.service_h)
    leg = col(lambda n: travel_h((n.lat, n.lon), n.dest) if n.dest else 0.0)
    t = _km(_np.array([[c.lat] for c in free]), _np.array([[c.lon] for c in free]), col(lambda n: n.lat), col(lambda n: n.lon)) \
        * a("travel.detour_factor") / a("travel.speed_kmh")
    urgency = early * w / _np.maximum(h, 0.1)
    gain = w * (_np.maximum(0.0, horizon - h) - _np.maximum(0.0, t - h)) + urgency * (horizon - t)
    v = _np.maximum(gain / _np.maximum(t + service + leg, 0.01), 0.0)
    delivery = _np.array([n.kind == "delivery" for n in needs])
    own = flags.mutual_aid or (_np.array([[c.org_id] for c in free]) == _np.array([n.supplier_id for n in needs]))
    has_unit = _np.array([[stock.get(c.org_id, 0) > 0] for c in free])
    v = _np.where(~delivery | (own & has_unit), v, 0.0)
    if fits is not None:
        for r, c in enumerate(free):
            for k, n in enumerate(needs):
                if v[r, k] > 0 and not fits(n, c):
                    v[r, k] = 0.0
    return v


def hungarian(values) -> list[tuple[int, int]]:
    """The (row, column) pairs with the largest total value, one per row and per column, in plain Python.
    Pairs worth nothing are left out."""
    rows, cols = len(values), len(values[0]) if len(values) else 0
    if not rows or not cols:
        return []
    flip = rows > cols  # the method wants no more rows than columns
    cst = [[-values[r][c] for r in range(rows)] for c in range(cols)] if flip else [[-values[r][c] for c in range(cols)] for r in range(rows)]
    n, m, inf = len(cst), len(cst[0]), float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cst[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0], j0 = p[j1], j1
    pairs = [(j - 1, p[j] - 1) if flip else (p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]
    return sorted((r, c) for r, c in pairs if values[r][c] > 0)


def solve(values) -> list[tuple[int, int]]:
    """`hungarian`, by scipy when it is installed."""
    if _lsa is None:
        return hungarian(values)
    m = _np.asarray(values, float)
    if m.size == 0:
        return []
    return [(int(r), int(c)) for r, c in zip(*_lsa(m, maximize=True)) if m[r, c] > 0]


def _pair(needs: list[Need], crews: list[Crew], stock: dict, flags: Flags, now_h: float, fits: Fits, travel: Travel) -> list[tuple[Crew, Need, float]]:
    free = [c for c in crews if c.free_at_h <= now_h]
    if not free or not needs:
        return []
    vals = _values(needs, free, stock, flags, fits, travel)
    deliveries = [k for k, n in enumerate(needs) if n.kind == "delivery"]
    while True:
        pairs = solve(vals)
        by_org: dict[str, list[tuple[float, int]]] = {}
        for r, k in pairs:
            if needs[k].kind == "delivery":
                by_org.setdefault(free[r].org_id, []).append((float(vals[r][k]), r))
        short = [r for org, got in by_org.items() for _, r in sorted(got)[: max(len(got) - stock.get(org, 0), 0)]]
        if not short:
            return [(free[r], needs[k], float(vals[r][k])) for r, k in pairs]
        for r in short:  # more deliveries than units: the least valuable crews deliver nothing this step, then solve again
            for k in deliveries:
                vals[r][k] = 0.0


def pair(needs: list[Need], crews: list[Crew], stock: dict, flags: Flags, now_h: float, *, fits: Fits = None,
         travel: Travel = travel_h) -> dict[str, Need]:
    """Free crew id -> the need it should take now. The total value is the best possible among these crews and needs."""
    return {c.crew_id: n for c, n, _ in _pair(needs, crews, stock, flags, now_h, fits, travel)}


def routes(needs: list[Need], crews: list[Crew], stock: dict, flags: Flags, now_h: float, *, routing: str, fits: Fits = None,
           travel: Travel = travel_h, rng: random.Random | None = None) -> dict[str, list[Need]]:
    """Crew id -> the needs it should serve, in order. Changes nothing: `plan` commits the first job of each."""
    start = {c.crew_id: [n] for c, n, _ in _pair(needs, crews, stock, flags, now_h, fits, travel)}
    if routing == "paired":
        return start
    if routing != "alns":
        raise ValueError(f"routing must be paired or alns, not {routing!r}")
    free = sum(c.free_at_h <= now_h for c in crews)
    if not free:
        return {}
    from hearth import alns  # here, not at the top: alns imports this module

    # speed cut: the search sees the pairing's needs and the first few per free crew (callers pass needs most urgent first)
    paired = {id(n) for r in start.values() for n in r}
    pool = [n for i, n in enumerate(needs) if i < a("planner.alns_needs_per_free_crew") * free or id(n) in paired]
    in_play = [c for c in crews if c.free_at_h < now_h + a("planner.lookahead_h")]
    return alns.search(start, pool, in_play, lambda n, c: allowed(n, c, stock, flags, fits), now_h, travel=travel,
                       rng=rng or random.Random(0))


def plan(needs: list[Need], crews: list[Crew], stock: dict, flags: Flags, now_h: float, *, routing: str, fits: Fits = None,
         travel: Travel = travel_h, rng: random.Random | None = None) -> list[Job]:
    """Accepted jobs for the crews that are free now: the first job of each crew's route. Like `planner.assign`, it
    moves the chosen crews (busy until done, at the drop-off) and takes a unit of stock per delivery."""
    by_id = {c.crew_id: c for c in crews}
    horizon, early = a("planner.lookahead_h"), a("planner.early_weight")
    firsts = [(by_id[cid], route[0]) for cid, route in routes(needs, crews, stock, flags, now_h, routing=routing, fits=fits,
                                                               travel=travel, rng=rng).items()
              if route and by_id[cid].free_at_h <= now_h]
    jobs = []
    for c, n in sorted(firsts, key=lambda cn: (-value(cn[1], cn[0], travel, horizon, early), cn[0].crew_id)):
        if n.kind == "delivery":
            if stock.get(c.org_id, 0) <= 0:
                continue  # shortcut: a crew whose unit went to a more valuable delivery waits one step, upgrade if stock ever runs short in the sweep
            stock[c.org_id] -= 1
        done = now_h + job_hours(n, c, travel)[1]
        c.free_at_h, (c.lat, c.lon) = done, (n.dest or (n.lat, n.lon))
        jobs.append(Job(job_id=f"{n.kind}-{n.patient_id}-{now_h:g}", kind=n.kind, patient_id=n.patient_id, org_id=c.org_id,
                        status="accepted", data={"crew_id": c.crew_id, "done_h": done, **({"dest": list(n.dest)} if n.dest else {})}))
    return jobs
