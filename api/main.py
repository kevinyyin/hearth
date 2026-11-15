"""Hearth API: run files for the map, the building agent's surveys and refuge proposals, and the approval-gated call."""
import hmac
import json
import logging
import os
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from api import live
from hearth import agents, dispatch, remote, staging, store
from hearth.buildings import refuge, status, tools
from hearth.messaging import registry
from hearth.buildings.agent import survey
from hearth.buildings.brief import access_brief
from hearth.buildings.profile import hours_to_unsafe, layer_effects
from hearth.config import ROOT, a
from hearth.contracts import BuildingProfile, Equipment, Home, Patient, TraceEvent, Vehicle
from hearth.sim.day import run_day

RESULTS = ROOT / "results"
DEMO_PATIENTS = ROOT / "data" / "demo" / "patients.json"
PATIENTS_FILE = ROOT / "data" / "processed" / "patients_beryl_2024_s1.parquet"
PATIENTS_JSON = "processed/patients_beryl_2024_s1.json"  # the same patients, in private storage for the hosted API

app = FastAPI(title="Hearth (simulated patients)")
log = logging.getLogger("hearth.api")


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
    try:
        return await call_next(request)
    except Exception as e:
        # Uncaught, a crash leaves as a bare 500 outside CORS, which the browser shows only as "Failed to fetch".
        # Answered here, inside CORS, the page can say what failed; the traceback goes to the server log.
        log.exception("unhandled error on %s", request.url.path)
        if isinstance(e, httpx.HTTPStatusError):
            return JSONResponse({"detail": f"an upstream service answered {e.response.status_code}"}, status_code=502)
        if isinstance(e, httpx.HTTPError):
            return JSONResponse({"detail": f"an upstream service did not answer ({type(e).__name__})"}, status_code=502)
        return JSONResponse({"detail": f"server error ({type(e).__name__})"}, status_code=500)


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
    """Demo patients first, then lane S's patients file, then the store (phone registrants live only there). Stored as a
    "patient" doc so the voice lane can read it."""
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
    if found is None and (stored := dispatch._valid(Patient, store.get("patient", patient_id))):
        return stored  # a phone registrant: already stored by the registration call
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


# ---- the simulation page's day, planned by the central planner ----
class _DayHousehold(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    needsAt: float = Field(ge=0, le=100_000)  # a long backup is a need after the day ends, not an error
    repeats: bool


class _DayStation(BaseModel):
    name: str = Field(max_length=40)
    at: tuple[float, float]  # [lon, lat], as the page writes it

    @field_validator("at")
    @classmethod
    def _on_earth(cls, at):
        if not (-180 <= at[0] <= 180 and -90 <= at[1] <= 90):
            raise ValueError("a station must be [lon, lat]")
        return at


class _DayConstants(BaseModel):  # each field is bounded, and so is the work: the page sends 15 vans and 96 steps
    stations: list[_DayStation] = Field(min_length=1, max_length=10)
    crewsPerStation: int = Field(ge=1, le=10)
    cruise: float = Field(gt=0, le=10)
    serviceH: float = Field(ge=0, le=4)
    dt: float = Field(ge=0.05, le=1)
    runHours: float = Field(ge=1, le=48)
    refillH: float = Field(ge=0.5, le=48)
    capacity: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def _bounded_work(self):
        if len(self.stations) * self.crewsPerStation > 30:
            raise ValueError("at most 30 vans in all")
        if self.runHours / self.dt > 200:
            raise ValueError("at most 200 steps: a longer day needs a larger dt")
        return self


class DayIn(BaseModel):
    households: list[_DayHousehold] = Field(max_length=600)
    constants: _DayConstants


@app.post("/api/sim/day")
def sim_day(body: DayIn):
    """The Hearth side of the simulation page's day, in the shape the page draws (`SideSim` in web/lib/simulation.ts).
    The page sends its own households and constants; the routes come from `hearth.routing`."""
    return run_day([h.model_dump() for h in body.households], body.constants.model_dump())


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
           "scan_ids": tools.matterport_scan_ids(building_id), "scan_sdk_key": os.environ.get("MATTERPORT_SDK_KEY") or None,
           # what someone said by phone today about power and the elevator, and whether this building's office can be called
           "status": status.latest(building_id), "can_call": building_id in registry.building_phones()}
    if doc := store.get("profile", building_id):
        p = BuildingProfile.model_validate(doc)
        # validated, so profiles stored before a contract field existed get it as unknown
        out.update(profile=p.model_dump(mode="json") | {"cached": True}, brief=access_brief(p).model_dump(), layer_effects=layer_effects(p),
                   hours_to_unsafe=hours_to_unsafe(p.heat_time_constant_h))
    return out


@app.post("/api/buildings/{building_id}/call")
def call_building(building_id: str):
    """Rings the building's office about power and the elevator. Only a number in HEARTH_BUILDING_PHONES: every phone
    number in the CoStar kit is fake."""
    _building(building_id)
    if building_id not in registry.building_phones():
        raise HTTPException(403, "no phone number is set for this building")
    call_id = live.start_call(None, "building_check", building_id=building_id)
    return {"call_id": call_id, "conversation_id": live.dial(call_id)}


@app.get("/api/buildings/{building_id}/image")
def building_image(building_id: str):
    rec = _building(building_id)
    img = tools.vexcel_image(building_id, rec["lat"], rec["lon"])
    if img is None:
        raise HTTPException(404, "no aerial image")
    return FileResponse(img, media_type="image/png")


@app.get("/api/buildings/{building_id}/entrance")
def building_entrance(building_id: str):
    """Where a vision model reads the way in on the aerial tile, for a home whose resident has marked none."""
    rec = _building(building_id)
    try:
        spot = tools.aerial_entrance(building_id, rec["lat"], rec["lon"])
    except Exception:  # the reading is optional: a vision or Vexcel failure is "no reading", not a broken page
        spot = None
    if spot is None:
        raise HTTPException(404, "no entrance reading")
    return spot


@app.get("/api/buildings/{building_id}/survey")
def building_survey(building_id: str, fresh: bool = False, patient_id: str | None = None):
    """`patient_id`: the phone registrant whose registration started it, when the dispatch page did. A cached profile
    is read back untracked; a live survey is a stored run, refused while one for this building is running."""
    rec = _building(building_id)
    events = survey(building_id, rec["address"], rec["lat"], rec["lon"], use_cache=not fresh)
    if not fresh and (doc := store.get("profile", building_id)) and doc.get("method", "agent") == "agent":
        return _sse(events)
    try:
        run = agents.claim("survey", building_id=building_id, patient_id=patient_id, address=rec["address"])
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _sse(agents.track(run, events))


@app.get("/api/buildings/{building_id}/survey/recording")
def survey_recording(building_id: str):
    """The last live survey of this building that finished, every event with its seconds; 404 before the first."""
    _building(building_id)
    if (doc := store.get(agents.RECORDING, building_id)) is None:
        raise HTTPException(404, "no recorded survey")
    return doc


# ---- home markup: what a resident persona says about their own home, shown to the responder ----
@app.get("/api/demo-patients")
def demo_patients():
    """The demo personas whose building exists in the data being served (the fixtures, or the CoStar extract)."""
    rows = json.loads(DEMO_PATIENTS.read_text()) if DEMO_PATIENTS.exists() else []
    return [r for r in rows if r.get("building_id") and tools.costar_record(r["building_id"])]


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


@app.get("/api/registrations")
def registrations():
    """Phone registrations, newest first, and registration calls that ended before anyone was registered."""
    from hearth.messaging import registry

    return registry.registrations()


@app.post("/api/storm")
def storm(round: registry.Round = Body("week", embed=True)):
    """Simulated: one round of calls to every phone on the county's list. No body means a week out, as the first button did."""
    return registry.storm(round)


# ---- help loop: a resident asks, a model orders, code offers the job to a crew with a refuge as the drop-off ----
CrewName = PathParam(pattern=r"^[A-Za-z0-9 _-]{1,40}$")


def _tracker(patient_id: str) -> dict:
    """What the resident may read: fixed lines by state, never the model's reason."""
    return dispatch.tracker(dispatch.request(patient_id))


@app.get("/api/patients/{patient_id}/help")
def help_status(patient_id: str):
    if dispatch.person(patient_id) is None:  # polled every few seconds: look the record up (and store it) only once
        _patient(patient_id)
    dispatch.expire()
    return _tracker(patient_id)


@app.post("/api/patients/{patient_id}/help")
def ask_for_help(patient_id: str):
    _patient(patient_id)  # also stores the patient record, which dispatch reads
    try:
        dispatch.open_request(patient_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _tracker(patient_id)


@app.post("/api/patients/{patient_id}/safe")
def say_safe(patient_id: str):
    _patient(patient_id)
    try:
        dispatch.mark_safe(patient_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _tracker(patient_id)


class CrewIn(BaseModel):
    base_building_id: str
    vehicle: Vehicle
    equipment: list[Equipment] = []
    on_duty: bool = True


@app.put("/api/crews/{crew_id}")
def save_crew(body: CrewIn, crew_id: str = CrewName):
    try:
        return dispatch.save_crew(crew_id, body.base_building_id, body.vehicle, body.equipment, body.on_duty)
    except KeyError:
        raise HTTPException(422, "no such building")


def _crew_view(crew_id: str) -> dict:
    """The crew and its current offer or job, with what the job card shows."""
    crew, req, job = dispatch.crew(crew_id), dispatch.crew_job(crew_id), None
    if crew and req and (who := dispatch.person(req.patient_id)):
        patient, home = who
        here = dispatch.locate(patient, home)
        job = {"request": req, "patient": patient, "home": home, "address": here.address, "building_id": here.building_id,
               "km": round(tools._km((crew.lat, crew.lon), (here.lat, here.lon)), 1)}
    return {"crew": crew, "job": job, "staging": staging.chosen()}


@app.get("/api/crews/{crew_id}/job")
def crew_job(crew_id: str = CrewName):
    dispatch.expire()
    return _crew_view(crew_id)


class JobAction(BaseModel):
    action: dispatch.Action
    patient_id: str  # the resident on the card the crew pressed the button on


@app.post("/api/crews/{crew_id}/job")
def crew_action(body: JobAction, crew_id: str = CrewName):
    try:
        dispatch.crew_action(crew_id, body.action, body.patient_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _crew_view(crew_id)


@app.get("/api/dispatch")
def dispatch_board():
    """The dispatch page's one poll: requests with where they are, crews, agent runs and the ones to start, refuge
    proposals waiting on a person, and the storm rounds placed. Ended requests older than `dispatch_page.window_h` drop off."""
    dispatch.expire()
    since = dispatch._now() - timedelta(hours=a("dispatch_page.window_h"))
    rows = []
    for req in dispatch.board():
        if (who := dispatch.person(req.patient_id)) and (req.state in dispatch.LIVE or max(req.times.values(), default=since) > since):
            here = dispatch.locate(*who)
            rows.append({"request": req, "patient": who[0], "home": who[1], "device": who[0].device, "mobility": who[0].mobility,
                         "address": here.address, "building_id": here.building_id, "lat": here.lat, "lon": here.lon})
    on = {r.job.org_id: r.patient_id for r in dispatch.requests() if r.state in dispatch.WITH_CREW and r.job}
    return {"requests": rows, "crews": [{"crew": c, "patient_id": on.get(c.crew_id)} for c in dispatch.crews()],
            "agents": agents.runs(), "to_start": agents.to_start(), "proposals": [p for p in store.all("proposal") if p.get("status") == "pending"],
            "storm": registry.storm_history()}


@lru_cache(maxsize=1)
def _simulated() -> list[list[float]]:
    for run_id in a("dispatch_page.simulated_runs"):
        try:
            pts = [[p["lon"], p["lat"]] for p in json.loads(_run_file(run_id, "snapshots/0.json").read_text())["patients"]]
        except HTTPException:
            continue
        return pts[:: max(1, len(pts) // a("dispatch_page.simulated_dots"))][: a("dispatch_page.simulated_dots")]
    return []


@app.get("/api/dispatch/simulated")
def simulated():
    """[lon, lat] of a sample of the county replay's simulated households, drawn faintly behind the real ones."""
    return _simulated()


@app.post("/api/dispatch/{patient_id}/handled")
def handled(patient_id: str):
    try:
        return dispatch.mark_handled(patient_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ---- refuge proposals and the approval gate ----
@app.post("/api/patients/{patient_id}/propose")
def propose(patient_id: str, body: dict | None = Body(default=None)):
    patient = _patient(patient_id)
    dark = set((body or {}).get("dark_zips") or [patient.zip])  # the patient's own ZIP is dark by definition
    here = dispatch.locate(patient, (dispatch.person(patient_id) or (None, None))[1])
    try:
        run = agents.claim("refuge", building_id=here.building_id, patient_id=patient_id, address=here.address,
                           request_at=agents.request_at(dispatch.request(patient_id)))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _sse(agents.track(run, refuge.propose(patient, dark)))


@app.get("/api/shelter-tile")
def shelter_tile(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    """The aerial around a shelter site, for the dispatcher to judge the lead by eye. A site has no building id, so it is
    asked for by its coordinates."""
    # shortcut: the building tile's 800 px PNG (about 1.2 MB) behind a thumbnail; ask Vexcel for a 400 px JPEG if the leads load slowly
    img = tools.vexcel_image("shelter", lat, lon, a("shelter.tile_half_m"), f"{lat:.5f}_{lon:.5f}")
    if img is None:
        raise HTTPException(404, "no aerial image")
    return FileResponse(img, media_type="image/png")


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
        dispatch.use_refuge(prop.patient_id, prop.options[0])  # the dispatcher's pick becomes the drop-off, and a crew is offered
        try:
            out["call_id"] = live.on_approved(prop)
            out["phone_call"] = live.dial(out["call_id"])  # the patient's phone rings when a person entered one
        except Exception as e:  # the approval stands; the dispatcher sees the call did not start
            out["call_error"] = f"{type(e).__name__}: {e}"
    return out


class CallIn(BaseModel):
    patient_id: str | None = None
    kind: Literal["impact", "move_consent", "register"]
    phone: str | None = None  # register only: the browser phone stands in for this listed demo number (it has no caller ID)


# ---- staging lots: a real parking lot for crews to gather at, proposed from CoStar and picked by the dispatcher ----
@app.get("/api/staging")
def staging_board():
    return staging.view()


class StagingChoice(BaseModel):
    building_id: str | None  # None clears the choice


@app.post("/api/staging")
def choose_staging(body: StagingChoice):
    if body.building_id is None:
        staging.clear()
    else:
        try:
            staging.choose(body.building_id)
        except ValueError as e:
            raise HTTPException(409, str(e))
    return {"chosen": staging.chosen()}


@app.get("/api/buildings/{building_id}/lot-image")
def lot_image(building_id: str):
    rec = _building(building_id)
    img = tools.vexcel_image(building_id, rec["lat"], rec["lon"], 150, "lot")
    if img is None:
        raise HTTPException(404, "no aerial image")
    return FileResponse(img, media_type="image/png")


@app.get("/api/buildings/{building_id}/lot-reading")
def lot_reading(building_id: str):
    rec = _building(building_id)
    try:
        note = tools.lot_reading(building_id, rec["lat"], rec["lon"])
    except Exception:  # the reading is optional: a vision or Vexcel failure is "no reading", not a broken card
        note = None
    if note is None:
        raise HTTPException(404, "no lot reading")
    return note


@app.post("/api/calls")
def calls(body: CallIn):
    if body.kind == "register":
        from hearth.messaging import registry

        if body.phone not in registry.demo_callers():  # strangers' details never reach the store
            raise HTTPException(403, "only a number on the demo caller list can register")
        return {"call_id": live.start_call(None, "register", phone=body.phone)}
    if not body.patient_id:
        raise HTTPException(422, "a patient id is needed")
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
