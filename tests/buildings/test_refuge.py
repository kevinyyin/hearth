from pathlib import Path

import pytest
from bhelpers import patient, profile, seed_pending_proposal

from hearth import store
from hearth.buildings import refuge
from hearth.buildings.profile import default_profile, finalize
from hearth.buildings.refuge import decide, eligible, outside_dark_area
from hearth.contracts import Sourced


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


def scan_seen(building_id="H-LEVEL", count=1):
    """A step-free 4-floor refuge whose only elevator evidence is a scan: CoStar lists none for hotels."""
    p = profile(building_id, step_free=True, floors=4)
    p.elevator_count = Sourced(value=count, source="matterport", confidence=0.5)
    return p


def test_an_elevator_only_seen_in_a_scan_needs_a_call_before_it_counts():
    who = patient(mobility="wheelchair_manual")
    ok, why = eligible(scan_seen(), who)
    assert not ok and why[0] == "needs a call"
    ok, why = eligible(scan_seen(), who, elevator_confirmed=refuge.SIMULATED_CALL)
    assert ok and any("simulated call" in w for w in why)
    ok, why = eligible(scan_seen(count=0), who, elevator_confirmed=refuge.SIMULATED_CALL)  # not seeing one in a scan proves nothing
    assert not ok and "unverified access" in why


def test_the_simulated_call_is_recorded_and_only_made_outside_the_outage_area(monkeypatch):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    who = patient(mobility="wheelchair_manual")
    ok, why = refuge.access(scan_seen(), who, {"77030"})  # H-LEVEL's own ZIP is dark: its elevator cannot be assumed
    assert not ok and why[0] == "needs a call" and store.get("refuge_call", "H-LEVEL") is None
    ok, why = refuge.access(scan_seen(), who, {"77002"})
    call = store.get("refuge_call", "H-LEVEL")
    assert ok and call["simulated"] is True and call["answer"] == "yes"
    assert store.all("call") == [] and store.all("message") == []  # no patient was called or texted


def test_a_refuge_confirmed_by_the_simulated_call_reaches_the_dispatcher_with_that_reason(monkeypatch):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    store.put("profile", "H-LEVEL", scan_seen())
    pat = patient(mobility="wheelchair_manual")
    refuge._ctx[pat.patient_id] = (pat, {"77002"})
    [opt] = refuge._options(pat, '[{"building_id": "H-LEVEL"}]')
    assert any("seen in a scan" in r for r in opt.reasons) and any("simulated call" in r for r in opt.reasons)


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


def test_a_fresh_office_answer_decides(monkeypatch):
    from hearth.buildings import status
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    status.record("H-LEVEL", "building_office", "C-B", power=True, elevator="no")
    assert refuge.confirm_elevator("H-LEVEL", {"77002"}) is None  # outside the dark area, yet the office said no
    status.record("H-LEVEL", "building_office", "C-B", power=True, elevator="yes")
    said = refuge.confirm_elevator("H-LEVEL", {"77002"})
    assert said.startswith("the building's office said so by phone at ") and ("AM" in said or "PM" in said)
    ok, why = refuge.access(scan_seen(), patient(mobility="wheelchair_manual"), {"77002"})
    assert ok and said in why and store.get("refuge_call", "H-LEVEL") is None  # no simulated call when the office answered


def test_a_stale_office_answer_falls_back_to_the_simulated_call(monkeypatch):
    import time
    from hearth.buildings import status
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    status.record("H-LEVEL", "building_office", "C-B", elevator="no")
    store.put("building_status", "H-LEVEL", store.get("building_status", "H-LEVEL") | {"t": time.time() - 7 * 3600})
    assert refuge.confirm_elevator("H-LEVEL", {"77002"}) == refuge.SIMULATED_CALL


def test_a_residents_answer_does_not_stand_in_for_the_office(monkeypatch):
    from hearth.buildings import status
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    status.record("H-LEVEL", "resident", "C-1", elevator="no")
    assert refuge.confirm_elevator("H-LEVEL", {"77002"}) == refuge.SIMULATED_CALL
