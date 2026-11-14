"""Hearth API: run files for the map, the building agent's surveys and refuge proposals, and the approval-gated call."""
import json
import re
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from api import live
from hearth import store
from hearth.buildings import refuge, tools
from hearth.buildings.agent import survey
from hearth.buildings.brief import access_brief
from hearth.buildings.profile import hours_to_unsafe, layer_effects
from hearth.config import ROOT
from hearth.contracts import BuildingProfile, Patient, TraceEvent

RESULTS = ROOT / "results"
DEMO_PATIENTS = ROOT / "data" / "demo" / "patients.json"
PATIENTS_FILE = ROOT / "data" / "processed" / "patients_beryl_2024_s1.parquet"

app = FastAPI(title="Hearth (simulated patients)")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)  # a full-county snapshot is megabytes of JSON; gzip keeps scrubbing smooth
try:  # lane V's OpenAI-compatible endpoint that ElevenLabs calls as its model
    from hearth.messaging.voice import router as voice_router

    app.include_router(voice_router)
except ImportError:
    pass


def _sse(events: Iterator[TraceEvent]) -> StreamingResponse:
    return StreamingResponse((f"data: {e.model_dump_json()}\n\n" for e in events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _run(run_id: str) -> Path:
    d = RESULTS / run_id
    if not re.fullmatch(r"[A-Za-z0-9_]+", run_id) or not (d / "meta.json").exists():
        raise HTTPException(404, "no such run")
    return d


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
    if found is None and PATIENTS_FILE.exists():
        import pandas as pd

        df = pd.read_parquet(PATIENTS_FILE)
        hit = df[df["patient_id"] == patient_id]
        if len(hit):
            found = Patient(**json.loads(hit.iloc[[0]].to_json(orient="records"))[0])
    if found is None:
        raise HTTPException(404, "no such patient")
    store.put("patient", patient_id, found)
    return found


# ---- replay files ----
@app.get("/api/runs")
def runs():
    keys = ("run_id", "scenario", "policy", "crews", "seed")
    return [{k: m.get(k) for k in keys} for m in (json.loads(p.read_text()) for p in sorted(RESULTS.glob("*/meta.json")))]


@app.get("/api/runs/{run_id}/meta")
def meta(run_id: str):
    return json.loads((_run(run_id) / "meta.json").read_text())


@app.get("/api/runs/{run_id}/snapshots/{i}")
def snapshot(run_id: str, i: int):
    return _json_file(_run(run_id) / "snapshots" / f"{i}.json")


@app.get("/api/runs/{run_id}/events")
def events(run_id: str, patient_id: str | None = None):
    rows = [json.loads(line) for line in (_run(run_id) / "events.jsonl").read_text().splitlines() if line]
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
           "embed_url": tools.matterport_embed_url(building_id), "image_url": f"/api/buildings/{building_id}/image"}
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
