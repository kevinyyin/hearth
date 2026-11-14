import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hearth import store
from hearth.messaging import voice
from hearth.messaging.interpreter import Turn
from hearth.messaging.templates import render
from hearth.messaging.voice import confirmed_facts, respond, start_call

PATIENT = {"patient_id": "p1", "synthetic": True, "lat": 29.76, "lon": -95.37, "zip": "77002", "floor": 6, "device": "oxygen",
           "device_detail": "oxygen concentrator", "backup_hours_on_hand": 6.0, "use_rate": 1.0, "mobility": "walks_with_help",
           "can_self_relocate": False, "temp_sensitive": "heat", "risk_weight": 3, "supplier_id": "s1", "building_id": "B-SAMPLE",
           "phone_status": "verified", "profile_status": "complete", "phone": "+15550100001"}
PROPOSAL = {"proposal_id": "P1", "patient_id": "p1", "status": "approved", "reason": None, "thread_id": "t1",
            "options": [{"building_id": "B-H1", "name": "Hotel Alpha", "lat": 29.8, "lon": -95.4, "reasons": [], "sources": [], "score": 1}]}
RIDE = {"job_id": "j1", "kind": "ride", "patient_id": "p1", "org_id": "o1", "status": "created", "eta": None,
        "data": {"org_name": "Harris Mobility", "window": "4 and 5 PM"}}
vars1 = {"org": "Harris Mobility", "window": "4 and 5 PM"}
FAKE = {
    "yes": Turn(confirms=True, confidence=0.95),
    "yes okay": Turn(consents_to_move=True, confirms=True, confidence=0.95),
    "no": Turn(confirms=False, confidence=0.95),
    "about forty minutes": Turn(backup_hours=0.67, confidence=0.9),
    "maybe, I guess": Turn(confidence=0.4),
    "should I turn my oxygen down?": Turn(medical_question=True, wants_human=True, confidence=0.9),
    "it's forty minutes, sorry": Turn(backup_hours=0.67, confidence=0.9, ack="I hear you."),
    "they said forty minutes": Turn(backup_hours=0.67, confidence=0.9, ack="Help is on the way."),
}


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(voice, "interpret_turn", lambda text, keypad, ctx, history: FAKE[text])
    store.put("patient", "p1", PATIENT)
    store.put("proposal", "P1", PROPOSAL)


def call_at_ask():
    c = start_call("p1", "impact"); respond(c, "hello?"); return c


def call_at_readback(hours):
    c = call_at_ask(); respond(c, "about forty minutes"); return c


def call_with_confirmed(**facts):
    c = call_at_ask(); doc = store.get("call", c); doc["facts"].update(facts); store.put("call", c, doc); return c


def call_at_move_offer():
    c = start_call("p1", "move_consent", "P1"); respond(c, "hello?"); return c


def test_first_line_says_automated():
    c = start_call("p1", "impact"); assert "automated" in respond(c, "")


def test_hours_need_readback_before_they_count():
    c = call_at_ask(); respond(c, "about forty minutes"); assert "backup_hours" not in confirmed_facts(c)
    respond(c, "yes"); assert confirmed_facts(c)["backup_hours"] == pytest.approx(0.67, abs=0.01)


def test_denied_readback_asks_again():
    c = call_at_readback(0.67); assert "how many" in respond(c, "no").lower() and "backup_hours" not in confirmed_facts(c)


def test_vague_turn_does_not_overwrite_confirmed_fact():
    c = call_with_confirmed(can_move=False); respond(c, "maybe, I guess"); assert confirmed_facts(c)["can_move"] is False


def test_medical_question_gets_the_fixed_handoff():
    c = call_at_ask(); assert respond(c, "should I turn my oxygen down?") == render("medical_handoff")


def test_no_promise_without_an_accepted_job():
    store.put("job", "j1", RIDE)
    c = start_call("p1", "move_consent", "P1"); out = " ".join(respond(c, t) for t in ["", "yes", "yes"])
    assert render("move_confirmed_ride", **vars1) not in out


def test_ride_line_only_after_the_job_is_accepted():
    store.put("job", "j1", RIDE | {"status": "accepted"})
    c = start_call("p1", "move_consent", "P1"); out = " ".join(respond(c, t) for t in ["", "yes", "yes"])
    assert render("move_confirmed_ride", **vars1) in out


def test_three_silences_escalate():
    c = call_at_ask(); [respond(c, "") for _ in range(3)]; assert store.get("call", c)["status"] == "escalated"


def test_consent_is_recorded():
    c = call_at_move_offer(); respond(c, "yes okay"); respond(c, "yes"); assert confirmed_facts(c)["consents_to_move"] is True


def test_consent_call_needs_an_approved_proposal():
    store.put("proposal", "P2", PROPOSAL | {"proposal_id": "P2", "status": "pending"})
    for pid in ("P2", "NOPE", None):
        with pytest.raises(PermissionError):
            start_call("p1", "move_consent", pid)


def test_ack_is_spoken_only_if_the_guard_allows_it():
    assert respond(call_at_ask(), "it's forty minutes, sorry").startswith("I hear you.")
    assert "on the way" not in respond(call_at_ask(), "they said forty minutes")


def sse_text(r):
    import json
    chunks = [line[6:] for line in r.text.splitlines() if line.startswith("data: ")]
    assert chunks[-1] == "[DONE]"
    return "".join(json.loads(c)["choices"][0]["delta"].get("content", "") for c in chunks[:-1])


def client():
    app = FastAPI(); app.include_router(voice.router); return TestClient(app)


def test_endpoint_streams_the_next_line():
    c = start_call("p1", "impact")
    r = client().post("/voice/v1/chat/completions", json={
        "model": "hearth", "stream": True, "messages": [{"role": "user", "content": "hello?"}],
        "elevenlabs_extra_body": {"call_id": c}})
    assert r.status_code == 200 and "automated" in sse_text(r)


def test_inbound_from_an_unknown_number_goes_to_a_person():
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [{"role": "user", "content": "hello?"}], "elevenlabs_extra_body": {"caller_number": "+15559999999"}})
    assert sse_text(r) == render("human_handoff")


def test_inbound_from_a_known_number_starts_an_impact_call():
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [{"role": "user", "content": "hello?"}], "elevenlabs_extra_body": {"caller_number": "+15550100001"}})
    assert "automated" in sse_text(r) and [c["kind"] for c in store.all("call")] == ["impact"]


def test_demo_patient_profile_is_read_back_in_plain_words():
    c = start_call("demo-1", "impact"); line = respond(c, "hello?")
    assert "your feeding pump" in line and "about four hours" in line


def test_interpreter_sees_the_last_question_and_not_this_turn_twice(monkeypatch):
    seen = []
    monkeypatch.setattr(voice, "interpret_turn", lambda text, keypad, ctx, history: seen.append(history) or FAKE[text])
    c = call_at_ask(); respond(c, "about forty minutes")
    assert seen[-1][-1]["role"] == "agent" and "about forty minutes" not in [m["text"] for m in seen[-1]]
