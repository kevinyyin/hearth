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
    "I can't breathe, should I turn it up?": Turn(needs_help_now=True, medical_question=True, confidence=0.9),
    "my oxygen stopped, I can't breathe": Turn(needs_help_now=True, wants_human=True, confidence=0.9),
    "thanks, bye": Turn(confidence=0.9),
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


def test_medical_question_gets_the_fixed_handoff_then_the_question_again():
    c = call_at_readback(0.67); out = respond(c, "should I turn my oxygen down?")
    assert out.startswith(render("medical_handoff")) and out.endswith("Is that right?") and "backup_hours" not in confirmed_facts(c)


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


def test_a_request_without_a_call_id_goes_to_a_person():
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [{"role": "user", "content": "hello?"}], "elevenlabs_extra_body": {"caller_number": "+15559999999"}})
    assert sse_text(r) == render("human_handoff")


def test_a_caller_number_from_the_request_never_attaches_to_a_call():
    c = call_at_move_offer()
    for turn in ("hello?", "yes", "yes"):
        r = client().post("/voice/v1/chat/completions", json={
            "stream": True, "messages": [{"role": "user", "content": turn}], "elevenlabs_extra_body": {"caller_number": PATIENT["phone"]}})
        assert sse_text(r) == render("human_handoff")
    assert "consents_to_move" not in confirmed_facts(c) and [d["call_id"] for d in store.all("call")] == [c]


def test_demo_patient_profile_is_read_back_in_plain_words():
    c = start_call("demo-1", "impact"); line = respond(c, "hello?")
    assert "your feeding pump" in line and "about four hours" in line


def test_interpreter_sees_the_last_question_and_not_this_turn_twice(monkeypatch):
    seen = []
    monkeypatch.setattr(voice, "interpret_turn", lambda text, keypad, ctx, history: seen.append(history) or FAKE[text])
    c = call_at_ask(); respond(c, "about forty minutes")
    assert seen[-1][-1]["role"] == "agent" and "about forty minutes" not in [m["text"] for m in seen[-1]]


def test_elevenlabs_silence_marker_counts_as_silence():
    c = call_at_ask()
    assert "Is that about right?" in respond(c, "...")  # first silence: ask again
    respond(c, " … "); respond(c, "...")
    assert store.get("call", c)["status"] == "escalated"


def test_keypad_yes_on_a_call_never_records_the_caller_as_safe(monkeypatch):
    from hearth.messaging import interpreter
    monkeypatch.setattr(voice, "interpret_turn", interpreter.interpret_turn)  # real keypad path, no model needed
    c = call_at_move_offer(); respond(c, "1"); respond(c, "1")
    assert confirmed_facts(c) == {"consents_to_move": True}


@pytest.mark.parametrize("answer", ["yes", "1"])
def test_yes_to_the_impact_question_confirms_the_profile_hours(monkeypatch, answer):
    from hearth.messaging import interpreter
    monkeypatch.setattr(voice, "interpret_turn", interpreter.interpret_turn)  # yes and keypad are read by code
    c = call_at_ask(); assert respond(c, answer) == render("ask_temperature") and confirmed_facts(c)["backup_hours"] == 6.0


@pytest.mark.parametrize("answer", ["no", "3"])
def test_no_to_the_impact_question_asks_for_hours(monkeypatch, answer):
    from hearth.messaging import interpreter
    monkeypatch.setattr(voice, "interpret_turn", interpreter.interpret_turn)
    c = call_at_ask(); assert respond(c, answer) == render("ask_hours") and "backup_hours" not in confirmed_facts(c)


def test_an_urgent_medical_turn_escalates():
    c = call_at_ask(); out = respond(c, "I can't breathe, should I turn it up?")
    assert out.startswith(render("medical_handoff")) and store.get("call", c)["status"] == "escalated"


def test_a_bare_number_after_ask_hours_is_hours_not_a_keypad_choice():
    c = call_at_ask(); respond(c, "no")  # -> ask_hours
    assert "three hours" in respond(c, "3") and store.get("call", c)["step"] == "readback"


def test_a_closed_call_says_nothing_to_silence_but_still_hears_an_emergency():
    c = call_at_move_offer(); respond(c, "yes"); respond(c, "yes")  # consent recorded, call done
    assert respond(c, "...") == ""
    respond(c, "my oxygen stopped, I can't breathe"); assert store.get("call", c)["status"] == "escalated"


def test_an_urgent_first_turn_escalates():
    c = start_call("p1", "impact"); respond(c, "my oxygen stopped, I can't breathe")
    assert store.get("call", c)["status"] == "escalated"


def test_an_internal_error_hands_off_instead_of_failing(monkeypatch):
    c = call_at_ask()
    monkeypatch.setattr(voice, "interpret_turn", lambda *a: (_ for _ in ()).throw(RuntimeError("bug")))
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [{"role": "user", "content": "about forty minutes"}], "elevenlabs_extra_body": {"call_id": c}})
    assert sse_text(r) == render("human_handoff") and store.get("call", c)["status"] == "handoff"


def test_short_distress_at_the_opening_escalates(monkeypatch):
    FAKE["help me"] = Turn(needs_help_now=True, wants_human=True, confidence=0.9)
    c = start_call("p1", "impact")
    out = respond(c, "help me")
    assert store.get("call", c)["status"] == "escalated" and render("human_handoff") in out


def test_dialysis_patient_hears_about_their_next_treatment_not_backup():
    store.put("patient", "p2", PATIENT | {"patient_id": "p2", "device": "home_dialysis", "backup_hours_on_hand": 30.0})
    c = start_call("p2", "impact")
    first = respond(c, "")
    assert "next home dialysis treatment" in first and "backup should last" not in first


def system(caller, conversation="conv-1"):
    return {"role": "system", "content": f"Every reply comes from the Hearth custom model endpoint. caller={caller} conversation={conversation}"}


def test_an_inbound_call_from_a_number_a_person_entered_gets_one_impact_check():
    store.put("contact", "p1", {"patient_id": "p1", "phone": "+15550100002"})
    lines = [sse_text(client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [system("+15550100002"), {"role": "user", "content": turn}]})) for turn in ("hello?", "yes")]
    calls = store.all("call")
    assert "automated" in lines[0] and lines[1] == render("ask_temperature")
    assert [(c["patient_id"], c["kind"]) for c in calls] == [("p1", "impact")]


def test_an_inbound_call_from_any_other_number_goes_to_a_person():
    r = client().post("/voice/v1/chat/completions", json={  # PATIENT["phone"] is a synthetic record, not a number a person entered
        "stream": True, "messages": [system(PATIENT["phone"]), {"role": "user", "content": "hello?"}]})
    assert sse_text(r) == render("human_handoff") and store.all("call") == []


def test_dial_rings_only_a_phone_a_person_entered(monkeypatch):
    import httpx
    posts = []
    for k, v in {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_AGENT_ID": "agent1", "ELEVENLABS_PHONE_NUMBER_ID": "line1"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(voice.httpx, "post", lambda url, **kw: posts.append(kw["json"]) or httpx.Response(
        200, json={"success": True, "conversation_id": "conv9"}, request=httpx.Request("POST", url)))
    c = start_call("p1", "move_consent", "P1")
    assert voice.dial(c) is None and posts == []  # PATIENT["phone"] is synthetic: never dialed
    store.put("contact", "p1", {"patient_id": "p1", "phone": "+15550100002"})
    assert voice.dial(c) == "conv9"
    assert posts[0]["to_number"] == "+15550100002" and posts[0]["conversation_initiation_client_data"]["custom_llm_extra_body"] == {"call_id": c}


def test_the_follow_up_text_goes_after_the_closing_line(monkeypatch):
    from hearth.messaging import photon
    sent = []
    monkeypatch.setattr(photon, "after_call", sent.append)
    c = call_at_move_offer(); respond(c, "yes")  # -> consent read-back
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "messages": [{"role": "user", "content": "yes"}], "elevenlabs_extra_body": {"call_id": c}})
    assert render("close_no_promise") in sse_text(r) and sent == [c]


END_CALL = [{"type": "function", "function": {"name": "end_call", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}}}}]


def chunks(r):
    import json
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: {")]


def test_a_handed_off_call_says_so_honestly_then_hangs_up():
    c = call_at_ask()
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "tools": END_CALL, "messages": [{"role": "user", "content": "maybe, I guess"}], "elevenlabs_extra_body": {"call_id": c}})
    said, calls = sse_text(r), [t for ch in chunks(r) for t in ch["choices"][0]["delta"].get("tool_calls", [])]
    assert said == render("human_handoff") and "connecting" not in said and "911" in said
    assert [t["function"]["name"] for t in calls] == ["end_call"] and chunks(r)[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_an_active_call_and_a_browser_without_end_call_stay_up():
    c = call_at_ask()
    for tools, turn in ((END_CALL, "about forty minutes"), ([], "maybe, I guess")):
        r = client().post("/voice/v1/chat/completions", json={
            "stream": True, "tools": tools, "messages": [{"role": "user", "content": turn}], "elevenlabs_extra_body": {"call_id": c}})
        assert not any(ch["choices"][0]["delta"].get("tool_calls") for ch in chunks(r))


def test_an_unknown_inbound_caller_is_told_and_the_call_ends():
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "tools": END_CALL, "messages": [system("+15550109999"), {"role": "user", "content": "hello?"}]})
    assert sse_text(r) == render("human_handoff") and chunks(r)[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_a_line_the_plan_does_not_allow_hands_the_call_to_a_person(monkeypatch):
    from hearth.messaging import scripts
    c = call_at_ask()
    monkeypatch.setattr(scripts, "advance", lambda call, t: [("delivery_confirmed", {"org": "x", "item": "y", "window": "z"})])
    assert respond(c, "yes") == render("human_handoff") and store.get("call", c)["status"] == "handoff"


def test_a_finished_call_hangs_up_after_the_closing_line(monkeypatch):
    from hearth.messaging import photon
    monkeypatch.setattr(photon, "after_call", lambda call_id: None)
    c = call_at_move_offer(); respond(c, "yes")  # -> consent read-back
    r = client().post("/voice/v1/chat/completions", json={
        "stream": True, "tools": END_CALL, "messages": [{"role": "user", "content": "yes"}], "elevenlabs_extra_body": {"call_id": c}})
    assert sse_text(r).endswith(render("close_no_promise")) and chunks(r)[-1]["choices"][0]["finish_reason"] == "tool_calls"
    assert store.get("call", c)["status"] == "done"  # nothing after the closing line can re-flag it
