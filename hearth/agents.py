"""Agent runs the dispatch page starts on its own: a building survey for each phone registration whose building has no
agent profile, and a refuge search for each request code could not place because no refuge fits.

Each run is a stored "agent_run" document (kind, building or patient, status, step lines, result), written as its
stream is read, so every dispatch tab shows the same runs and a reload starts nothing new. The page starts only what
`to_start` lists; the server refuses a second start while one is running.
"""
import re
import threading
import time
from typing import Iterator, Literal

from hearth import dispatch, store
from hearth.buildings import tools
from hearth.config import a
from hearth.contracts import HelpRequest, TraceEvent

KIND = "agent_run"
LAYERS = {"costar": "CoStar records", "aerial": "Vexcel aerial", "interior": "Matterport scan"}
DOING = {"costar_record": "reading the record", "vexcel_attributes": "reading the roof and trees", "aerial_detect": "finding parking and entrances",
         "aerial_look": "looking at the aerial", "matterport_rooms": "reading rooms", "matterport_panoramas": "listing panoramas",
         "scan_look": "looking at a panorama"}
# shortcut: one process only, like dispatch._lock; two hosted instances could each start the same run. Use a database lock if that shows.
_lock = threading.Lock()


def request_at(r: HelpRequest | None) -> str | None:
    """Which request a refuge search was for: the time it entered the queue."""
    return str(r.times["waiting"]) if r and "waiting" in r.times else None


def _fresh(run: dict | None) -> dict | None:
    """A running record nobody has written to for `agents.stale_after_s` was cut off (tab closed, function limit)."""
    if run and run["status"] == "running" and time.time() - run["updated_at"] > a("agents.stale_after_s"):
        return run | {"status": "stopped"}
    return run


def runs() -> list[dict]:
    """Every run, with `on_rail` while it runs and for `agents.rail_min` after it ends."""
    out = [r for d in store.all(KIND) if (r := _fresh(d))]
    return [r | {"on_rail": r["status"] == "running" or time.time() - r["updated_at"] < a("agents.rail_min") * 60} for r in out]


def claim(kind: Literal["survey", "refuge"], *, building_id: str | None, patient_id: str | None, address: str | None,
          request_at: str | None = None) -> dict:
    """Stores a new running record; ValueError while one for the same building (survey) or patient (refuge) runs."""
    run_id = f"{kind}-{building_id if kind == 'survey' else patient_id}"
    with _lock:
        if (old := _fresh(store.get(KIND, run_id))) and old["status"] == "running":
            raise ValueError(f"this {'building survey' if kind == 'survey' else 'refuge search'} is already running")
        now = time.time()
        run = {"run_id": run_id, "kind": kind, "building_id": building_id, "patient_id": patient_id, "address": address,
               "request_at": request_at, "status": "running", "started_at": now, "updated_at": now, "steps": [], "result": {}}
        store.put(KIND, run_id, run)
    return run


def _steps(kind: str, events: list[TraceEvent]) -> list[dict]:
    """Step lines with seconds since the run began: t1 is None while the step is live. Survey layers run side by side
    and each ends when its subagent saves its findings; refuge steps run one after another."""
    steps: dict[str, dict] = {}

    def start(key, text, t):
        for s in steps.values():  # a refuge step ends when the next one begins
            if kind == "refuge" and s["t1"] is None:
                s["t1"] = t
        steps[key] = {"text": text, "t0": t, "t1": None}

    for e in events:
        name = e.text.split("(")[0]
        if kind == "survey" and e.kind == "subagent" and e.agent in LAYERS and e.agent not in steps:
            start(e.agent, LAYERS[e.agent], e.t)
        elif kind == "survey" and e.kind == "tool" and e.agent in steps and steps[e.agent]["t1"] is None and name in DOING:
            steps[e.agent]["text"] = f"{LAYERS[e.agent]}, {DOING[name]}"
        elif kind == "survey" and e.kind == "file" and e.agent in steps:
            steps[e.agent] |= {"text": LAYERS[e.agent], "t1": e.t}
        elif kind == "survey" and e.kind == "profile":
            start("profile", "Writing the outage profile", e.t)
        elif kind == "refuge" and e.kind == "tool" and name == "search_refuges":
            start(name, "Hotels and senior housing nearby", e.t)
        elif kind == "refuge" and e.kind == "tool" and name == "check_access" and (m := re.search(r"building_id=([^,)]+)", e.text)):
            rec = tools.costar_record(m[1]) or {}
            start(m[1], f"Access checked: {rec.get('name') or rec.get('address') or m[1]}", e.t)
        elif kind == "refuge" and e.kind == "tool" and name == "search_shelter_sites":
            start(name, "Aerial search for shelter sites", e.t)
        elif e.kind == "interrupt":
            start("proposal", "Proposal sent for approval", e.t)
        if e.kind in ("done", "interrupt"):
            for key, s in steps.items():
                if s["t1"] is None:
                    s |= {"t1": e.t} | ({"text": LAYERS[key]} if key in LAYERS else {})
            if (sites := e.data.get("shelter_sites")) is not None and "search_shelter_sites" in steps:
                steps["search_shelter_sites"]["text"] = f"Aerial search: {len(sites)} shelter lead{'' if len(sites) == 1 else 's'}"
    return list(steps.values())


def track(run: dict, events: Iterator[TraceEvent]) -> Iterator[TraceEvent]:
    """Passes the stream through, storing the run's steps after every event and its status and result at the end. A
    stream closed early (the tab went away) leaves the run "stopped", so the page may start it again."""
    seen: list[TraceEvent] = []
    try:
        for e in events:
            seen.append(e)
            run["steps"], run["updated_at"] = _steps(run["kind"], seen), time.time()
            if e.kind == "interrupt":
                run |= {"status": "done", "result": {"proposal_id": e.data.get("proposal_id")}}
            elif e.kind == "done":
                error = e.data.get("error") or (e.data.get("profile") or {}).get("error")
                run |= {"status": "failed" if error else "done",
                        "result": {"error": error} if error else {"message": e.text} | ({"shelter_sites": e.data["shelter_sites"]} if "shelter_sites" in e.data else {})}
            store.put(KIND, run["run_id"], run)
            yield e
    finally:
        if run["status"] == "running":
            store.put(KIND, run["run_id"], run | {"status": "stopped", "updated_at": time.time()})
    if run["kind"] == "survey" and run["status"] == "done":
        dispatch.place_again(run["patient_id"] or "")  # a newly surveyed hotel can unblock someone


def _rejected(run: dict) -> bool:
    pid = run["result"].get("proposal_id")
    return bool(pid) and (store.get("proposal", pid) or {}).get("status") == "rejected"


def to_start() -> list[dict]:
    """The runs the dispatch page should start now, at most `agents.max_running` at once across every tab."""
    have = {r["run_id"]: r for r in runs()}
    surveyed = {p["building_id"] for p in store.all("profile") if p.get("method", "agent") == "agent" and "building_id" in p}
    want: dict[str, dict] = {}

    def add(kind, building_id, patient_id, run_id):
        old = have.get(run_id)
        want.setdefault(run_id, {"run_id": run_id, "kind": kind, "building_id": building_id, "patient_id": patient_id,
                                 "key": f"{run_id}@{old['started_at'] if old else 0}"})  # a new key each time it may start again

    for h in store.all("home"):
        run_id = f"survey-{h.get('building_id')}"
        if h.get("source") == "phone" and h.get("building_id") and h["building_id"] not in surveyed and have.get(run_id, {"status": "stopped"})["status"] == "stopped":
            add("survey", h["building_id"], h["patient_id"], run_id)
    no_refuge = dispatch.NO_REFUGE.format(km=a("refuge.search_radius_km"))
    for r in dispatch.requests():
        old = have.get(f"refuge-{r.patient_id}")
        if r.state == "waiting" and r.blocked == no_refuge and (
                old is None or old["status"] == "stopped" or (old["status"] != "running" and (old.get("request_at") != request_at(r) or _rejected(old)))):
            add("refuge", None, r.patient_id, f"refuge-{r.patient_id}")
    running = sum(r["status"] == "running" for r in have.values())
    return list(want.values())[: max(0, a("agents.max_running") - running)]
