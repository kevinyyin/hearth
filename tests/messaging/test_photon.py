import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hearth import store
from hearth.messaging import photon
from hearth.messaging.voice import start_call

SECRET = "whsec_" + base64.b64encode(b"hearth-test-signing-key-32-bytes").decode()


@pytest.fixture(autouse=True)
def sent(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    store.put("patient", "p1", {"patient_id": "p1", "device": "oxygen", "backup_hours_on_hand": 6.0, "phone": "+15550100001"})
    store.put("contact", "p1", {"patient_id": "p1", "phone": "+15550100002"})
    out = []
    monkeypatch.setattr(photon, "_send", lambda phone, text: out.append((phone, text)) or "pho_msg_test")
    return out


def call_with(facts, patient_id="p1", **extra):
    c = start_call(patient_id, "impact"); doc = store.get("call", c); doc["facts"].update(facts); doc.update(extra)
    store.put("call", c, doc); return c


def test_text_refuses_a_promise_without_an_accepted_job(sent):
    with pytest.raises(PermissionError):
        photon.send_text("p1", "delivery_confirmed", org="Harris Supply", item="oxygen", window="2 to 4 PM")
    assert sent == [] and store.all("message") == []


def test_a_delivery_text_goes_once_the_delivery_is_accepted(sent):
    store.put("job", "j1", {"job_id": "j1", "kind": "delivery", "patient_id": "p1", "org_id": "o1", "status": "accepted", "eta": None, "data": {}})
    photon.send_text("p1", "delivery_confirmed", org="Harris Supply", item="oxygen", window="2 to 4 PM")
    msg = store.all("message")[-1]
    assert sent[0][0] == "+15550100002" and msg["status"] == "sent" and "accepted your delivery" in msg["body"]


def test_after_call_text_uses_only_confirmed_facts(sent):
    c = call_with({"backup_hours": 3.0, "home_too_hot_or_cold": False}, pending=5.0)  # 5 was never read back
    photon.after_call(c)
    body = store.all("message")[-1]["body"]
    assert "3 hours of backup" in body and "not too hot or too cold" in body and "5" not in body and "coming" not in body


def test_no_text_without_a_confirmed_fact_or_a_phone_a_person_entered(sent):
    store.put("patient", "p2", {"patient_id": "p2", "device": "oxygen", "phone": "+15550100003"})  # a synthetic record's phone
    photon.after_call(call_with({}))
    photon.after_call(call_with({"backup_hours": 3.0}, patient_id="p2"))
    assert sent == []


def signed(body: bytes, secret=SECRET, ts=None, msg_id="msg_1"):
    ts = str(int(ts or time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"webhook-id": msg_id, "webhook-timestamp": ts, "webhook-signature": f"v1,{sig}", "content-type": "application/json"}


def test_webhook_keeps_signed_events_and_refuses_the_rest(monkeypatch):
    monkeypatch.setenv("PHOTON_WEBHOOK_SECRET", SECRET)
    app = FastAPI(); app.include_router(photon.router); c = TestClient(app)
    body = json.dumps({"type": "message.received", "data": {"id": "pho_msg_1"}}).encode()
    other = "whsec_" + base64.b64encode(b"someone-else-signing-key-32-byte").decode()
    assert c.post("/photon/webhook", content=body, headers=signed(body, secret=other)).status_code == 401
    assert c.post("/photon/webhook", content=body, headers=signed(body, ts=time.time() - 600)).status_code == 401  # replayed late
    assert c.post("/photon/webhook", content=body + b" ", headers=signed(body)).status_code == 401  # changed on the way
    assert store.get("photon_event", "msg_1") is None
    assert c.post("/photon/webhook", content=body, headers=signed(body)).status_code == 204
    assert store.get("photon_event", "msg_1")["type"] == "message.received"
    monkeypatch.delenv("PHOTON_WEBHOOK_SECRET")
    assert c.post("/photon/webhook", content=body, headers=signed(body)).status_code == 401  # no secret: nothing is trusted


def test_the_follow_up_lists_a_confirmed_address_and_floor():
    from hearth.messaging.photon import _facts_text
    said = _facts_text({"backup_hours": 4.0, "address": "1200 Fixture St, Houston, TX 77002", "floor": 3}, {})
    assert said == "4 hours of backup, your address 1200 Fixture St, Houston, TX 77002 and floor 3"


def help_world(monkeypatch):
    """The help loop's fixture world (tests/test_dispatch.py), with p4 reachable by text."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[1] / "buildings"))
    from bhelpers import profile
    from hearth import dispatch
    from hearth.config import ROOT
    from hearth.contracts import Patient
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    for r in json.loads((ROOT / "data/demo/patients.json").read_text()):
        store.put("patient", r["patient_id"], Patient(**r))
    store.put("profile", "H-STEPS", profile("H-STEPS", floors=3))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps({"order": [{"patient_id": r["patient_id"], "reason": "x"} for r in rows]}))
    store.put("contact", "p4", {"patient_id": "p4", "phone": "+15550100004"})
    dispatch.save_crew("A", "B-NOSCAN", "car", [], True)
    return dispatch


def test_each_tracker_line_is_texted_once(sent, monkeypatch):
    dispatch = help_world(monkeypatch)
    dispatch.open_request("p4")
    assert [t for p, t in sent if p == "+15550100004"] == ["Hearth: Request received", "Hearth: A crew has been asked"]
    dispatch.expire()
    dispatch.save_crew("A", "B-NOSCAN", "car", [], True)  # a change elsewhere: nothing new for p4
    assert len([1 for p, _ in sent if p == "+15550100004"]) == 2
    dispatch.crew_action("A", "accept")
    new = [t for p, t in sent if p == "+15550100004"][2:]
    assert len(new) == 1 and "has accepted your ride" in new[0] and " between " in new[0]


def test_no_crew_or_time_is_texted_before_accept(sent, monkeypatch):
    dispatch = help_world(monkeypatch)
    dispatch.open_request("p4")
    assert not any("accepted" in t or "arrive" in t for _, t in sent)


def test_no_phone_sends_nothing(sent, monkeypatch):
    dispatch = help_world(monkeypatch)
    assert dispatch.open_request("p2").state in ("waiting", "offered") and sent == []


def test_a_failed_text_does_not_stop_the_help_loop(sent, monkeypatch):
    dispatch = help_world(monkeypatch)
    monkeypatch.setattr(photon, "_send", lambda phone, text: (_ for _ in ()).throw(LookupError("no iMessage assignment")))
    dispatch.open_request("p4")
    assert dispatch.crew_action("A", "accept").state == "accepted"
    assert {m["status"] for m in store.all("message") if m["key"] == "tracker"} == {"failed"}


def test_old_requests_are_not_texted_when_someone_else_asks(sent, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from hearth.contracts import HelpRequest
    dispatch = help_world(monkeypatch)
    then = datetime.now(timezone.utc) - timedelta(hours=8)
    store.put("help", "p4", HelpRequest(patient_id="p4", state="accepted", times={"waiting": then, "offered": then, "accepted": then}))
    dispatch.open_request("p2")  # a rehearsal leftover must not start texting a teammate's phone
    assert [t for p, t in sent if p == "+15550100004"] == []
