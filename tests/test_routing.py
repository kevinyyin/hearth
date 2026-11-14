import random

import pytest

from hearth.planner import Crew, Flags, Need, assign
from hearth.routing import cost, hungarian, pair, plan, routes, solve


def need(pid, w=3.0, hours=10.0, supplier="s1", kind="delivery", lat=29.76, lon=-95.37):
    return Need(patient_id=pid, kind=kind, supplier_id=supplier, weight=w, hours_until_empty=hours, lat=lat, lon=lon,
                service_h=0.2, since_h=0.0)


def crew(cid, org="s1", lat=29.80, lon=-95.40):
    return Crew(crew_id=cid, org_id=org, lat=lat, lon=lon)


def stock(n):
    return {"s1": n, "s2": n, "s3": n}


def at(x):
    """A point x hundredths of a degree north of the usual one: about 1.1 km a step."""
    return 29.76 + x * 0.01


def test_cost_is_weighted_lateness_plus_a_pull_toward_sooner():
    n = need("a", w=3, hours=2)  # deadline at now + 2
    assert cost(n, 1.0, 0.0) == pytest.approx(0.1 * (3 / 2) * 1.0)  # early term only
    assert cost(n, 5.0, 0.0) == pytest.approx(3 * 3.0 + 0.1 * (3 / 2) * 5.0)  # 3 h late


def test_pairing_beats_nearest_first():
    def world():
        return ([need("urgent", w=5, hours=0, lat=at(4.9)), need("other", w=3, hours=0, lat=at(-1))],
                [crew("A", lat=at(0), lon=-95.37), crew("B", lat=at(10), lon=-95.37)])
    needs, crews = world()
    greedy = {j.data["crew_id"]: j.patient_id for j in assign(needs, crews, stock(9), Flags(), 0)}
    assert greedy == {"A": "urgent", "B": "other"}  # the urgent need takes its nearest crew; the other gets a long drive
    needs, crews = world()
    paired = {c: n.patient_id for c, n in pair(needs, crews, stock(9), Flags(), 0).items()}
    assert paired == {"A": "other", "B": "urgent"}  # B is almost as near the urgent need, and A is next door to the other


def test_a_need_due_after_the_window_still_gets_a_free_crew():
    assert len(plan([need("far", hours=28)], [crew("c1")], stock(1), Flags(), 0, routing="paired")) == 1


def test_nothing_to_plan_returns_nothing():
    assert plan([], [crew("c1")], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a")], [], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a", supplier="s1")], [crew("c2", org="s2")], stock(1), Flags(), 0, routing="paired") == []
    assert plan([need("a")], [crew("c1")], stock(0), Flags(), 0, routing="paired") == []
    assert plan([need("a")], [crew("c1")], stock(1), Flags(), 0, routing="paired", fits=lambda n, c: False) == []


def test_a_busy_crew_is_not_paired():
    busy = crew("c1")
    busy.free_at_h = 3.0
    assert plan([need("a")], [busy], stock(1), Flags(), 0, routing="paired") == []


@pytest.mark.parametrize("rows,cols", [(2, 5), (5, 2), (4, 4), (1, 1)])
def test_the_two_solvers_agree_on_uneven_sides(rows, cols):
    rng = random.Random(rows * 10 + cols)
    for _ in range(30):
        v = [[rng.choice([0.0, rng.random()]) for _ in range(cols)] for _ in range(rows)]
        total = lambda pairs: sum(v[r][c] for r, c in pairs)  # noqa: E731
        assert total(solve(v)) == pytest.approx(total(hungarian(v)))
        for pairs in (solve(v), hungarian(v)):
            assert all(v[r][c] > 0 for r, c in pairs)
            assert len({r for r, _ in pairs}) == len(pairs) == len({c for _, c in pairs})


def test_the_plain_solver_finds_the_best_total_not_the_best_first_pick():
    assert sorted(hungarian([[10.0, 9.0], [9.0, 1.0]])) == [(0, 1), (1, 0)]  # 18 beats 10 + 1


def test_a_job_that_takes_no_time_does_not_divide_by_zero():
    n = Need("a", "ride", "", 2.0, 1.0, 29.80, -95.40, 0.0, 0.0, dest=(29.80, -95.40))  # the crew stands on it
    assert len(plan([n], [crew("c1")], {}, Flags(), 0, routing="paired")) == 1


def test_stock_caps_deliveries_and_keeps_the_most_valuable():
    jobs = plan([need("low", w=1), need("high", w=5)], [crew("c1"), crew("c2")], stock(1), Flags(), 0, routing="paired")
    assert [j.patient_id for j in jobs] == ["high"]


def test_mutual_aid_lets_another_suppliers_crew_deliver():
    args = ([need("a", supplier="s1")], [crew("c2", org="s2")], stock(1))
    assert plan(*args, Flags(mutual_aid=True), 0, routing="paired")[0].org_id == "s2"


def test_plan_commits_like_assign():
    c, s = crew("c1"), stock(3)
    job = plan([need("a")], [c], s, Flags(), 0, routing="paired")[0]
    assert job.status == "accepted" and job.kind == "delivery" and job.data["crew_id"] == "c1"
    assert job.data["done_h"] == c.free_at_h > 0
    assert s["s1"] == 2 and (c.lat, c.lon) == (29.76, -95.37)


def test_a_ride_ends_at_its_drop_off():
    c = crew("c1")
    n = Need("a", "ride", "", 2.0, 1.0, 29.76, -95.37, 0.2, 0.0, dest=(29.70, -95.30))
    job = plan([n], [c], {}, Flags(), 0, routing="paired")[0]
    assert job.data["dest"] == [29.70, -95.30] and (c.lat, c.lon) == (29.70, -95.30)


def test_routes_mutates_nothing():
    c, s = crew("c1"), stock(3)
    assert [n.patient_id for n in routes([need("a")], [c], s, Flags(), 0, routing="paired")["c1"]] == ["a"]
    assert c.free_at_h == 0 and s["s1"] == 3
