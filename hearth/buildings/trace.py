"""Map deep-agent stream chunks (stream_mode="updates", subgraphs=True) to TraceEvents for the UI."""
import json
import time

from hearth.contracts import TraceEvent

# subagent chunks carry only a namespace id, so the agent is named from the tool it calls
TOOL_AGENT = {"costar_record": "costar", "vexcel_attributes": "aerial", "aerial_look": "aerial", "aerial_detect": "aerial",
              "matterport_rooms": "interior", "matterport_panoramas": "interior", "scan_look": "interior",
              "search_refuges": "refuge", "check_access": "refuge", "submit_proposal": "refuge"}
LOOK_TOOLS = {"aerial_look", "scan_look", "aerial_detect"}  # their results are shown in the trace
FILE_AGENT = {"costar": "costar", "vexcel": "aerial", "matterport": "interior"}  # /<id>/<layer>.md


def _text(content) -> str:
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


def _msg(m) -> dict:
    if isinstance(m, dict):
        return m
    return {"type": m.type, "name": getattr(m, "name", None), "content": _text(m.content),
            "tool_calls": [{"name": c["name"], "args": c["args"]} for c in getattr(m, "tool_calls", None) or []]}


def plain(chunk) -> list:
    """A JSON-able copy of one chunk: [namespace, {node: {messages, todos, files, interrupt}}]. Idempotent."""
    ns, update = chunk
    out = {}
    for node, val in (update or {}).items():
        if node == "__interrupt__":
            out[node] = json.loads(json.dumps([getattr(i, "value", i) for i in val], default=str))
            continue
        if not isinstance(val, dict):
            continue
        d = {}
        msgs = val.get("messages")
        msgs = getattr(msgs, "value", msgs)  # messages may arrive wrapped in Overwrite
        if msgs:
            d["messages"] = [_msg(m) for m in msgs]
        if val.get("todos"):
            d["todos"] = [{"content": t["content"], "status": t["status"]} for t in val["todos"]]
        if val.get("files"):
            d["files"] = sorted(val["files"])
        out[node] = d
    return [list(ns), out]


def _loads(s, default):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def to_trace(chunk, seq: int, t0: float, root: str = "surveyor") -> list[TraceEvent]:
    ns, update = plain(chunk)
    t = round(time.time() - t0, 2)
    events: list[TraceEvent] = []

    def emit(kind, agent, text, data=None):
        events.append(TraceEvent(seq=seq + len(events), t=t, kind=kind, agent=agent, text=text, data=data or {}))

    for node, d in update.items():
        if node == "__interrupt__":
            emit("interrupt", "dispatcher", "waiting for dispatcher approval", {"requests": d})
            continue
        if d.get("todos"):
            emit("todo", root if not ns else "subagent",
                 "; ".join(f"[{t['status']}] {t['content']}" for t in d["todos"]), {"todos": d["todos"]})
        for m in d.get("messages", []):
            for call in m.get("tool_calls", []):
                name, a = call["name"], call["args"]
                who = TOOL_AGENT.get(name, root if not ns else "subagent")
                if name == "task":
                    emit("subagent", a.get("subagent_type", "subagent"), str(a.get("description", ""))[:300])
                elif name in ("write_file", "edit_file"):
                    path = str(a.get("file_path", ""))
                    emit("file", FILE_AGENT.get(path.rsplit("/", 1)[-1].split(".")[0], who), path, {"path": path})
                elif name == "write_profile":
                    for c in _loads(a.get("conflicts_json"), []):
                        emit("conflict", "surveyor", str(c))
                    emit("profile", "surveyor", "writing the outage profile")
                elif name != "write_todos":
                    emit("tool", who, f"{name}({', '.join(f'{k}={v}' for k, v in a.items())})"[:300])
            if m.get("type") == "tool" and m.get("name") in LOOK_TOOLS:
                emit("tool", TOOL_AGENT[m["name"]], f"saw: {m['content']}"[:400])
    return events
