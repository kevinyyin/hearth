"""The replay builds the pairing's values with numpy; the hosted API builds them in plain Python. Same answer."""
import random

import pytest

from hearth import routing
from hearth.planner import Crew, Flags, Need


def world(seed):
    rng = random.Random(seed)
    spot = lambda: (29.76 + rng.uniform(-0.3, 0.3), -95.37 + rng.uniform(-0.3, 0.3))  # noqa: E731
    needs = [Need(f"p{i}", rng.choice(["delivery", "ride", "welfare_check"]), rng.choice(["s1", "s2"]), rng.uniform(1, 5),
                  rng.uniform(-3, 20), *spot(), rng.uniform(0.1, 0.5), 0.0) for i in range(12)]
    for n in needs:
        if n.kind == "ride":
            n.dest = spot()
    return needs, [Crew(f"c{i}", rng.choice(["s1", "s2"]), *spot()) for i in range(5)]


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("flags", [Flags(), Flags(mutual_aid=True)])
def test_fast_and_plain_value_paths_agree(seed, flags, monkeypatch):
    needs, crews = world(seed)
    stock, fits = {"s1": 3, "s2": 0}, lambda n, c: (n.patient_id, c.crew_id) != ("p0", "c0")
    assert routing._np is not None
    fast = routing._values(needs, crews, stock, flags, fits, routing.travel_h)
    paired = routing.pair(needs, crews, stock, flags, 0.0, fits=fits)
    monkeypatch.setattr(routing, "_np", None)
    monkeypatch.setattr(routing, "_lsa", None)
    plain = routing._values(needs, crews, stock, flags, fits, routing.travel_h)
    assert [[pytest.approx(v, rel=1e-9, abs=1e-12) for v in row] for row in plain] == [list(row) for row in fast]
    assert {c: n.patient_id for c, n in routing.pair(needs, crews, stock, flags, 0.0, fits=fits).items()} == \
        {c: n.patient_id for c, n in paired.items()}
