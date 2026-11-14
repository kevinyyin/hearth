"""Surveyor deep agent: one building in, one sourced outage profile out, with a live trace.

Plan, three layer subagents in parallel, files as the cache, a conflict follow-up, then write_profile.
Derived numbers (time constants) are computed by code in profile.finalize, never by the model.
"""
import json
import time
from pathlib import Path
from typing import Iterator

from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from hearth import store
from hearth.buildings import tools
from hearth.buildings.profile import FIELDS, LAYERS, default_profile, finalize
from hearth.buildings.trace import to_trace
from hearth.config import a, anthropic_headers
from hearth.contracts import BuildingProfile, Evidence, Sourced, TraceEvent

TIMEOUT_S = 90
_context: dict[str, tuple[str, float, float]] = {}  # building_id -> (address, lat, lon) for the running survey
_written: dict[str, float] = {}  # building_id -> time write_profile last saved it


def _where(building_id: str) -> tuple[str, float, float]:
    return _context.get(building_id, ("", 0.0, 0.0))


# ---- tools the agents call ----
@tool
def costar_record(building_id: str) -> str:
    """The building's CoStar property record (floors, units, year built, construction, type, elevators)."""
    rec = tools.costar_record(building_id)
    return json.dumps(rec) if rec else "Not in CoStar: no record for this building."


@tool
def vexcel_attributes(building_id: str) -> str:
    """Vexcel aerial attributes at the building: roof material, condition, shape, tree cover, capture date."""
    _, lat, lon = _where(building_id)
    attrs, _ = tools.cached(building_id, "vexcel", lambda: tools.vexcel_attributes(lat, lon))
    return json.dumps(attrs) if attrs else "No Vexcel attributes at this point."


@tool
def aerial_look(building_id: str, question: str) -> str:
    """Ask a vision model one question about the building's top-down Vexcel image."""
    _, lat, lon = _where(building_id)
    img = tools.vexcel_image(building_id, lat, lon)
    return f"[{img.name}] {tools.look(img, question)}" if img else "No aerial image for this building."


@tool
def matterport_panoramas(building_id: str) -> str:
    """List the building's Matterport scan panoramas as [{pano_id, label}]. Empty means no scan."""
    panos = tools.matterport_panoramas(building_id)
    return json.dumps([{"pano_id": p["pano_id"], "label": p["label"]} for p in panos]) if panos else "No Matterport scan for this building."


@tool
def scan_look(building_id: str, pano_id: str, question: str) -> str:
    """Ask a vision model one question about one Matterport panorama."""
    pano = next((p for p in tools.matterport_panoramas(building_id) if p["pano_id"] == pano_id), None)
    if pano is None:
        return f"No panorama {pano_id}."
    if pano.get("reading"):  # fixtures carry a written reading instead of an image
        return pano["reading"]
    return tools.look(Path(pano["path"]), question) if pano.get("path") else "No image for this panorama."


@tool
def write_profile(building_id: str, fields_json: str, evidence_json: str, conflicts_json: str, layers_missing_json: str) -> str:
    """Save the building's outage profile. Call once, at the end.

    fields_json: {field: {"value": ..., "source": "costar"|"vexcel"|"matterport", "confidence": 0..1}} for any of:
      floors, units, year_built, construction, property_type, elevator_count, roof_tone, tree_cover_fraction,
      step_free_entrance, entrance_steps, stair_width_m, min_door_width_m, van_dropoff. Leave out fields no layer showed.
    evidence_json: [{"field", "layer", "ref" (image file or pano_id), "note"}].
    conflicts_json: ["plain sentence per disagreement between layers"].
    layers_missing_json: subset of ["costar", "vexcel", "matterport"] that returned nothing.
    """
    try:
        fields = json.loads(fields_json)
        unknown = set(fields) - set(FIELDS)
        if unknown:
            return f"error: unknown fields {sorted(unknown)}; allowed: {FIELDS}"
        sourced = {k: Sourced.model_validate(v) for k, v in fields.items()}
        silent = [k for k, v in sourced.items() if v.source == "default" and v.value is not None]
        if silent:
            return f"error: {silent} have a value but no layer as source; leave them out instead"
        missing = json.loads(layers_missing_json)
        if not set(missing) <= set(LAYERS):
            return f"error: layers_missing must be a subset of {list(LAYERS)}"
        address, lat, lon = _where(building_id)
        profile = default_profile(building_id, address, lat, lon).model_copy(update={
            **sourced, "evidence": [Evidence.model_validate(e) for e in json.loads(evidence_json)],
            "conflicts": [str(c) for c in json.loads(conflicts_json)], "layers_missing": missing})
        profile = finalize(BuildingProfile.model_validate(profile.model_dump()))
    except Exception as e:  # the model gets the reason and can retry
        return f"error: {e}"
    store.put("profile", building_id, profile)
    _written[building_id] = time.time()
    return f"saved profile for {building_id}"


SYSTEM = """You survey one building for a county health department planning for people on home medical devices
during a multi-day power outage. You produce one outage profile. Work in this order:
1. Write a short to-do plan with write_todos.
2. In ONE turn, call the task tool three times to dispatch the costar, aerial and interior subagents in parallel.
   Give each the building id. They save findings to /<building_id>/costar.md, /<building_id>/vexcel.md and
   /<building_id>/matterport.md and return a summary.
3. Compare the layers. List every conflict (for example CoStar lists an elevator but the scan shows none). For each
   conflict, ask the relevant subagent one follow-up question with the task tool.
4. Call write_profile once. Every field needs the layer it came from and a confidence 0..1. Leave out any field no
   layer showed; never fill a field from your own assumptions. When layers disagree, keep the value from the more
   direct evidence, give it confidence 0.5 or less, and record the conflict in plain words. List layers that
   returned nothing in layers_missing. Evidence refs are image file names or panorama ids.
Do not write medical advice or promises of help. Be brief."""

SUBAGENTS = [
    {"name": "costar", "description": "Reads the building's CoStar record.", "tools": [costar_record],
     "system_prompt": "Call costar_record once. Report floors, units, year_built, construction, property_type and "
                      "elevator_count (quote the elevator note), each with a confidence 0..1. If the record lacks a field, say "
                      "'not in record'; never guess. If there is no record, say so. Save your findings with write_file to "
                      "/<building_id>/costar.md, then return a short summary."},
    {"name": "aerial", "description": "Reads Vexcel aerial attributes and the top-down image.", "tools": [vexcel_attributes, aerial_look],
     "system_prompt": "Call vexcel_attributes, then aerial_look at most twice: roof tone (light, medium or dark) and where a "
                      "van can stop near an entrance. Report roof_tone, tree_cover_fraction (the roof tree cover as a 0..1 "
                      "fraction) and van_dropoff (short text), each with a confidence 0..1 and the image file as evidence. "
                      "Save your findings with write_file to /<building_id>/vexcel.md, then return a short summary."},
    {"name": "interior", "description": "Reads the Matterport scan: entrances, steps, doors, stairs, elevators.",
     "tools": [matterport_panoramas, scan_look],
     "system_prompt": "Call matterport_panoramas. If there is no scan, say 'no scan' and stop. Otherwise call scan_look on "
                      "the entrance, lobby and stair panoramas (and any elevator panorama) with one specific question each. "
                      "Report step_free_entrance (true if any entrance is level), entrance_steps, min_door_width_m, "
                      "stair_width_m and elevator_count if elevators are visible (or 'none visible'), each with a confidence "
                      "0..1 and the pano_id as evidence. Scans show common areas only; never describe a resident's unit. "
                      "Save your findings with write_file to /<building_id>/matterport.md, then return a short summary."},
]


def build_surveyor(model=None):
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain_anthropic import ChatAnthropic

    chat = lambda m, effort: ChatAnthropic(model=a(m), default_headers=anthropic_headers(), timeout=60, max_retries=1,
                                           output_config={"effort": a(effort)})
    model = model or chat("models.agent", "models.agent_effort")
    sub = chat("models.subagent", "models.subagent_effort")
    return create_deep_agent(model=model, tools=[write_profile], system_prompt=SYSTEM, middleware=[TodoListMiddleware()],
                             subagents=[s | {"model": sub} for s in SUBAGENTS], backend=FilesystemBackend(root_dir=tools.CACHE_ROOT, virtual_mode=True),
                             checkpointer=InMemorySaver())


def survey(building_id: str, address: str, lat: float, lon: float, use_cache: bool = True) -> Iterator[TraceEvent]:
    """Stream the survey as TraceEvents. The last event is always kind="done" with a profile, even on failure."""
    t0, seq = time.time(), 0
    if use_cache and (hit := store.get("profile", building_id)):
        yield TraceEvent(seq=0, t=0.0, kind="done", agent="surveyor", text="cached profile", data={"profile": hit | {"cached": True}})
        return
    _context[building_id] = (address, lat, lon)
    error = None
    try:
        graph = build_surveyor()
        config = {"configurable": {"thread_id": f"survey-{building_id}-{t0}"}, "recursion_limit": 80}
        msg = {"messages": [{"role": "user", "content": f"Survey building {building_id} at {address} ({lat}, {lon})."}]}
        # shortcut: the timeout is checked between stream chunks, not preemptively; model calls have their own 60 s timeout
        for chunk in graph.stream(msg, config, stream_mode="updates", subgraphs=True):
            for e in to_trace(chunk, seq, t0):
                seq += 1
                yield e
            if time.time() - t0 > TIMEOUT_S:
                error = f"survey timed out after {TIMEOUT_S} s"
                break
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    if _written.get(building_id, 0) >= t0:  # written during this run, even if a later step failed
        profile = store.get("profile", building_id)
    else:
        profile = finalize(default_profile(building_id, address, lat, lon)).model_copy(
            update={"error": error or "the agent finished without writing a profile"}).model_dump(mode="json")
    yield TraceEvent(seq=seq, t=round(time.time() - t0, 2), kind="done", agent="surveyor",
                     text="survey failed; showing defaults" if profile["error"] else "profile written", data={"profile": profile})
