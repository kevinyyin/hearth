import hashlib
import itertools
import json
import time

import numpy as np
import pytest

from hearth.contracts import Event, PlanState, Snapshot
from hearth.decision import decide, with_hysteresis
from hearth.population import load_population
from hearth.sim.engine import run
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
            "assumptions_sha256"} <= s.keys()
    assert s["assumptions_sha256"] == hashlib.sha256(ASSUMPTIONS.read_bytes()).hexdigest()
    assert s["moves"] == (d / "events.jsonl").read_text().count('"type": "moved"') > 0


def test_sweep_rows_take_median_and_percentiles():
    from hearth.metrics import sweep_rows
    runs = [{"policy": "p3", "crews": 5, "risk_hours_weighted": float(w), "risk_hours_unweighted": float(w) / 2} for w in range(1, 12)]
    assert sweep_rows(runs) == [{"policy": "p3", "crews": 5, "median": 6.0, "p5": 1.5, "p95": 10.5, "unweighted_median": 3.0}]


def test_sweep_writes_one_row_per_policy_and_crew_count(tmp_path):
    from hearth.sim.sweep import sweep
    rows = sweep("sample", [5, 10], 2, out_root=tmp_path)
    assert len(rows) == 10 and json.loads((tmp_path / "sweep_sample.json").read_text()) == rows
    assert {r["policy"] for r in rows} == {"p0", "p3", "p3__nobld", "p3__nomove", "p3__aid"}


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
