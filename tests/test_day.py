"""The simulation page's 24-hour day, planned by the central planner (hearth/sim/day.py)."""
import json

import pytest

from hearth.config import ROOT
from hearth.sim.day import run_day, weighted_wait

# written by web/lib/simDayFixture.test.ts: the page's stand-in households, its constants, and its own greedy's result
FX = json.loads((ROOT / "tests/fixtures/sim_day.json").read_text())
K = FX["constants"]


@pytest.fixture(scope="module")
def side():
    return run_day(FX["households"], K)


def test_the_planner_day_waits_no_longer_than_the_pages_greedy(side):
    assert weighted_wait(side, K["runHours"]) <= FX["greedy"]["weightedWait"]


def test_the_day_has_the_shape_the_page_draws(side):
    vans = len(K["stations"]) * K["crewsPerStation"]
    assert set(side) == {"jobs", "calls", "legs", "station", "tours", "stops", "refills", "events"} and side["calls"] == []
    assert len(side["legs"]) == vans == len(side["station"])
    assert side["station"] == [c % len(K["stations"]) for c in range(vans)]
    for legs in side["legs"]:  # a van is in one place at a time, and every leg has the page's five fields
        assert all(set(leg) == {"from", "to", "t0", "t1", "departure"} for leg in legs)
        assert all(a["t1"] <= b["t0"] + 1e-9 for a, b in zip(legs, legs[1:]))
    for j in side["jobs"]:
        assert set(j) == {"h", "dueAt", "knownAt", "sentAt", "servedAt", "refill"} and j["knownAt"] == j["dueAt"]
        assert j["servedAt"] is None or j["dueAt"] <= j["sentAt"] <= j["servedAt"]
    assert all(e.get("stops", 1) <= K["capacity"] for e in side["events"] if e["kind"] == "dispatch")
    assert [e["t"] for e in side["events"]] == sorted(e["t"] for e in side["events"])
    assert {e["kind"] for e in side["events"]} == {"call", "dispatch", "arrive", "restock"}


def test_the_counters_match_the_jobs_and_the_legs(side):
    served = [j for j in side["jobs"] if j["servedAt"] is not None]
    assert side["stops"] == len(served) and side["refills"] == sum(j["refill"] for j in served)
    assert side["tours"] == sum(leg["departure"] for legs in side["legs"] for leg in legs)
    assert side["tours"] == sum(e["kind"] == "dispatch" for e in side["events"])


def test_every_round_starts_and_ends_at_the_vans_station(side):
    for c, legs in enumerate(side["legs"]):
        base = K["stations"][side["station"][c]]["at"]
        for i, leg in enumerate(legs):
            if leg["departure"]:
                assert leg["from"] == base
                assert i == 0 or legs[i - 1]["to"] == base


def test_the_event_lines_read_as_the_pages_do(side):
    text = {e["kind"]: e["text"] for e in side["events"]}
    assert text["call"].startswith("Called household ") and text["call"].endswith(" — on the registry, device down")
    assert text["arrive"].startswith("Crew ") and " helped household " in text["arrive"]
    assert " restocked household " in text["restock"]
    assert any(e["text"].endswith(" — 1 stop, then back") or e["text"].endswith(" stops chained")
               for e in side["events"] if e["kind"] == "dispatch")


def test_the_day_is_reproducible(side):
    assert run_day(FX["households"], K) == side


def test_a_repeat_household_needs_a_restock_after_refill_hours():
    one = run_day([{"lon": -95.37, "lat": 29.76, "needsAt": 0, "repeats": True}], K)
    first, second = one["jobs"][0], one["jobs"][1]
    assert not first["refill"] and second["refill"]
    assert second["dueAt"] == pytest.approx(first["servedAt"] + K["refillH"])


def test_a_household_that_does_not_repeat_is_visited_once():
    one = run_day([{"lon": -95.37, "lat": 29.76, "needsAt": 2.0, "repeats": False}], K)
    assert len(one["jobs"]) == 1 and one["jobs"][0]["sentAt"] == 2.0 and one["stops"] == 1


def test_an_empty_day_is_an_empty_side():
    none = run_day([], K)
    assert none["jobs"] == [] and none["events"] == [] and none["tours"] == 0 and len(none["legs"]) == 15
