import pytest

from hearth import store
from hearth.contracts import Home, Patient
from hearth.messaging import registry

FULL = {"device": "oxygen", "device_words": "oxygen machine", "building_id": "B-SAMPLE", "address": "1200 Fixture St, Houston, TX 77002",
        "unit": "00-0310", "plan": "1BR, 1BA - 700SF (fixture)", "scan_id": "fixture-B-SAMPLE", "backup_hours": 4.0, "floor": 3}
PHONE = "+15550001111"


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("HEARTH_FIXTURES", "1")


def call(**facts):
    return {"call_id": "C-1", "kind": "register", "patient_id": None, "ctx": {"phone": PHONE}, "facts": facts, "status": "active"}


def test_nothing_is_written_until_device_address_hours_and_floor():
    assert registry.save(call(**{k: v for k, v in FULL.items() if k != "floor"})) is None and store.all("patient") == []


def test_a_full_call_writes_patient_contact_and_home():
    pid = registry.save(c := call(**FULL))
    p, h = Patient(**store.get("patient", pid)), Home(**store.get("home", pid))
    assert pid.startswith("R-") and c["patient_id"] == pid and p.synthetic and p.mobility == "bedbound" and p.floor == 3
    assert (p.building_id, p.zip, p.phone_status, p.backup_hours_on_hand) == ("B-SAMPLE", "77002", "unverified", 4.0)
    assert store.get("contact", pid)["phone"] == PHONE
    assert (h.source, h.ok_without_h, h.size, h.unit, h.scan_id, h.device_name) == ("phone", 4.0, None, "00-0310", "fixture-B-SAMPLE", "oxygen machine")
    assert h.said_at is not None


def test_saving_again_updates_the_same_records():
    c = call(**FULL)
    pid = registry.save(c)
    c["facts"]["door"] = "side door"
    assert registry.save(c) == pid and Home(**store.get("home", pid)).door == "side door" and len(store.all("patient")) == 1


def test_the_newest_registration_wins_for_a_phone():
    registry.save(call(**FULL))
    second = registry.save(call(**FULL))
    assert registry.patient_for_phone(PHONE) == second


def test_a_demo_patients_contact_is_not_a_registration():
    store.put("contact", "demo-2", {"patient_id": "demo-2", "phone": "+15550002222"})
    assert registry.patient_for_phone("+15550002222") is None


def test_reset_removes_a_phones_registrations():
    pid = registry.save(call(**FULL))
    store.put("help", pid, {"patient_id": pid})
    assert registry.reset(PHONE) == 1 and registry.patient_for_phone(PHONE) is None
    assert all(store.get(k, pid) is None for k in ("patient", "contact", "home", "help"))


def test_registrations_lists_homes_and_calls_that_need_a_person():
    pid = registry.save(call(**FULL))
    store.put("call", "C-1", call(**FULL) | {"patient_id": pid, "status": "done", "started_at": 2.0})
    store.put("call", "C-9", call(device="oxygen") | {"call_id": "C-9", "status": "handoff", "started_at": 1.0})
    store.put("call", "C-8", call() | {"call_id": "C-8", "status": "active", "started_at": __import__("time").time()})  # still talking: not listed
    out = registry.registrations()
    assert [r["patient"].patient_id for r in out["registered"]] == [pid] and out["registered"][0]["call_status"] == "done"
    assert [r["call_id"] for r in out["needs_person"]] == ["C-9"] and out["needs_person"][0]["phone"] == PHONE


def test_environment_lists(monkeypatch):
    monkeypatch.setenv("HEARTH_BUILDING_PHONES", "H-LEVEL=+15551230000, B-SAMPLE = +15551230001")
    monkeypatch.setenv("HEARTH_DEMO_CALLERS", " +15550001111 ,+15550002222")
    assert registry.building_phones() == {"H-LEVEL": "+15551230000", "B-SAMPLE": "+15551230001"}
    assert registry.demo_callers() == {"+15550001111", "+15550002222"} and registry.alert_phones() == []


def test_storm_texts_alert_phones_and_calls_registrants_in_the_area(monkeypatch):
    from hearth.messaging import photon, voice
    texts, dials = [], []
    monkeypatch.setattr(photon, "_send", lambda phone, text: texts.append((phone, text)) or "pho1")
    monkeypatch.setattr(voice, "dial", lambda call_id: dials.append(store.get("call", call_id)) or "conv1")
    monkeypatch.setenv("HEARTH_ALERT_PHONES", "+15550009999")
    monkeypatch.setenv("HEARTH_LINE_NUMBER", "(555) 010-0000")
    inside = registry.save(call(**FULL))
    outside = registry.save({"patient_id": None, "ctx": {"phone": "+15550002222"}, "facts": dict(FULL)})
    store.put("patient", outside, store.get("patient", outside) | {"zip": "99999"})
    out = registry.storm()
    assert out == {"alerted": ["+15550009999"], "dialed": [inside], "failed": []}
    assert texts == [("+15550009999", "Simulated Harris County alert: a hurricane is forecast for your area. If you or someone at home relies on "
                                      "powered medical equipment, call Hearth at (555) 010-0000 so a crew knows how to reach you. In an emergency, call 911.")]
    assert [(d["patient_id"], d["kind"], d["ctx"]["storm"]) for d in dials] == [(inside, "check", True)]


def test_storm_with_nothing_configured():
    assert registry.storm() == {"alerted": [], "dialed": [], "failed": []}


def test_a_storm_call_that_cannot_ring_is_reported(monkeypatch):
    from hearth.messaging import voice
    monkeypatch.setattr(voice, "dial", lambda call_id: None)  # no phone line set up
    pid = registry.save(call(**FULL))
    assert registry.storm()["failed"] == [f"{pid}: not dialed (the phone line is not set up)"]


def test_a_check_call_without_a_phone_in_its_context_saves_a_correction():
    pid = registry.save(call(**FULL))
    c = {"call_id": "C-2", "kind": "check", "patient_id": pid, "ctx": {"storm": True}, "facts": dict(FULL, backup_hours=2.0), "status": "active"}
    assert registry.save(c) == pid and Home(**store.get("home", pid)).ok_without_h == 2.0 and store.get("contact", pid)["phone"] == PHONE


def test_a_long_answer_is_cut_to_fit_not_lost():
    pid = registry.save(call(**FULL | {"complex_building": "the building closest to the pool, past the second gate on the left",
                                       "door": "x" * 300, "room": "y" * 200, "unit": "z" * 30}))
    h = Home(**store.get("home", pid))
    assert (len(h.complex_building), len(h.door), len(h.room), len(h.unit)) == (40, 200, 120, 20)


def test_a_registration_call_that_went_quiet_needs_a_person():
    import time
    long_ago = time.time() - 600
    store.put("call", "C-7", call(device="oxygen") | {"call_id": "C-7", "status": "active", "started_at": long_ago,
                                                      "transcript": [{"role": "caller", "text": "oxygen", "t": long_ago}]})
    store.put("call", "C-8", call() | {"call_id": "C-8", "status": "active", "started_at": time.time(), "transcript": []})
    assert [(r["call_id"], r["status"]) for r in registry.registrations()["needs_person"]] == [("C-7", "unfinished")]
