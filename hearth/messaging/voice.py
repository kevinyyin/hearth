"""Voice calls: call records, silence and hand-off rules, the ElevenLabs custom-model endpoint, and agent setup.

Each caller turn goes to the interpreter (Claude Haiku, structured fields); scripts.py picks template keys; this module
renders only keys `allowed` for the patient's plan state and job status. A model never writes a promise.
"""
import json
import os
import sys
import time
import uuid
from typing import Literal

import httpx
from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import StreamingResponse

from hearth import store
from hearth.config import ROOT, a
from hearth.contracts import PlanState
from hearth.messaging import guard, scripts
from hearth.messaging.interpreter import interpret_turn
from hearth.messaging.templates import allowed, render

router = APIRouter()
DEMO_PATIENTS = ROOT / "data" / "demo" / "patients.json"


def start_call(patient_id: str, kind: Literal["impact", "move_consent"], proposal_id: str | None = None) -> str:
    """Stores a "call" doc and returns its id. A consent call needs a dispatcher-approved proposal for this patient."""
    proposal = store.get("proposal", proposal_id) if proposal_id else None
    if kind == "move_consent" and not (proposal and proposal["status"] == "approved" and proposal["patient_id"] == patient_id):
        raise PermissionError(f"no approved proposal {proposal_id!r} for patient {patient_id}")
    p = _patient(patient_id)
    ctx = {"county": a("voice.county"), "device": p.get("device", "medical device").replace("_", " "),
           "hours": p.get("backup_hours_on_hand"), "supply": "backup",
           "place": proposal["options"][0]["name"] if proposal else None}
    call_id = f"C-{uuid.uuid4().hex[:8]}"
    store.put("call", call_id, {"call_id": call_id, "patient_id": patient_id, "kind": kind, "proposal_id": proposal_id,
                                "status": "active", "step": "open", "last": None, "silences": 0, "ctx": ctx,
                                "facts": {}, "transcript": [], "events": [], "started_at": time.time()})
    return call_id


def respond(call_id: str, caller_text: str, keypad: str | None = None) -> str:
    """The agent's next line. Updates the call doc."""
    call = store.get("call", call_id)
    if call is None:
        raise KeyError(call_id)
    text = caller_text.strip()
    if text or keypad:
        call["transcript"].append({"role": "caller", "text": text or f"[keypad {keypad}]", "t": time.time()})
    state = PlanState.MOVE if call["kind"] == "move_consent" else PlanState.OWN_BACKUP
    job = _latest_ride(call["patient_id"]) if call["kind"] == "move_consent" else None
    job_status = job["status"] if job else "none"
    call["ctx"]["ride"] = ({"org": job["data"].get("org_name", job["org_id"]), "window": job["data"]["window"]}
                           if job_status == "accepted" and "window" in job["data"] else None)
    ack, lines = _turn(call, text, keypad)
    said = [render(k, **v) if allowed(k, state, job_status) else render("human_handoff") for k, v in lines]
    out = " ".join(([ack] if ack else []) + said)
    call["transcript"].append({"role": "agent", "text": out, "t": time.time()})
    store.put("call", call_id, call)
    return out


def confirmed_facts(call_id: str) -> dict:
    """Only values the caller confirmed (numbers after a read-back)."""
    return dict(store.get("call", call_id)["facts"])


def _turn(call: dict, text: str, keypad: str | None) -> tuple[str | None, scripts.Lines]:
    if call["status"] != "active":
        return None, [("close_no_promise" if call["status"] == "done" else "human_handoff", {})]
    if call["step"] == "open":
        return None, _script(call, scripts.opening(call))
    if not text and not keypad:  # silence is never safe
        call["silences"] += 1
        if call["silences"] >= a("voice.silences_to_escalate"):
            _end(call, "escalated", "escalation", f"no answer for {call['silences']} turns")
            return None, [("human_handoff", {})]
        return None, [tuple(call["last"])]  # ask the last question again
    call["silences"] = 0
    history = [{"role": m["role"], "text": m["text"]} for m in call["transcript"][:-1]]  # [-1] is this turn
    t = interpret_turn(text, keypad, call["ctx"], history)
    call["transcript"][-1]["read"] = t.model_dump(exclude_defaults=True)  # what the interpreter heard, for review
    if t.medical_question:
        call["events"].append({"type": "medical_question", "text": text, "t": time.time()})
        return None, [("medical_handoff", {})]
    if t.needs_help_now:
        _end(call, "escalated", "escalation", "caller needs help now")
        return None, [("human_handoff", {})]
    if t.wants_human or t.confidence < a("voice.min_confidence"):
        _end(call, "handoff", "handoff", "caller asked for a person, or the turn was unclear")
        return None, [("human_handoff", {})]
    return (t.ack if t.ack and guard.allows(t.ack) else None), _script(call, scripts.advance(call, t))


def _script(call: dict, lines: scripts.Lines) -> scripts.Lines:
    call["last"] = list(lines[-1])
    return lines


def _end(call: dict, status: str, event: str, why: str) -> None:
    call["status"] = status
    call["events"].append({"type": event, "text": why, "t": time.time()})


def _patient(patient_id: str) -> dict:
    """A stored Patient, else the demo file the API serves; missing fields fall back to generic words and ask_hours."""
    # shortcut: does not read the simulation parquet; store.put("patient", ...) any non-demo patient before calling
    demo = json.loads(DEMO_PATIENTS.read_text()) if DEMO_PATIENTS.exists() else []
    return store.get("patient", patient_id) or next((p for p in demo if p["patient_id"] == patient_id), {})


def _latest_ride(patient_id: str) -> dict | None:
    rides = [j for j in store.all("job") if j["patient_id"] == patient_id and j["kind"] == "ride"]
    return rides[-1] if rides else None


def _inbound(number: str | None) -> str | None:
    """An inbound call continues the caller's active call, or starts an impact call for the patient with that phone."""
    patient = next((p for p in store.all("patient") if number and p.get("phone") == number), None)
    if patient is None:
        return None
    pid = patient["patient_id"]
    active = [c for c in store.all("call") if c["patient_id"] == pid and c["status"] == "active"]
    return active[-1]["call_id"] if active else start_call(pid, "impact")


@router.post("/voice/v1/chat/completions")
def chat_completions(body: dict = Body(...), authorization: str | None = Header(None)) -> StreamingResponse:
    """OpenAI-compatible streaming endpoint that ElevenLabs calls as its model."""
    secret = os.environ.get("HEARTH_VOICE_SECRET")
    if secret and authorization != f"Bearer {secret}":
        raise HTTPException(401)
    extra = body.get("elevenlabs_extra_body") or {}
    msgs = body.get("messages") or []
    last = msgs[-1] if msgs else {}
    content = last.get("content") or ""
    text = (content if isinstance(content, str) else " ".join(p.get("text", "") for p in content)).strip() \
        if last.get("role") == "user" else ""  # no new caller message: a silent turn
    call_id = extra.get("call_id") or _inbound(extra.get("caller_number"))
    if call_id and store.get("call", call_id):
        line = respond(call_id, text)  # keypad digits arrive as a bare user turn; the interpreter reads them
    else:
        line = render("human_handoff")
    return StreamingResponse(_sse(line, body.get("model", "hearth-voice")), media_type="text/event-stream")


def _sse(line: str, model: str):
    base = {"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    yield "data: " + json.dumps(base | {"choices": [{"index": 0, "delta": {"role": "assistant", "content": line}, "finish_reason": None}]}) + "\n\n"
    yield "data: " + json.dumps(base | {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
    yield "data: [DONE]\n\n"


def setup(public_url: str) -> str:
    """Creates (or, with ELEVENLABS_AGENT_ID set, updates) the ElevenLabs agent whose model is this server."""
    api, h = "https://api.elevenlabs.io/v1/convai", {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    custom = {"url": public_url.rstrip("/") + "/voice/v1", "model_id": "hearth-voice"}
    if secret := os.environ.get("HEARTH_VOICE_SECRET"):
        r = httpx.post(f"{api}/secrets", headers=h, json={"type": "new", "name": "hearth-voice-secret", "value": secret})
        r.raise_for_status()
        custom["api_key"] = {"secret_id": r.json()["secret_id"]}
    config = {
        "name": "Hearth voice line (simulated patients)",
        "conversation_config": {
            "agent": {"first_message": "", "language": "en", "prompt": {
                "prompt": "Every reply comes from the Hearth custom model endpoint.", "llm": "custom-llm", "custom_llm": custom}},
            "turn": {"turn_timeout": a("voice.turn_timeout_s"), "turn_eagerness": "patient"},
            "conversation": {"dtmf_input_settings": {"dtmf_input_timeout": 2, "hash_terminator": True}},
        },
        "platform_settings": {"overrides": {"custom_llm_extra_body": True}},
    }
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
    r = (httpx.patch(f"{api}/agents/{agent_id}", headers=h, json=config, timeout=30) if agent_id
         else httpx.post(f"{api}/agents/create", headers=h, json=config, timeout=30))
    if r.is_error:
        sys.exit(f"ElevenLabs refused the agent config ({r.status_code}): {r.text[:500]}")
    return agent_id or r.json()["agent_id"]


if __name__ == "__main__":
    if sys.argv[1:2] != ["setup"] or len(sys.argv) != 3:
        sys.exit("usage: python -m hearth.messaging.voice setup <public https url of the API>")
    print("ELEVENLABS_AGENT_ID=" + setup(sys.argv[2]))
