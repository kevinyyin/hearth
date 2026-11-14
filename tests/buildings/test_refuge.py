from pathlib import Path

import pytest
from bhelpers import patient, profile, seed_pending_proposal

from hearth import store
from hearth.buildings import refuge
from hearth.buildings.profile import default_profile, finalize
from hearth.buildings.refuge import decide, eligible, outside_dark_area


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(refuge, "MEMORY_FILE", str(tmp_path / "memories" / "dispatcher.md"))


def test_wheelchair_patient_needs_step_free_and_elevator():
    ok, why = eligible(profile(step_free=False, floors=4, elevators=1), patient(mobility="wheelchair_power"))
    assert not ok and why
    ok, why = eligible(profile(step_free=True, floors=4, elevators=0), patient(mobility="bedbound"))
    assert not ok and any("elevator" in w for w in why)
    ok, why = eligible(profile(step_free=True, floors=4, elevators=2), patient(mobility="wheelchair_manual"))
    assert ok and any("step-free" in w for w in why)


def test_single_floor_refuge_needs_no_elevator():
    assert eligible(profile(step_free=True, floors=1), patient(mobility="wheelchair_manual"))[0]


def test_unknown_access_is_ineligible():
    ok, why = eligible(finalize(default_profile("H", "x", 0, 0)), patient(mobility="wheelchair_manual"))
    assert not ok and "unverified access" in why


def test_walking_patient_has_no_access_constraint():
    assert eligible(finalize(default_profile("H", "x", 0, 0)), patient(mobility="walks"))[0]


def test_dark_area_check_is_by_zip_and_unknown_is_not_outside():
    assert outside_dark_area("77030", {"77002"}) and not outside_dark_area("77002", {"77002"}) and not outside_dark_area(None, set())


def test_reject_writes_memory_and_changes_nothing_else():
    seed_pending_proposal("P1")
    p = decide("P1", "reject", "no backup generator")
    assert p.status == "rejected" and p.reason == "no backup generator"
    assert "no backup generator" in Path(refuge.MEMORY_FILE).read_text() and "Fixture Hotel" in Path(refuge.MEMORY_FILE).read_text()
    assert store.get("proposal", "P1")["status"] == "rejected"
    assert store.all("call") == [] and store.all("message") == []


def test_reject_needs_a_reason():
    seed_pending_proposal("P3")
    with pytest.raises(ValueError):
        decide("P3", "reject", "")
    assert store.get("proposal", "P3")["status"] == "pending"


def test_approve_sets_approved_and_cannot_be_decided_twice():
    seed_pending_proposal("P4")
    assert decide("P4", "approve", None).status == "approved"
    with pytest.raises(ValueError):
        decide("P4", "reject", "changed my mind")


def test_pending_proposal_never_times_into_approved():
    seed_pending_proposal("P2")
    assert store.get("proposal", "P2")["status"] == "pending"


def test_option_sources_come_from_the_profile_not_the_model(monkeypatch):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    store.put("profile", "H-LEVEL", profile("H-LEVEL", step_free=True, floors=1))
    opts = refuge._options(patient(mobility="wheelchair_manual"), '[{"building_id": "H-LEVEL", "reasons": ["close"], "sources": ["guess"]}]')
    assert [o.sources for o in opts] == [["costar", "matterport"]] and opts[0].name == "Level Inn (fixture)"
    assert refuge._options(patient(mobility="wheelchair_manual"), '[{"building_id": "H-STEPS"}]') == []   # no stored profile


def test_options_recheck_dark_area_and_type_and_build_reasons_in_code(monkeypatch):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    store.put("profile", "H-LEVEL", profile("H-LEVEL", step_free=True, floors=1))
    store.put("profile", "B-SAMPLE", profile("B-SAMPLE", step_free=True, floors=1))
    pat = patient(mobility="wheelchair_manual")
    refuge._ctx[pat.patient_id] = (pat, {"77030"})                       # H-LEVEL's ZIP is dark now
    assert refuge._options(pat, '[{"building_id": "H-LEVEL"}]') == []
    refuge._ctx[pat.patient_id] = (pat, {"77002"})
    assert refuge._options(pat, '[{"building_id": "B-SAMPLE"}]') == []   # apartments are not refuges
    [opt] = refuge._options(pat, '[{"building_id": "H-LEVEL", "reasons": ["model says: lovely lobby"]}]')
    assert "power at refuge not verified" in opt.reasons and any("step-free" in r for r in opt.reasons)
    assert any(r.endswith("km away") for r in opt.reasons) and not any("lovely" in r for r in opt.reasons)


def test_rejection_memory_survives_a_fresh_server_instance():
    seed_pending_proposal("P5")
    decide("P5", "reject", "elevator out of service")
    Path(refuge.MEMORY_FILE).unlink()                     # a new instance starts with an empty temp folder
    refuge.sync_memory()
    assert "elevator out of service" in Path(refuge.MEMORY_FILE).read_text()
