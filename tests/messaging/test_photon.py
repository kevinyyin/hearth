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
