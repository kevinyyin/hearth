import hashlib
import itertools
import json
import time

import numpy as np

from hearth.contracts import Event, PlanState, Snapshot
from hearth.decision import decide, with_hysteresis
from hearth.population import load_population
from hearth.sim.engine import run
from hearth.sim.policies import CODE, decide_vec, hysteresis_vec

from conftest import ctx, pat


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
