import hashlib
import itertools
import json
import time

import numpy as np
import pytest

from hearth.contracts import Event, PlanState, Snapshot
from hearth.decision import decide, with_hysteresis
from hearth.population import load_population
from hearth.planner import Flags
from hearth.sim.engine import policy_label, run
from hearth.sim.policies import CODE, decide_vec, hysteresis_vec

from conftest import ctx, pat


@pytest.fixture(autouse=True)
def _empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "hearth.db"))


def digest(d):
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + p.read_bytes())
    return h.hexdigest()


def test_same_seed_same_bytes(tmp_path):
    run("sample", "p3", 1, 5, out_root=tmp_path / "a"); run("sample", "p3", 1, 5, out_root=tmp_path / "b")
    assert digest(tmp_path / "a") == digest(tmp_path / "b")


def test_outputs_validate_against_contracts(tmp_path):
    run("sample", "p3", 1, 5, out_root=tmp_path); d = next(tmp_path.iterdir())
    Snapshot.model_validate_json((d / "snapshots/0.json").read_text()); assert (d / "assumptions.yaml").exists()
    for line in (d / "events.jsonl").read_text().splitlines(): Event.model_validate_json(line)
    meta = json.loads((d / "meta.json").read_text())
    assert meta["synthetic"] and len(meta["ticks"]) == len(list((d / "snapshots").iterdir()))


def test_vectorized_decide_matches_decide():
    devices, sens = ["oxygen", "home_dialysis"], ["none", "heat"]
    for dev, s, backup, hu, tu, dl, mv, am in itertools.product(devices, sens, [0.0, 23.0, 30.0], *[[False, True]] * 5):
        want = decide(pat(device=dev, temp_sensitive=s), backup, ctx(12, hu, tu, dl, mv, am))
        got = decide_vec(np.array([dev]), np.array([s]), np.array([backup]), 12.0, np.array([hu]), np.array([tu]),
                         np.array([dl]), np.array([mv]), am)
        assert got[0] == CODE[want]


def test_vectorized_hysteresis_matches():
    for prev, prop, streak in itertools.product(list(PlanState), list(PlanState), [0, 1]):
        want = with_hysteresis(prev, prop, streak)
        s, k = hysteresis_vec(np.array([CODE[prev]]), np.array([CODE[prop]]), np.array([streak]))
        assert (s[0], k[0]) == (CODE[want[0]], want[1])


def test_p0_moves_nobody(tmp_path):
    run("sample", "p0", 1, 5, out_root=tmp_path); d = next(tmp_path.iterdir())
    assert not [l for l in (d / "events.jsonl").read_text().splitlines() if '"type": "moved"' in l]


def test_silence_is_never_safe(tmp_path):
    """Under p3 a dark patient Hearth cannot reach is UNREACHABLE until a crew checks, never OWN_BACKUP."""
    run("sample", "p3", 1, 5, out_root=tmp_path); d = next(tmp_path.iterdir())
    unverified = {p.patient_id for p in load_population("sample", 1) if p.phone_status != "verified"}
    first = {}
    for e in map(json.loads, (d / "events.jsonl").read_text().splitlines()):
        if e["type"] == "state_change" and e["patient_id"] in unverified:
            first.setdefault(e["patient_id"], e["data"]["to"])
    assert first and set(first.values()) == {"UNREACHABLE"}


def test_full_county_run_is_fast_enough(tmp_path):
    t = time.time(); run("beryl_2024", "p3", 1, 20, out_root=tmp_path); assert time.time() - t < 180


def test_summary_has_published_keys(tmp_path):
    from hearth.config import ASSUMPTIONS
    s = run("sample", "p3", 1, 5, out_root=tmp_path); d = next(tmp_path.iterdir())
    assert {"risk_hours_weighted", "risk_hours_unweighted", "device_hours", "temp_hours", "moves", "patients_reaching_zero",
            "patients", "assumptions_sha256"} <= s.keys()
    assert 0 <= s["patients_reaching_zero"] <= s["patients"] == 200  # the sample scenario's patients
    assert s["assumptions_sha256"] == hashlib.sha256(ASSUMPTIONS.read_bytes()).hexdigest()
    assert s["moves"] == (d / "events.jsonl").read_text().count('"type": "moved"') > 0


def test_sweep_rows_take_median_and_percentiles():
    from hearth.metrics import sweep_rows
    runs = [{"policy": "p3", "crews": 5, "risk_hours_weighted": float(w), "risk_hours_unweighted": float(w) / 2,
             "patients_reaching_zero": w * 10, "patients": 647} for w in range(1, 12)]
    assert sweep_rows(runs) == [{"policy": "p3", "crews": 5, "median": 6.0, "p5": 1.5, "p95": 10.5, "unweighted_median": 3.0,
                                 "ran_out_median": 60.0, "patients": 647}]


def test_sweep_writes_one_row_per_policy_and_crew_count(tmp_path):
    from hearth.sim.sweep import sweep
    rows = sweep("sample", [5, 10], 2, out_root=tmp_path)
    assert len(rows) == 14 and json.loads((tmp_path / "sweep_sample.json").read_text()) == rows
    assert [r["policy"] for r in rows[::2]] == ["p0", "p3", "p3__nobld", "p3__nomove", "p3__aid", "p3__paired", "p3__alns"]


def test_routing_changes_the_label_and_leaves_greedy_alone():
    assert policy_label("p3", Flags()) == "p3"
    assert policy_label("p3", Flags(routing="alns")) == "p3__alns"
    assert policy_label("p3", Flags(use_buildings=False, routing="paired")) == "p3__nobld__paired"


@pytest.mark.parametrize("routing", ["paired", "alns"])
def test_a_routed_run_is_reproducible_and_valid(routing):
    s1 = run("sample", "p3", 1, 5, Flags(routing=routing), out_root=None)
    s2 = run("sample", "p3", 1, 5, Flags(routing=routing), out_root=None)
    assert s1 == s2 and s1["run_id"] == f"sample__p3__{routing}__c5__s1"


def test_a_routed_run_sends_crews(tmp_path):
    run("sample", "p3", 1, 5, Flags(routing="alns"), out_root=tmp_path)
    events = [json.loads(line) for line in (tmp_path / "sample__p3__alns__c5__s1" / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "job_created" for e in events) and any(e["type"] == "job_completed" for e in events)


def test_documented_case_replay_is_labeled_and_moves_once_the_home_turns_hot(tmp_path):
    run("case_jarrett", "p3", 1, 20, out_root=tmp_path); d = next(tmp_path.iterdir())
    meta = json.loads((d / "meta.json").read_text())
    assert meta["patients"] == 1 and "replay of a documented case; outcome under Hearth is simulated" in meta["label"]
    evs = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines()]
    states = [e["data"]["to"] for e in evs if e["type"] == "state_change"]
    # charged device, hot home: once the home is forecast unsafe she is never left on her own backup
    assert "MOVE" in states and "OWN_BACKUP" not in states[states.index("MOVE"):]
    assert any(e["type"] == "moved" and e["t"] < "2024-07-11" for e in evs)


def test_reasons_shown_to_the_dispatcher_are_true(tmp_path):
    run("sample", "p0", 1, 5, out_root=tmp_path); d = next(tmp_path.iterdir())
    whys = {json.loads(l)["data"]["why"] for l in (d / "events.jsonl").read_text().splitlines() if '"state_change"' in l}
    assert not [w for w in whys if "queued" in w]  # under p0 nobody is queued until a call fails
    meta = json.loads((d / "meta.json").read_text())
    assert meta["profiles_used"] == [] and json.loads((d / "summary.json").read_text())["profiles_used"] == 0


def test_p0_never_sends_a_delivery_to_home_dialysis(tmp_path):
    run("sample", "p0", 1, 20, out_root=tmp_path); d = next(tmp_path.iterdir())
    dialysis = {p.patient_id for p in load_population("sample", 1) if p.device == "home_dialysis"}
    deliveries = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if '"kind": "delivery"' in l]
    assert dialysis and deliveries and not [e for e in deliveries if e["patient_id"] in dialysis]


def test_nobody_is_moved_into_their_own_dark_building(tmp_path, monkeypatch):
    from hearth import store
    from hearth.buildings.profile import default_profile
    from hearth.contracts import Sourced
    from hearth.scenario import load
    sc = {**load("sample"), "use_profiles": True}
    monkeypatch.setattr("hearth.population.load", lambda name: sc)
    monkeypatch.setattr("hearth.sim.engine.load", lambda name: sc)
    for bid, kind, lat in [("2001", "senior_housing", 29.752), ("2002", "multifamily", 29.745), ("3001", "hotel", 29.758)]:
        prof = default_profile(bid, "test", lat, -95.362)
        store.put("profile", bid, prof.model_copy(update={"property_type": Sourced(value=kind, source="costar", confidence=0.9)}))
    run("sample", "p3", 1, 20, out_root=tmp_path); d = next(tmp_path.iterdir())
    home = {p.patient_id: (p.lat, p.lon) for p in load_population("sample", 1) if p.building_id}
    rides = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if '"kind": "ride"' in l and "job_created" in l]
    assert home and rides and not [r for r in rides if r["patient_id"] in home and tuple(r["data"]["dest"]) == home[r["patient_id"]]]


def test_delivery_is_feasible_only_for_patients_a_unit_is_left_for():
    from hearth.sim.policies import allot_deliveries
    wants = np.array([True] * 5 + [False])
    priority = np.array([1.0, 5.0, 3.0, 4.0, 2.0, 9.0])
    supplier = np.array(["s1", "s1", "s1", "s2", "s2", "s1"])
    holding = np.array([True, False, False, False, False, False])          # patient 0's delivery is already on the way
    got = allot_deliveries(wants, priority, supplier, {"s1": 1, "s2": 1}, pooled=False, holding=holding)
    assert got.tolist() == [True, True, False, True, False, False]        # s1's one unit to the higher priority; s2's likewise
    pooled = allot_deliveries(wants, priority, supplier, {"s1": 1, "s2": 1}, pooled=True, holding=holding)
    assert pooled.tolist() == [True, True, False, True, False, False]     # two pooled units, top two priorities
    assert not allot_deliveries(wants, priority, supplier, {"s1": 0, "s2": 0}, pooled=True, holding=holding)[1:].any()


def test_a_moved_patient_is_no_longer_safe_once_their_refuge_goes_dark():
    from hearth.sim.engine import refuge_open
    moved = np.array([True, True, True, False])
    dest = np.array([0, 1, -1, 1])                    # -1: moved somewhere always open (hospital or shelter)
    dest_dark_now = np.array([False, True])
    assert refuge_open(moved, dest, dest_dark_now).tolist() == [True, False, True, False]


@pytest.mark.parametrize("routing", ["paired", "alns"])
def test_a_routed_crew_does_one_job_at_a_time_and_a_patient_has_one_job_at_a_time(tmp_path, routing):
    run("sample", "p3", 1, 5, Flags(routing=routing), out_root=tmp_path)
    events = [json.loads(line) for line in (tmp_path / f"sample__p3__{routing}__c5__s1" / "events.jsonl").read_text().splitlines()]
    created = [e for e in events if e["type"] == "job_created"]
    assert created
    busy_until, open_jobs = {}, set()
    for e in events:
        if e["type"] == "job_created":
            crew = e["data"]["crew_id"]
            assert busy_until.get(crew, "") <= e["t"], f"{crew} was sent again before it was done"
            assert e["patient_id"] not in open_jobs
            busy_until[crew] = e["data"]["eta"]
            open_jobs.add(e["patient_id"])
        elif e["type"] == "job_completed":
            open_jobs.discard(e["patient_id"])


def test_the_phone_tree_is_never_labelled_with_a_routing_it_does_not_use():
    assert policy_label("p0", Flags(routing="paired")) == "p0"
