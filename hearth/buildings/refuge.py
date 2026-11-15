"""Refuge finder: hotels and senior housing outside the dark area, access checked by code, ranked by a deep agent,
and stopped at the library's approval interrupt. It books nothing. A dispatcher approves or rejects; rejections
are written to the agent's memory file and read on every later proposal."""
import json
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Literal
from zoneinfo import ZoneInfo

from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from hearth import store
from hearth.buildings import status, tools
from hearth.buildings.agent import survey
from hearth.buildings.trace import to_trace
from hearth.config import ROOT, a, anthropic_headers
from hearth.contracts import BuildingProfile, Patient, RefugeOption, RefugeProposal, TraceEvent

# shortcut: polygons for the Beryl replay's 132 Harris County ZIPs only, so a site in any other ZIP is dropped as unknown; swap in a full county file to keep those
ZCTA_FILE = ROOT / "data" / "processed" / "zcta_beryl_2024.geojson"
SHELTER_CAVEAT = "power, access and permission are not verified: a place to call about, not a shelter"
_zip_rings = None
_sites: dict[str, list[dict]] = {}  # patient_id -> shelter sites the running proposal's search found
MEMORY_FILE = str(tools.CACHE_ROOT / "memories" / "dispatcher.md")
MEMORY_SOURCE = "/memories/dispatcher.md"  # the same file, as the agent's filesystem backend (rooted at data/buildings) sees it
MEMORY_HEADER = "# Dispatcher decisions on refuge proposals\n"
NEEDS_STEP_FREE = {"wheelchair_manual", "wheelchair_power", "bedbound"}
_ctx: dict[str, tuple[Patient, set[str]]] = {}  # patient_id -> (patient, dark zips) for the running proposal
_graph = None


def outside_dark_area(zip: str | None, dark_zips: set[str]) -> bool:
    """Unknown ZIP is not outside: we cannot show the refuge has power."""
    return bool(zip) and zip not in dark_zips


def zip_at(lat: float, lon: float) -> str | None:
    """The ZIP whose polygon contains the point, or None. `population.zip_at` without numpy, which the hosted API does not install."""
    global _zip_rings
    if _zip_rings is None:
        polys = lambda g: [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        _zip_rings = {f["properties"]["zip"]: [ring for poly in polys(f["geometry"]) for ring in poly]
                      for f in json.loads(ZCTA_FILE.read_text())["features"]}

    def crossings(ring) -> int:  # even-odd ray cast, counted over outer rings and holes alike
        return sum((y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))
    return next((z for z, rings in _zip_rings.items() if sum(map(crossings, rings)) % 2), None)


def shelter_sites(patient: Patient, dark_zips: set[str]) -> list[dict]:
    """Places near the patient that look, from the air, like they could shelter someone, in a ZIP that is not dark, nearest
    first. Vexcel says what a place looks like and CoStar, where it has a record, what it is. Nothing says it has power, is
    open or would agree, so these are leads for a dispatcher to call about and never a proposal."""
    here = (patient.lat, patient.lon)
    tiles = [t | {"looks_like": phrase} for phrase in a("shelter.phrases")
             for t in tools.vexcel_search(*here, a("shelter.search_half_m"), phrase, a("shelter.tiles_per_phrase"))]
    sites = []
    for t in sorted(tiles, key=lambda t: -t["score"]):  # best match first, so it names a place several tiles cover
        at = (t["lat"], t["lon"])
        if outside_dark_area(z := zip_at(*at), dark_zips) and all(tools._km(at, (s["lat"], s["lon"])) * 1000 >= a("shelter.merge_m") for s in sites):
            sites.append(t | {"zip": z, "km": round(tools._km(here, at), 1)})
    sites = sorted(sites, key=lambda s: tools._km(here, (s["lat"], s["lon"])))[: a("shelter.max_sites")]
    records = [r for r in tools.costar_all() if r.get("lat") is not None]
    for s in sites:
        m = lambda r: tools._km((s["lat"], s["lon"]), (r["lat"], r["lon"])) * 1000
        near = min(records, key=m, default=None)
        s["costar"] = None if near is None or m(near) > a("shelter.costar_match_m") else {
            "building_id": near["building_id"], "name": near.get("name") or near["address"], "property_type": near["property_type"],
            "floors": near.get("floors"), "surface_spaces": near.get("surface_spaces"), "lot_acres": near.get("lot_acres"), "m": round(m(near))}
        s["caveat"] = SHELTER_CAVEAT
    return sites


SIMULATED_CALL = "the refuge confirmed by phone that it is running (simulated call)"
NEEDS_CALL = "needs a call"  # the first reason when the only open question is one a phone call to the refuge can settle


def eligible(option_profile: BuildingProfile, patient: Patient, elevator_confirmed: str | None = None) -> tuple[bool, list[str]]:
    """Code, not model. Wheelchair and bedbound patients need a step-free entrance, and an elevator above one floor.
    An elevator a scan shows but no record states counts only once the refuge has confirmed it; `elevator_confirmed` says
    who did (the building's office by phone, or the simulated call)."""
    p = option_profile
    if patient.mobility not in NEEDS_STEP_FREE:
        return True, [f"patient {patient.mobility.replace('_', ' ')}: no access constraint"]
    src = lambda f: f"{getattr(p, f).source}, confidence {getattr(p, f).confidence:.1f}"
    if p.step_free_entrance.value is None:
        return False, ["unverified access", "no layer showed a step-free entrance"]
    if p.step_free_entrance.value is not True:
        return False, [f"no step-free entrance ({src('step_free_entrance')})"]
    reasons = [f"step-free entrance ({src('step_free_entrance')})"]
    floors = p.floors.value
    if floors == 1:
        return True, reasons + ["single floor: no elevator needed"]
    if p.elevator_count.source == "matterport":  # seen, or not seen, in a scan: a scan covers a lobby and a few rooms
        if not p.elevator_count.value or p.elevator_count.value < 1:
            return False, ["unverified access", f"no elevator seen in the scans for {floors or 'an unknown number of'} floors, which does not show there is none"]
        seen = f"elevator seen in a scan ({src('elevator_count')})"
        if not elevator_confirmed:
            return False, [NEEDS_CALL, seen, "not confirmed running"]
        return True, reasons + [seen, elevator_confirmed]
    if p.elevator_count.value is None:
        return False, ["unverified access", f"elevator unknown for {floors or 'an unknown number of'} floors"]
    if p.elevator_count.value < 1:
        return False, [f"no elevator for {floors or 'unknown'} floors ({src('elevator_count')})"]
    return True, reasons + [f"{p.elevator_count.value} elevator(s) ({src('elevator_count')})"]


def confirm_elevator(building_id: str, dark_zips: set[str]) -> str | None:
    """Is a passenger elevator running? Who said so, or None. A building office's answer by phone within
    `refuge.building_answer_valid_h` decides; otherwise a simulated call: nobody is called, the answer is the assumption
    `refuge.elevator_runs_outside_outage`, and the question is only put to a building outside the dark area."""
    said = status.latest(building_id)
    if said and said["said_by"] == "building_office" and time.time() - said["t"] < a("refuge.building_answer_valid_h") * 3600:
        if said.get("elevator") != "yes":
            return None
        at = datetime.fromtimestamp(said["t"], ZoneInfo("America/Chicago")).strftime("%-I:%M %p")
        return f"the building's office said so by phone at {at}"
    rec = tools.costar_record(building_id)
    if rec is None or not outside_dark_area(rec.get("zip"), dark_zips):
        return None
    yes = bool(a("refuge.elevator_runs_outside_outage"))
    store.put("refuge_call", building_id, {"building_id": building_id, "simulated": True, "question": "Is a passenger elevator running?",
                                           "answer": "yes" if yes else "no", "t": time.time()})
    return SIMULATED_CALL if yes else None


def access(prof: BuildingProfile, patient: Patient, dark_zips: set[str]) -> tuple[bool, list[str]]:
    """`eligible`, plus the simulated call when the only thing missing is confirmation of an elevator a scan showed."""
    ok, why = eligible(prof, patient)
    if not ok and why[0] == NEEDS_CALL and (said := confirm_elevator(prof.building_id, dark_zips)):
        return eligible(prof, patient, elevator_confirmed=said)
    return ok, why


def _profile_for(building_id: str) -> BuildingProfile | None:
    """Survey with cache first; returns the final profile."""
    rec = tools.costar_record(building_id)
    if rec is None:
        return None
    last = None
    for last in survey(building_id, rec["address"], rec["lat"], rec["lon"]):
        pass
    return BuildingProfile.model_validate(last.data["profile"])


@tool
def search_refuges(patient_id: str) -> str:
    """Hotels and senior housing near the patient, outside the dark area, nearest first."""
    patient, dark = _ctx[patient_id]
    rows = tools.costar_search(["hotel", "senior_housing"], (patient.lat, patient.lon), a("refuge.search_radius_km"))
    rows = [r for r in rows if outside_dark_area(r.get("zip"), dark)][: a("refuge.max_candidates")]
    if not rows:
        return "No hotels or senior housing outside the dark area within range."
    return json.dumps([{"building_id": r["building_id"], "name": r.get("name") or r["address"], "type": r["property_type"],
                        "km": round(tools._km((patient.lat, patient.lon), (r["lat"], r["lon"])), 1),
                        "has_scan": bool(r.get("matterport_model_ids", True))} for r in rows])


@tool
def check_access(patient_id: str, building_id: str) -> str:
    """Survey a candidate (cached if surveyed before) and check, by code, whether this patient can get in. When a scan
    shows an elevator no record states, this places a simulated call to the refuge to confirm it."""
    patient, dark = _ctx[patient_id]
    prof = _profile_for(building_id)
    if prof is None:
        return f"{building_id}: not in CoStar."
    ok, why = access(prof, patient, dark)
    return json.dumps({"building_id": building_id, "eligible": ok, "reasons": why, "floors": prof.floors.value,
                       "layers_missing": prof.layers_missing, "survey_error": prof.error, "cached": prof.cached})


@tool
def submit_proposal(patient_id: str, options_json: str) -> str:
    """Send the ranked proposal to the dispatcher for approval. options_json: [{"building_id", "name", "reasons": [...],
    "sources": [...], "score": 0..1}], best first, eligible options only. The dispatcher must approve before anything happens."""
    return "The dispatcher approved this proposal. Nothing is booked; stop here."


@tool
def search_shelter_sites(patient_id: str) -> str:
    """Only when no candidate is eligible: an aerial search for places outside the dark area that look like a school gym,
    a church or a community centre. The dispatcher gets them as leads to call about; they are never proposed."""
    patient, dark = _ctx[patient_id]
    try:
        _sites[patient_id] = shelter_sites(patient, dark)
    except Exception as ex:  # a Vexcel failure or missing ZIP polygons means no leads, not a broken run
        return f"shelter site search unavailable ({type(ex).__name__}); stop here."
    # the model gets a count only: the dispatcher reads the sites from code, on the run's last event
    return f"{len(_sites[patient_id])} possible shelter site(s) sent to the dispatcher as leads to call about. None is confirmed; do not propose them. Stop here."


TOOLS = [search_refuges, check_access, submit_proposal, search_shelter_sites]
SYSTEM = """You find a temporary refuge with power for one simulated patient on a home medical device during a power
outage. You book nothing and contact no patient. The only contact is one check_access may make: a simulated call to a
refuge to confirm an elevator a scan showed. Steps:
1. Write a short to-do plan with write_todos.
2. Call search_refuges once.
3. Call check_access for each candidate, nearest first. Skip any building the dispatcher's notes in your memory say to avoid.
4. Eligibility from check_access is final; never propose an ineligible building. Rank eligible ones: closer first, then
   higher-confidence access evidence, then buildings with a scan. Reasons and sources come from check_access.
5. Call submit_proposal once with 1 to 3 options.
6. If no candidate is eligible, or search_refuges found none, call search_shelter_sites once instead, say in one sentence that
   no refuge was eligible, and stop without submitting. Those sites are unverified leads: never describe or propose them.
Be brief. No medical advice, no promises of help."""


def sync_memory() -> None:
    """Write the stored rejection notes to the agent's memory file. The notes live in the store, so a fresh server
    instance (whose temp folder starts empty) still remembers them."""
    Path(MEMORY_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(MEMORY_FILE).write_text((store.get("memory", "dispatcher") or {"text": MEMORY_HEADER})["text"])


def _build(checkpointer):
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain_anthropic import ChatAnthropic

    sync_memory()
    model = ChatAnthropic(model=a("models.agent"), default_headers=anthropic_headers(), timeout=60, max_retries=1,
                          output_config={"effort": a("models.agent_effort")})
    return create_deep_agent(model=model, tools=TOOLS, system_prompt=SYSTEM,
                             middleware=[TodoListMiddleware()], memory=[MEMORY_SOURCE], interrupt_on={"submit_proposal": True},
                             backend=FilesystemBackend(root_dir=tools.CACHE_ROOT, virtual_mode=True), checkpointer=checkpointer)


_pg_checkpoints_ready = False


@contextmanager
def _graph_session():
    """The refuge graph. With the store on Postgres, the paused agent is checkpointed there too, so an Approve that
    lands on another server instance can resume it; otherwise one in-memory graph per process."""
    global _graph, _pg_checkpoints_ready
    url = store.postgres_url()
    if not url:
        if _graph is None:
            _graph = _build(InMemorySaver())
        yield _graph
        return
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    with psycopg.connect(url, autocommit=True, prepare_threshold=None, row_factory=dict_row) as conn:
        saver = PostgresSaver(conn)
        if not _pg_checkpoints_ready:
            saver.setup()  # creates the checkpoint tables once
            _pg_checkpoints_ready = True
        yield _build(saver)


def _options(patient: Patient, options_json: str) -> list[RefugeOption]:
    """The agent's options, re-checked by code: only buildings with a stored profile that passes `eligible` survive."""
    dark = _ctx.get(patient.patient_id, (patient, {patient.zip}))[1]
    out = []
    for o in json.loads(options_json):
        rec, prof = tools.costar_record(o["building_id"]), store.get("profile", o["building_id"])
        if rec is None or prof is None or rec["property_type"] not in ("hotel", "senior_housing"):
            continue
        ok, why = access(BuildingProfile.model_validate(prof), patient, dark)
        if not ok or not outside_dark_area(rec.get("zip"), dark):
            continue
        km = tools._km((patient.lat, patient.lon), (rec["lat"], rec["lon"]))
        layers = sorted({v["source"] for k, v in prof.items() if isinstance(v, dict) and v.get("source") not in (None, "default")})
        out.append(RefugeOption(building_id=o["building_id"], name=rec.get("name") or rec["address"], lat=rec["lat"], lon=rec["lon"],
                                reasons=why + [f"{km:.1f} km away", "power at refuge not verified"], sources=layers,
                                score=float(o.get("score", 0))))
    return out


def propose(patient: Patient, dark_zips: set[str]) -> Iterator[TraceEvent]:
    """Stream the refuge agent's work. Ends at kind="interrupt" with data={"proposal_id"}, or kind="done" if nothing fits;
    that done event carries data["shelter_sites"] when the agent's shelter search ran."""
    t0, seq = time.time(), 0
    _ctx[patient.patient_id] = (patient, dark_zips)
    _sites.pop(patient.patient_id, None)
    thread = f"refuge-{patient.patient_id}-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 60}
    ask = (f"Find a refuge for simulated patient {patient.patient_id}: device {patient.device}, mobility {patient.mobility}, "
           f"heat/cold sensitivity {patient.temp_sensitive}.")
    error = None
    try:
        sync_memory()  # rejections recorded by any instance since this one started
        with _graph_session() as graph:
            for chunk in graph.stream({"messages": [{"role": "user", "content": ask}]}, config, stream_mode="updates", subgraphs=True):
                for e in to_trace(chunk, seq, t0, root="refuge"):
                    if e.kind != "interrupt":
                        seq += 1
                        yield e
                        continue
                    args = e.data["requests"][0]["action_requests"][0]["args"]
                    options = _options(patient, args["options_json"])
                    if not options:
                        error = "the agent proposed no option that passes the access check"
                        break
                    prop = RefugeProposal(proposal_id=f"P-{uuid.uuid4().hex[:8]}", patient_id=patient.patient_id, options=options,
                                          status="pending", thread_id=thread)
                    store.put("proposal", prop.proposal_id, prop)
                    yield TraceEvent(seq=seq, t=e.t, kind="interrupt", agent="dispatcher", text="waiting for dispatcher approval",
                                     data={"proposal_id": prop.proposal_id, "proposal": prop.model_dump(mode="json")})
                    return
                if error:
                    break
    except Exception as ex:
        error = f"{type(ex).__name__}: {ex}"
    sites = _sites.pop(patient.patient_id, None)
    found = "a dispatcher should decide" if sites is None else (
        f"{len(sites)} possible shelter site{'' if len(sites) == 1 else 's'} to call about, none confirmed" if sites
        else "the aerial search found no shelter site outside the dark area either")
    yield TraceEvent(seq=seq, t=round(time.time() - t0, 2), kind="done", agent="refuge", text=error or f"no eligible refuge found; {found}",
                     data={"error": error} | ({"shelter_sites": sites} if sites else {}))


def decide(proposal_id: str, decision: Literal["approve", "reject"], reason: str | None) -> RefugeProposal:
    """Record the dispatcher's decision, then resume the paused agent. Only a pending proposal can be decided."""
    doc = store.get("proposal", proposal_id)
    if doc is None:
        raise KeyError(proposal_id)
    prop = RefugeProposal.model_validate(doc)
    if prop.status != "pending":
        raise ValueError(f"proposal {proposal_id} is already {prop.status}")
    if decision == "reject":
        if not (reason or "").strip():
            raise ValueError("a rejection needs a reason")
        notes = (store.get("memory", "dispatcher") or {"text": MEMORY_HEADER})["text"]
        line = f"- {date.today().isoformat()}: rejected {', '.join(o.name for o in prop.options)}: {reason.strip()}\n"
        store.put("memory", "dispatcher", {"text": notes + line})
        sync_memory()
    prop = prop.model_copy(update={"status": "approved" if decision == "approve" else "rejected", "reason": reason})
    store.put("proposal", proposal_id, prop)
    if store.postgres_url() or _graph is not None:  # in memory, only a thread this process started can resume
        resume = {"type": "approve"} if decision == "approve" else {
            "type": "reject", "message": f"Dispatcher rejected: {reason}. Do not submit another proposal in this conversation; stop."}
        try:
            with _graph_session() as graph:
                for _ in graph.stream(Command(resume={"decisions": [resume]}), {"configurable": {"thread_id": prop.thread_id}},
                                      stream_mode="updates"):
                    pass
        except Exception:  # the decision is already recorded; resuming the agent is best-effort
            pass
    return prop
