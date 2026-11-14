import math
import random

import pytest

from hearth.alns import plan_cost, reach_times, search
from hearth.planner import Crew, Flags, Need
from hearth.routing import routes


def flat(p, q):
    """One hour per unit of distance: keeps the arithmetic in the tests readable."""
    return math.hypot(p[0] - q[0], p[1] - q[1])


def need(pid, x, w=1.0, hours=0.0, kind="delivery", dest=None, service=0.0):
    return Need(pid, kind, "s1", w, hours, 0.0, float(x), service, 0.0, dest=dest)


def crew(cid, x=0.0, **over):
    return Crew(cid, "s1", 0.0, float(x), **over)


def yes(n, c):
    return True


def world(seed, crews=4, needs=14):
    rng = random.Random(seed)
    cs = [crew(f"c{i}", rng.uniform(-5, 5), free_at_h=rng.choice([0.0, 0.0, rng.uniform(0, 3)])) for i in range(crews)]
    ns = [need(f"p{i}", rng.uniform(-6, 6), w=rng.uniform(1, 5), hours=rng.uniform(-2, 8), service=0.2) for i in range(needs)]
    return cs, ns


def test_reach_times_follow_the_route_and_return_to_base_when_full():
    c = crew("c", base=(0.0, 0.0), capacity=2)
    assert reach_times(c, [need("a", 1), need("b", 2), need("c", 3)], 0.0, flat) == [1.0, 2.0, 7.0]  # 2 back, 3 out again


def test_a_busy_crew_starts_when_it_is_free():
    assert reach_times(crew("c", free_at_h=5.0), [need("a", 1)], 0.0, flat) == [6.0]


def test_a_ride_ends_at_its_drop_off_before_the_next_stop():
    ride = need("r", 1, kind="ride", dest=(0.0, 5.0))
    assert reach_times(crew("c"), [ride, need("b", 6)], 0.0, flat) == [1.0, 6.0]


def test_service_time_delays_the_next_stop():
    assert reach_times(crew("c"), [need("a", 1, service=0.5), need("b", 2)], 0.0, flat) == [1.0, 2.5]


def test_an_unrouted_need_costs_what_reaching_it_at_the_end_of_the_window_would():
    late = need("a", 1, w=2.0)  # already late: 2 an hour, plus the early term 0.1 * 2 / 0.1 an hour, over the 6 h window
    assert plan_cost({}, [late], [crew("c")], 0.0, flat) == pytest.approx(2 * 6 + 2 * 6)
    assert plan_cost({"c": [late]}, [late], [crew("c")], 0.0, flat) == pytest.approx(2 * 1 + 2 * 1, abs=1e-4)


@pytest.mark.parametrize("seed", range(20))
def test_search_never_ends_above_its_start(seed):
    cs, ns = world(seed)
    start = routes(ns, cs, {"s1": 99}, Flags(), 0.0, routing="paired", travel=flat)
    out = search(start, ns, cs, yes, 0.0, travel=flat, rng=random.Random(seed))
    assert plan_cost(out, ns, cs, 0.0, flat) <= plan_cost(start, ns, cs, 0.0, flat) + 1e-9


def test_search_is_reproducible():
    cs, ns = world(3)
    start = routes(ns, cs, {"s1": 99}, Flags(), 0.0, routing="paired", travel=flat)
    ids = lambda r: {c: [n.patient_id for n in route] for c, route in r.items()}  # noqa: E731
    assert ids(search(start, ns, cs, yes, 0.0, travel=flat, rng=random.Random(7))) == \
        ids(search(start, ns, cs, yes, 0.0, travel=flat, rng=random.Random(7)))


@pytest.mark.parametrize("seed", range(10))
def test_search_keeps_every_need_at_most_once_and_only_on_crews_that_can_take_it(seed):
    cs, ns = world(seed)
    can = lambda n, c: not (c.crew_id == "c0" and int(n.patient_id[1:]) % 2)  # noqa: E731
    start = routes(ns, cs, {"s1": 99}, Flags(), 0.0, routing="paired", travel=flat, fits=can)
    out = search(start, ns, cs, can, 0.0, travel=flat, rng=random.Random(seed))
    routed = [n.patient_id for route in out.values() for n in route]
    assert len(routed) == len(set(routed)) and set(routed) <= {n.patient_id for n in ns}
    assert all(can(n, c) for c in cs for n in out.get(c.crew_id, []))


def test_search_does_not_change_its_start():
    cs, ns = world(1)
    start = routes(ns, cs, {"s1": 99}, Flags(), 0.0, routing="paired", travel=flat)
    before = {c: list(r) for c, r in start.items()}
    search(start, ns, cs, yes, 0.0, travel=flat, rng=random.Random(1))
    assert start == before


def test_search_finds_the_obvious_chain():
    c, ns = crew("c1"), [need("a", 1), need("b", 2), need("c", 3)]
    start = routes(ns, [c], {"s1": 99}, Flags(), 0.0, routing="paired", travel=flat)
    assert sum(len(r) for r in start.values()) == 1  # the pairing gives a crew one job
    out = search(start, ns, [c], yes, 0.0, travel=flat, rng=random.Random(0))
    assert [n.patient_id for n in out["c1"]] == ["a", "b", "c"]


def test_search_untangles_a_bad_order():
    c, ns = crew("c1"), [need(p, x) for p, x in (("a", 1), ("b", 2), ("c", 3), ("d", 4))]
    out = search({"c1": [ns[3], ns[0], ns[2], ns[1]]}, ns, [c], yes, 0.0, travel=flat, rng=random.Random(0))
    assert [n.patient_id for n in out["c1"]] == ["a", "b", "c", "d"]


def test_routes_with_alns_returns_several_jobs_per_crew():
    c, ns = crew("c1"), [need("a", 1), need("b", 2), need("c", 3)]
    out = routes(ns, [c], {"s1": 99}, Flags(), 0.0, routing="alns", travel=flat, rng=random.Random(0))
    assert [n.patient_id for n in out["c1"]] == ["a", "b", "c"] and c.free_at_h == 0
