"""Texts by Photon iMessage, and Photon's signed webhook.

A text renders a template key `allowed` for the patient's plan state and job status, so no text promises help that no
crew has accepted. It goes only to a phone a person entered (a "contact" doc), never to a synthetic record's phone.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from hearth import store
from hearth.contracts import PlanState
from hearth.messaging.templates import allowed, render
from hearth.messaging.voice import confirmed_facts, phone_of

router = APIRouter()
API = "https://api.photon.codes/v1/projects/"


def send_text(patient_id: str, key: str, **vars) -> str:
    """Sends one templated text and stores a "message" doc (status sent or failed). Returns the message id."""
    state, job_status = _plan(patient_id)
    if not allowed(key, state, job_status):
        raise PermissionError(f"{key} is not allowed for {patient_id} ({state}, job {job_status})")
    if not (phone := phone_of(patient_id)):
        raise LookupError(f"no phone a person entered for {patient_id}")
    msg_id = f"M-{uuid.uuid4().hex[:8]}"
    doc = {"message_id": msg_id, "patient_id": patient_id, "key": key, "body": render(key, **vars), "status": "failed", "t": time.time()}
    try:
        doc["photon_id"] = _send(phone, doc["body"])
        doc["status"] = "sent"
    except Exception as e:
        doc["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        store.put("message", msg_id, doc)
    return msg_id


def after_call(call_id: str) -> str | None:
    """The follow-up text: only what the caller confirmed. Nothing when nothing was confirmed or no person entered a phone."""
    call = store.get("call", call_id)
    if not call.get("patient_id"):  # a registration that ended before anyone was registered
        return None
    said = _facts_text(confirmed_facts(call_id), call["ctx"])
    if not (said and phone_of(call["patient_id"])):
        return None
    return send_text(call["patient_id"], "call_summary", facts=said)


def _facts_text(facts: dict, ctx: dict) -> str:
    parts = []
    if (h := facts.get("backup_hours")) is not None:
        amount = f"{h:g} hour{'' if h == 1 else 's'}" if h >= 1 else f"{round(h * 60)} minutes"
        parts.append(f"{amount} of {ctx.get('supply') or 'backup'}")
    if address := facts.get("address"):
        parts.append(f"your address {address}")
    if (floor := facts.get("floor")) is not None:
        parts.append(f"floor {floor}")
    if (hot := facts.get("home_too_hot_or_cold")) is not None:
        parts.append(f"your home is {'' if hot else 'not '}too hot or too cold")
    if (move := facts.get("consents_to_move")) is not None:
        parts.append(f"you agree to move to {ctx['place']}" if move else "you do not want to move")
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + (parts[-1] if parts else "")


def _plan(patient_id: str) -> tuple[PlanState, str]:
    jobs = [j for j in store.all("job") if j["patient_id"] == patient_id]
    if jobs:
        state = {"ride": PlanState.MOVE, "delivery": PlanState.RESUPPLY}.get(jobs[-1]["kind"], PlanState.OWN_BACKUP)
        return state, jobs[-1]["status"]
    moving = any(p["patient_id"] == patient_id and p["status"] == "approved" for p in store.all("proposal"))
    return (PlanState.MOVE if moving else PlanState.OWN_BACKUP), "none"


def _photon(method: str, path: str, body: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {os.environ['PHOTON_PROJECT_API_KEY']}"}
    if method == "POST":
        h["Idempotency-Key"] = uuid.uuid4().hex
    r = httpx.request(method, API + os.environ["PHOTON_PROJECT_ID"] + path, headers=h, json=body, timeout=20)
    if r.is_error:
        raise RuntimeError(f"Photon {method} {path} answered {r.status_code}: {r.text[:300]}")
    return r.json()


def _line(phone: str) -> str | None:
    found = _photon("GET", "/platforms/imessage/assignments")["assignments"]
    return next((a["assignedPhoneNumber"] for a in found if a["handle"] == phone and not a.get("releasedAt")), None)


def _send(phone: str, text: str) -> str:
    """From the project's shared iMessage line. Photon delivers only to a phone with an assignment that has texted the
    line since it was made (`python -m hearth.messaging.photon contact` makes it)."""
    if not (line := _line(phone)):
        raise LookupError(f"{phone} has no iMessage assignment on the shared line")
    agent, peer = (_photon("POST", "/users", {"platform": "imessage", "handle": x})["id"] for x in (line, phone))
    space = _photon("POST", "/spaces", {"platform": "imessage", "participantIds": [agent, peer]})["id"]
    content = {"type": "text", "format": "plain", "text": text}
    return _photon("POST", "/messages", {"senderId": agent, "spaceId": space, "content": content})["id"]


def _verified(headers, body: bytes) -> bool:
    """Standard Webhooks: base64 HMAC-SHA256 of "id.timestamp.body", within five minutes."""
    secret = os.environ.get("PHOTON_WEBHOOK_SECRET", "")
    msg_id, ts, sigs = (headers.get(k, "") for k in ("webhook-id", "webhook-timestamp", "webhook-signature"))
    if not (secret.startswith("whsec_") and msg_id and ts.isdigit()) or abs(time.time() - int(ts)) > 300:
        return False
    key = base64.b64decode(secret.removeprefix("whsec_"))
    want = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(s[3:], want) for s in sigs.split() if s.startswith("v1,"))


@router.post("/photon/webhook")
async def webhook(request: Request) -> Response:
    """Photon events (calls, messages received and delivered), kept as "photon_event" docs for review."""
    body = await request.body()
    if not _verified(request.headers, body):
        raise HTTPException(401, "bad or missing webhook signature")
    event = json.loads(body)
    store.put("photon_event", request.headers["webhook-id"], {"type": event.get("type"), "data": event.get("data"), "t": time.time()})
    return Response(status_code=204)


if __name__ == "__main__":
    # a person enters a test phone for a synthetic patient: the consent call and the follow-up text go to it
    if sys.argv[1:2] != ["contact"] or len(sys.argv) != 4 or not re.fullmatch(r"\+[1-9]\d{7,14}", sys.argv[3]):
        sys.exit("usage: python -m hearth.messaging.photon contact <patient_id> <+E.164 phone>")
    pid, phone = sys.argv[2:]
    store.put("contact", pid, {"patient_id": pid, "phone": phone})
    line = _line(phone) or _photon("POST", "/platforms/imessage/assignments", {"handle": phone})["assignedPhoneNumber"]
    print(f"{pid} now rings and texts {phone}. Text {line} once from that phone so the iMessage line can reply.")
