"""Voice calls: call records, silence and hand-off rules, the ElevenLabs custom-model endpoint, and agent setup.

Each caller turn goes to the interpreter (Claude Haiku, structured fields); scripts.py picks template keys; this module
renders only keys `allowed` for the patient's plan state and job status. A model never writes a promise.
"""
import json
import logging
import os
import re
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
from hearth.buildings import tools
from hearth.messaging import guard, register, registry, scripts
from hearth.messaging.interpreter import Turn, interpret_turn
from hearth.messaging.templates import allowed, render

router = APIRouter()
log = logging.getLogger(__name__)
DEMO_PATIENTS = ROOT / "data" / "demo" / "patients.json"
# answering the phone, not answering a question: skips the model on the first turn. Anything else is interpreted,
# so a short "help me" at the opening still escalates
# a bare number answers the question just asked ("3" hours, floor "1"), not the keypad menu ("1" yes, "3" it's different)
BARE_NUMBER = {"ask_hours": "backup_hours", "reg_ask_hours": "backup_hours", "ask_floor": "floor", "ask_floor_building": "floor",
               "ask_unit": "unit", "ask_building": "building"}
BARE_TEXT = {"ask_unit", "ask_building"}  # their answer is a name, kept as said
BACKUP_STEPS = {
    "impact": {"ask", "readback"},
    "register": {"hours", "hours_readback"},
    "check": {"check_hours", "hours", "hours_readback"},
    "menu": {"check_hours", "hours", "hours_readback"},
}
GREETINGS = {"hello", "hi", "hey", "yes", "yeah", "speaking", "this is she", "this is he", "who is this", "who's this"}


Kind = Literal["impact", "move_consent", "register", "check", "menu", "building_check"]


def start_call(patient_id: str | None, kind: Kind, proposal_id: str | None = None, phone: str | None = None,
               building_id: str | None = None, storm: bool = False) -> str:
    """Stores a "call" doc and returns its id. A consent call needs a dispatcher-approved proposal for this patient. A
    registration has no patient yet, only the caller's phone; a building call has a building, never a patient."""
    proposal = store.get("proposal", proposal_id) if proposal_id else None
    if kind == "move_consent" and not (proposal and proposal["status"] == "approved" and proposal["patient_id"] == patient_id):
        raise PermissionError(f"no approved proposal {proposal_id!r} for patient {patient_id}")
    ctx = {"county": a("voice.county"), "storm": storm}
    if phone:
        ctx["phone"] = phone
    if kind == "building_check":
        rec = tools.costar_record(building_id) or {}
        ctx |= {"building_id": building_id, "name": rec.get("name") or "the building", "address": ", ".join(rec.get("address", "").split(", ")[:2]),
                "one_story": rec.get("floors") == 1}
    elif patient_id:
        p = _patient(patient_id)
        dialysis = p.get("device") == "home_dialysis"  # its hours are the time until the next treatment, not device backup
        ctx |= {"device": p.get("device", "medical device").replace("_", " "), "dialysis": dialysis,
                "hours": p.get("backup_hours_on_hand"), "supply": "time before your next treatment" if dialysis else "backup",
                "place": proposal["options"][0]["name"] if proposal else None}
    call_id = f"C-{uuid.uuid4().hex[:8]}"
    store.put("call", call_id, {"call_id": call_id, "patient_id": patient_id, "kind": kind, "proposal_id": proposal_id,
                                "status": "active", "step": "open", "last": None, "silences": 0, "ctx": ctx,
                                "facts": {}, "transcript": [], "events": [], "started_at": time.time()})
    return call_id


def respond(call_id: str, caller_text: str, keypad: str | None = None, defer: bool = False) -> str:
    """The agent's next line. Updates the call doc. Help work the turn left (opening a request asks a model and sends
    texts) runs here, unless `defer`: the voice endpoint runs it after the caller has the line."""
    call = store.get("call", call_id)
    if call is None:
        raise KeyError(call_id)
    text = caller_text.strip() if re.search(r"\w", caller_text) else ""  # ElevenLabs sends "..." for a silent turn
    if text or keypad:
        call["transcript"].append({"role": "caller", "text": text or f"[keypad {keypad}]", "t": time.time()})
    state = PlanState.MOVE if call["kind"] == "move_consent" else PlanState.OWN_BACKUP
    job = _latest_ride(call["patient_id"]) if call["kind"] == "move_consent" else None
    job_status = job["status"] if job else "none"
    call["ctx"]["ride"] = ({"org": job["data"].get("org_name", job["org_id"]), "window": job["data"]["window"]}
                           if job_status == "accepted" and "window" in job["data"] else None)
    ack, lines = _turn(call, text, keypad)
    if refused := [k for k, _ in lines if not allowed(k, state, job_status)]:
        _end(call, "handoff", "handoff", f"line not allowed for this plan: {refused}")  # so the hand-off line is true
    said = [render(k, **v) if allowed(k, state, job_status) else render("human_handoff") for k, v in lines]
    out = " ".join(([ack] if ack else []) + said)
    call["transcript"].append({"role": "agent", "text": out, "t": time.time()})
    store.put("call", call_id, call)
    if not defer:
        run_help(call_id)
    return out


def run_help(call_id: str) -> None:
    """The help work a turn left: taken off the call doc first, so a turn arriving meanwhile cannot run it twice."""
    call = store.get("call", call_id)
    if action := register.take_help(call):
        store.put("call", call_id, call)
        register.do_help(call["patient_id"], action)


def confirmed_facts(call_id: str) -> dict:
    """Only values the caller confirmed (numbers after a read-back)."""
    return dict(store.get("call", call_id)["facts"])


def _turn(call: dict, text: str, keypad: str | None) -> tuple[str | None, scripts.Lines]:
    active = call["status"] == "active"
    if not text and not keypad:  # silence is never safe
        if not active:
            return None, []  # the call is over: say nothing back to silence
        if call["step"] == "open":
            return None, _script(call, scripts.opening(call))
        call["silences"] += 1
        if call["silences"] >= a("voice.silences_to_escalate"):
            _end(call, "escalated", "escalation", f"no answer for {call['silences']} turns")
            return None, [("human_handoff", {})]
        return None, [tuple(call["last"])]  # ask the last question again
    call["silences"] = 0
    if active and call["step"] == "open" and " ".join(re.sub(r"[^a-z' ]", " ", text.lower()).split()) in GREETINGS:
        return None, _script(call, scripts.opening(call))
    if not keypad and active and call["last"] and call["last"][0] in BARE_NUMBER and text.isdigit() and len(text) <= 3:
        t = Turn(**{BARE_NUMBER[call["last"][0]]: text if call["last"][0] in BARE_TEXT else int(text)})
    else:
        history = [{"role": m["role"], "text": m["text"]} for m in call["transcript"][:-1]]  # [-1] is this turn
        t = interpret_turn(text, keypad, call["ctx"], history)
    call["transcript"][-1]["read"] = t.model_dump(exclude_defaults=True)  # what the interpreter heard, for review
    if t.needs_help_now:
        _end(call, "escalated", "escalation", "caller needs help now")  # a person sees the call, as before
        if call["patient_id"] and call["kind"] != "building_check":  # and the request goes into the help queue at once
            return None, ([("medical_handoff", {})] if t.medical_question else []) + register.help_now(call)
        return None, [("medical_handoff" if t.medical_question else "human_handoff", {})]
    if t.medical_question:
        call["events"].append({"type": "medical_question", "text": text, "t": time.time()})
        if not active:
            return None, [("medical_handoff", {})]
        # then ask the pending question again, so a "yes" to the hand-off line is not read as an answer
        again = scripts.opening(call) if call["step"] == "open" else [tuple(call["last"])]
        return None, [("medical_handoff", {})] + _script(call, again)
    if t.wants_human:
        _end(call, "handoff", "handoff", "caller asked for a person, or the turn was unclear")
        return None, [("human_handoff", {})]
    if not active:
        return None, [("close_no_promise" if call["status"] == "done" else "human_handoff", {})]
    if call["step"] == "open":
        return None, _script(call, scripts.opening(call))
    step = call["step"]
    lines = scripts.advance(call, t)
    backup_steps = BACKUP_STEPS.get(call["kind"], ())
    if call["status"] == "active" and step in backup_steps:
        if call["step"] not in backup_steps:
            call.pop("backup_retries", None)
        elif (step, call["step"]) not in {("ask", "readback"), ("hours", "hours_readback")}:
            # One clarification is allowed. Corrections also spend the retry so repeated
            # changes to a pending value cannot keep the call in read-back indefinitely.
            if call.get("backup_retries", 0):
                call.pop("pending", None)
                _end(call, "handoff", "handoff", "backup duration unresolved")
                return None, _script(call, [("human_handoff", {})])
            call["backup_retries"] = 1
    return (t.ack if t.ack and guard.allows(t.ack) else None), _script(call, lines)


def _script(call: dict, lines: scripts.Lines) -> scripts.Lines:
    call["last"] = list(lines[-1])
    return lines


def _end(call: dict, status: str, event: str, why: str) -> None:
    if call["status"] != "escalated":  # never downgrade an escalation
        call["status"] = status
    call["events"].append({"type": event, "text": why, "t": time.time()})


def _patient(patient_id: str) -> dict:
    """A stored Patient, else the demo file the API serves; missing fields fall back to generic words and ask_hours."""
    # shortcut: does not read the simulation parquet; store.put("patient", ...) any non-demo patient before calling
    demo = json.loads(DEMO_PATIENTS.read_text()) if DEMO_PATIENTS.exists() else []
    return store.get("patient", patient_id) or next((p for p in demo if p["patient_id"] == patient_id), {})


def phone_of(patient_id: str) -> str | None:
    """Only a phone a person entered (a "contact" doc); a synthetic patient's phone field is never dialed or texted."""
    return (store.get("contact", patient_id) or {}).get("phone")


def dial(call_id: str) -> str | None:
    """Rings the call's number from the Photon line through ElevenLabs; returns its conversation id. None when there is
    no number a person entered (or listed, for a building) or the line is not set up: the browser phone takes the call then."""
    call = store.get("call", call_id)
    if call["kind"] == "building_check":
        phone = registry.building_phones().get(call["ctx"]["building_id"])  # never a number from the CoStar kit (all fake)
    elif call["kind"] in ("register", "menu"):
        phone = call["ctx"].get("phone")
    else:
        phone = phone_of(call["patient_id"])
    line = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    if not (phone and line):
        return None
    r = httpx.post("https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                   json={"agent_id": os.environ["ELEVENLABS_AGENT_ID"], "agent_phone_number_id": line, "to_number": phone,
                         "conversation_initiation_client_data": {"custom_llm_extra_body": {"call_id": call_id}}}, timeout=30)
    if r.is_error or not r.json().get("success"):
        raise RuntimeError(f"ElevenLabs did not place the call ({r.status_code}): {r.text[:300]}")
    return r.json().get("conversation_id")


def _inbound_call(msgs: list) -> str | None:
    """A call to the Photon line. The agent's prompt carries ElevenLabs' caller ID and conversation ID (a browser call
    has no caller ID). A phone registration gets the menu; a demo-list number with none gets the registration call;
    anyone else gets a person. Contacts made for synthetic demo patients do not route inbound calls."""
    # shortcut: caller ID can be spoofed on the phone network; a real line would confirm who is calling on the call
    system = next((m.get("content") for m in msgs if m.get("role") == "system"), None)
    found = re.search(r"caller=(\+\d{8,15}) conversation=(\S+)", system if isinstance(system, str) else "")
    if not found:
        return None
    caller, conversation = found.groups()
    if known := store.get("conversation", conversation):
        return known["call_id"]
    if patient_id := registry.patient_for_phone(caller):
        call_id = start_call(patient_id, "menu", phone=caller)
    elif caller in registry.demo_callers():
        call_id = start_call(None, "register", phone=caller)
    else:
        return None
    store.put("conversation", conversation, {"call_id": call_id, "caller": caller})
    return call_id


def _latest_ride(patient_id: str) -> dict | None:
    rides = [j for j in store.all("job") if j["patient_id"] == patient_id and j["kind"] == "ride"]
    return rides[-1] if rides else None


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
    call_id = extra.get("call_id") or _inbound_call(msgs)  # a caller number in the extra body is never trusted
    then = None
    can_hang_up = any((t.get("function") or {}).get("name") == "end_call" for t in body.get("tools") or [])
    if not (call_id and (call := store.get("call", call_id))):
        line = render("human_handoff")
    else:
        try:
            line = respond(call_id, text, defer=True)  # keypad digits arrive as a bare user turn; the interpreter reads them
            now = store.get("call", call_id)
            steps = [lambda: run_help(call_id)] if now.get("help_action") else []  # a help request opens after the line
            if call["status"] == "active" and now["status"] == "done":
                from hearth.messaging.photon import after_call

                steps.append(lambda: after_call(call_id))
            then = (lambda: [step() for step in steps]) if steps else None
        except Exception as e:  # a bug must not leave the caller with a dead line: a person takes over
            log.exception("voice turn failed for %s", call_id)
            call = store.get("call", call_id)
            _end(call, "handoff", "error", f"{type(e).__name__}: {e}")
            store.put("call", call_id, call)
            line = render("human_handoff")
    # the call is over (closed, or a person has it, or no one matched the caller): end it after this line, so nothing
    # heard afterwards (the agent's own closing words, on the first real call) can re-flag a finished call
    now = store.get("call", call_id) if can_hang_up and call_id else None
    hang_up = can_hang_up and (now is None or now["status"] in ("done", "handoff", "escalated"))
    return StreamingResponse(_sse(line, body.get("model", "hearth-voice"), then, hang_up), media_type="text/event-stream")


def _sse(line: str, model: str, then=None, hang_up: bool = False):
    base = {"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}

    def chunk(delta: dict, finish: str | None) -> str:
        return "data: " + json.dumps(base | {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"

    yield chunk({"role": "assistant", "content": line}, None)
    if hang_up:  # ElevenLabs' end_call system tool: the line above is spoken, then the call ends
        yield chunk({"tool_calls": [{"index": 0, "id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                                     "function": {"name": "end_call", "arguments": json.dumps({"reason": "call finished"})}}]}, None)
    yield chunk({}, "tool_calls" if hang_up else "stop")
    yield "data: [DONE]\n\n"
    if then:  # after the caller has the line, so the follow-up text adds no delay to the call
        try:
            then()
        except Exception:
            log.exception("after-call step failed")


def setup(public_url: str) -> str:
    """Creates (or, with ELEVENLABS_AGENT_ID set, updates) the ElevenLabs agent whose model is this server."""
    api, h = "https://api.elevenlabs.io/v1/convai", {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    custom = {"url": public_url.rstrip("/") + "/voice/v1", "model_id": "hearth-voice"}
    if secret := os.environ.get("HEARTH_VOICE_SECRET"):
        r = httpx.post(f"{api}/secrets", headers=h, json={"type": "new", "name": f"hearth-voice-{int(time.time())}", "value": secret})
        r.raise_for_status()
        custom["api_key"] = {"secret_id": r.json()["secret_id"]}
    config = {
        "name": "Hearth voice line (simulated patients)",
        "conversation_config": {
            "agent": {"first_message": "", "language": "en", "prompt": {
                "prompt": "Every reply comes from the Hearth custom model endpoint. "
                          "caller={{system__caller_id}} conversation={{system__conversation_id}}", "llm": "custom-llm", "custom_llm": custom,
                "built_in_tools": {"end_call": {"type": "system", "name": "end_call", "description": "Ends the call after a hand-off.",
                                                "params": {"system_tool_type": "end_call"}}}}},
            "turn": {"turn_timeout": a("voice.turn_timeout_s"), "turn_eagerness": "patient"},
            "tts": {"optimize_streaming_latency": a("voice.tts_streaming_optimization")},
            "conversation": {"dtmf_input_settings": {"dtmf_input_timeout": 2, "hash_terminator": True}},
        },
        "platform_settings": {"overrides": {"custom_llm_extra_body": True,  # carries call_id to our endpoint
                                            "conversation_config_override": {"conversation": {"text_only": True}}}},
    }
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
    r = (httpx.patch(f"{api}/agents/{agent_id}", headers=h, json=config, timeout=30) if agent_id
         else httpx.post(f"{api}/agents/create", headers=h, json=config, timeout=30))
    if r.is_error:
        sys.exit(f"ElevenLabs refused the agent config ({r.status_code}): {r.text[:500]}")
    return agent_id or r.json()["agent_id"]


if __name__ == "__main__":
    if sys.argv[1:2] == ["reset"] and len(sys.argv) == 3:
        print(f"removed {registry.reset(sys.argv[2])} registration(s) for that number")
    elif sys.argv[1:2] == ["setup"] and len(sys.argv) == 3:
        print("ELEVENLABS_AGENT_ID=" + setup(sys.argv[2]))
    else:
        sys.exit("usage: python -m hearth.messaging.voice setup <public https url of the API> | reset <phone>")
