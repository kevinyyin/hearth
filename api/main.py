"""Hearth API: run files for the map, the building agent's surveys and refuge proposals, and the approval-gated call."""
import hmac
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from api import live
from hearth import remote, store
from hearth.buildings import refuge, tools
from hearth.buildings.agent import survey
from hearth.buildings.brief import access_brief
from hearth.buildings.profile import hours_to_unsafe, layer_effects
from hearth.config import ROOT
from hearth.contracts import BuildingProfile, Home, Patient, TraceEvent

RESULTS = ROOT / "results"
DEMO_PATIENTS = ROOT / "data" / "demo" / "patients.json"
PATIENTS_FILE = ROOT / "data" / "processed" / "patients_beryl_2024_s1.parquet"
PATIENTS_JSON = "processed/patients_beryl_2024_s1.json"  # the same patients, in private storage for the hosted API

app = FastAPI(title="Hearth (simulated patients)")


@app.middleware("http")
async def guard(request: Request, call_next):
    """Hosted (HEARTH_PASSWORD set): every route needs the shared password, sent as a bearer token. Local: the API is for
    this machine, so requests through a tunnel (forwarding headers) are refused. Either way /voice keeps its own secret,
    /photon checks Photon's signature, and CORS preflights pass."""
    if request.method == "OPTIONS" or request.url.path.startswith(("/voice/", "/photon/")):
        return await call_next(request)
    if password := os.environ.get("HEARTH_PASSWORD"):
        given = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(given.encode(), password.encode()):
            return JSONResponse({"detail": "password required"}, status_code=401)
    elif "x-forwarded-for" in request.headers or "cf-connecting-ip" in request.headers:
        return JSONResponse({"detail": "the dispatcher API is not reachable through a tunnel"}, status_code=403)
    return await call_next(request)


# added after the guard so they wrap it: a 401 still carries CORS headers the browser can read
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("HEARTH_WEB_ORIGINS", "http://localhost:3000").split(","),
                   allow_origin_regex=os.environ.get("HEARTH_WEB_ORIGIN_REGEX"),  # preview deployments get new hostnames
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)  # a full-county snapshot is megabytes of JSON; gzip keeps scrubbing smooth
try:  # lane V: the OpenAI-compatible endpoint ElevenLabs calls as its model, and Photon's webhook
    from hearth.messaging.photon import router as photon_router
    from hearth.messaging.voice import router as voice_router

    app.include_router(voice_router)
    app.include_router(photon_router)
except ImportError:
    pass


def _sse(events: Iterator[TraceEvent]) -> StreamingResponse:
    return StreamingResponse((f"data: {e.model_dump_json()}\n\n" for e in events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _run_file(run_id: str, rel: str) -> Path:
    """A run's file from the repo's results/, else from private storage (the county replay is too big to bundle)."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", run_id):
        raise HTTPException(404, "no such run")
    local = RESULTS / run_id / rel
    if local.exists():
        return local
    if (fetched := remote.fetch(f"results/{run_id}/{rel}")) is not None:
        return fetched
    raise HTTPException(404, "no such run or file")


def _json_file(path: Path):
    if not path.exists():
        raise HTTPException(404, f"{path.name} not produced yet")
    return json.loads(path.read_text())


def _building(building_id: str) -> dict:
    try:
        rec = tools.costar_record(building_id)
    except ValueError:
        rec = None
    if rec is None:
        raise HTTPException(404, "no such building")
    return rec


def _patient(patient_id: str) -> Patient:
    """Demo patients first, then lane S's patients file. Stored as a "patient" doc so the voice lane can read it."""
    found = None
    if DEMO_PATIENTS.exists():
        found = next((Patient(**r) for r in json.loads(DEMO_PATIENTS.read_text()) if r["patient_id"] == patient_id), None)
    if found is None and PATIENTS_FILE.exists():  # local: the simulation's parquet (pandas is a sim-only dependency)
        import pandas as pd

        df = pd.read_parquet(PATIENTS_FILE)
        hit = df[df["patient_id"] == patient_id]
        if len(hit):
            found = Patient(**json.loads(hit.iloc[[0]].to_json(orient="records"))[0])
    elif found is None and (copy := remote.fetch(PATIENTS_JSON)):  # hosted: a JSON copy
        found = next((Patient(**r) for r in json.loads(copy.read_text()) if r["patient_id"] == patient_id), None)
    if found is None:
        raise HTTPException(404, "no such patient")
    store.put("patient", patient_id, found)
    return found


# ---- replay files ----
@app.get("/api/runs")
def runs():
    keys = ("run_id", "scenario", "policy", "crews", "seed")
    ids = [p.parent.name for p in RESULTS.glob("*/meta.json")]
    try:
        ids += [r for r in remote.listdir("results") if re.fullmatch(r"[A-Za-z0-9_]+", r) and r not in ids]
    except Exception:  # storage unreachable: list the bundled runs
        pass
    return [{k: m.get(k) for k in keys} for m in (json.loads(_run_file(r, "meta.json").read_text()) for r in sorted(ids))]


@app.get("/api/runs/{run_id}/meta")
def meta(run_id: str):
    return json.loads(_run_file(run_id, "meta.json").read_text())


@app.get("/api/runs/{run_id}/snapshots/{i}")
def snapshot(run_id: str, i: int):
    return json.loads(_run_file(run_id, f"snapshots/{i}.json").read_text())


@lru_cache(maxsize=4)
def _events(path: str, mtime: float) -> list[dict]:
    """Parsed once per run file (a county run has about 140k events); the mtime key drops it when the run is regenerated."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


@app.get("/api/runs/{run_id}/events")
def events(run_id: str, patient_id: str | None = None):
    path = _run_file(run_id, "events.jsonl")
    rows = _events(str(path), path.stat().st_mtime)
    return [e for e in rows if patient_id is None or e.get("patient_id") == patient_id]


@app.get("/api/results")
def results():
    return _json_file(RESULTS / "sweep_beryl_2024.json")


# ---- buildings ----
@app.get("/api/buildings")
def buildings():
    method = {p["building_id"]: p.get("method", "agent") for p in store.all("profile")}
    return [{"building_id": r["building_id"], "name": r.get("name"), "address": r["address"], "lat": r["lat"], "lon": r["lon"],
             "property_type": r["property_type"], "has_scan": bool(r.get("matterport_model_ids")),
             "surveyed": method.get(r["building_id"]) == "agent", "records_only": method.get(r["building_id"]) == "fields"}
            for r in tools.costar_all()]


@app.get("/api/buildings/ranking")
def ranking():
    return _json_file(ROOT / "data" / "processed" / "building_ranking.json")


@app.get("/api/buildings/{building_id}")
def building(building_id: str):
    rec = _building(building_id)
    out = {"building_id": building_id, "name": rec.get("name"), "address": rec["address"], "lat": rec["lat"], "lon": rec["lon"],
           "profile": None, "brief": None, "layer_effects": None, "hours_to_unsafe": None,
           "embed_url": tools.matterport_embed_url(building_id), "image_url": f"/api/buildings/{building_id}/image",
           # the embed SDK key is a browser key by design; it travels here so it sits behind the password, not in the web bundle
           "scan_ids": tools.matterport_scan_ids(building_id), "scan_sdk_key": os.environ.get("MATTERPORT_SDK_KEY") or None}
    if doc := store.get("profile", building_id):
        p = BuildingProfile.model_validate(doc)
        # validated, so profiles stored before a contract field existed get it as unknown
        out.update(profile=p.model_dump(mode="json") | {"cached": True}, brief=access_brief(p).model_dump(), layer_effects=layer_effects(p),
                   hours_to_unsafe=hours_to_unsafe(p.heat_time_constant_h))
    return out


@app.get("/api/buildings/{building_id}/image")
def building_image(building_id: str):
    rec = _building(building_id)
    img = tools.vexcel_image(building_id, rec["lat"], rec["lon"])
    if img is None:
        raise HTTPException(404, "no aerial image")
    return FileResponse(img, media_type="image/png")


@app.get("/api/buildings/{building_id}/survey")
def building_survey(building_id: str, fresh: bool = False):
    rec = _building(building_id)
    return _sse(survey(building_id, rec["address"], rec["lat"], rec["lon"], use_cache=not fresh))


# ---- home markup: what a resident persona says about their own home, shown to the responder ----
@app.get("/api/demo-patients")
def demo_patients():
    return json.loads(DEMO_PATIENTS.read_text()) if DEMO_PATIENTS.exists() else []


def _home(doc: dict | None) -> Home | None:
    """A stored home, or None when there is none or it no longer fits the contract: the resident then starts a fresh
    one, and one bad document cannot take the responder's whole list down."""
    try:
        return Home.model_validate(doc) if doc else None
    except ValidationError:
        return None


@app.get("/api/patients/{patient_id}/home")
def home(patient_id: str):
    return {"patient": _patient(patient_id), "home": _home(store.get("home", patient_id))}


@app.put("/api/patients/{patient_id}/home")
def save_home(patient_id: str, body: Home):
    if body.patient_id != patient_id:
        raise HTTPException(400, "patient id does not match")
    _patient(patient_id)
    try:
        _building(body.building_id)
    except HTTPException:
        raise HTTPException(422, "no such building")
    if body.scan_id and body.scan_id not in tools.matterport_scan_ids(body.building_id):
        raise HTTPException(422, "that scan is not one of this building's")
    store.put("home", patient_id, body)
    return body


@app.get("/api/homes")
def homes():
    out = []
    for doc in store.all("home"):
        if (h := _home(doc)) is None:
            continue
        try:
            out.append({"home": h, "patient": _patient(h.patient_id), "address": _building(h.building_id)["address"]})
        except HTTPException:  # the patient or building is gone: not a job a responder can take
            continue
    return out


# ---- refuge proposals and the approval gate ----
@app.post("/api/patients/{patient_id}/propose")
def propose(patient_id: str, body: dict | None = Body(default=None)):
    patient = _patient(patient_id)
    dark = set((body or {}).get("dark_zips") or [patient.zip])  # the patient's own ZIP is dark by definition
    return _sse(refuge.propose(patient, dark))


@app.get("/api/proposals")
def proposals():
    return store.all("proposal")


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = None


@app.post("/api/proposals/{proposal_id}/decision")
def decision(proposal_id: str, body: Decision):
    if body.decision == "reject" and not (body.reason or "").strip():
        raise HTTPException(400, "a rejection needs a reason")
    try:
        prop = refuge.decide(proposal_id, body.decision, body.reason)
    except KeyError:
        raise HTTPException(404, "no such proposal")
    except ValueError as e:
        raise HTTPException(409, str(e))
    out = prop.model_dump(mode="json")
    if prop.status == "approved":
        try:
            out["call_id"] = live.on_approved(prop)
            out["phone_call"] = live.dial(out["call_id"])  # the patient's phone rings when a person entered one
        except Exception as e:  # the approval stands; the dispatcher sees the call did not start
            out["call_error"] = f"{type(e).__name__}: {e}"
    return out


class CallIn(BaseModel):
    patient_id: str
    kind: Literal["impact", "move_consent"]


@app.post("/api/calls")
def calls(body: CallIn):
    proposal_id = None
    if body.kind == "move_consent":
        approved = [p for p in store.all("proposal") if p["patient_id"] == body.patient_id and p["status"] == "approved"]
        if not approved:
            raise HTTPException(409, "no approved proposal for this patient; a dispatcher must approve a move first")
        proposal_id = approved[-1]["proposal_id"]
    try:
        return {"call_id": live.start_call(body.patient_id, body.kind, proposal_id)}
    except ImportError:
        raise HTTPException(503, "voice lane not installed yet")


@app.get("/api/calls/{call_id}")
def call(call_id: str):
    if (doc := store.get("call", call_id)) is None:
        raise HTTPException(404, "no such call")
    return doc
