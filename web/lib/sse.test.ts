import { describe, expect, it } from "vitest";
import { parseSSE, reduceTrace } from "./sse";
import type { TraceEvent } from "./types";

const ev = (seq: number, kind: TraceEvent["kind"], agent: string, text: string, data: Record<string, unknown> = {}): TraceEvent => ({
  seq, t: seq, kind, agent, text, data,
});

const recorded: TraceEvent[] = [
  ev(0, "todo", "surveyor", "plan", { todos: [{ content: "Dispatch layers", status: "in_progress" }, { content: "Write profile", status: "pending" }] }),
  ev(1, "subagent", "costar", "Read the CoStar record"),
  ev(2, "subagent", "aerial", "Read Vexcel"),
  ev(3, "subagent", "interior", "Read the scan"),
  ev(4, "tool", "interior", "scan_look(pano-lobby)"),
  ev(5, "tool", "interior", "saw: no elevator visible"),
  ev(6, "file", "costar", "/B-SAMPLE/costar.md", { path: "/B-SAMPLE/costar.md" }),
  ev(7, "subagent", "interior", "Follow-up: re-check the lobby"),
  ev(8, "todo", "surveyor", "plan", { todos: [{ content: "Dispatch layers", status: "completed" }, { content: "Write profile", status: "in_progress" }] }),
  ev(9, "conflict", "surveyor", "CoStar lists 1 elevator; the scan shows none"),
  ev(10, "done", "surveyor", "profile written", { profile: { building_id: "B-SAMPLE", error: null, cached: false } }),
];

describe("reduceTrace", () => {
  it("keeps the latest to-do statuses, one row per subagent, conflicts, files and the profile", () => {
    const r = reduceTrace(recorded);
    expect(r.todos.map((t) => t.status)).toEqual(["completed", "in_progress"]);
    expect(r.subagents.map((s) => s.name)).toEqual(["costar", "aerial", "interior"]);
    const interior = r.subagents.find((s) => s.name === "interior")!;
    expect(interior.last).toBe("saw: no elevator visible");
    expect(interior.asks).toBe(2);
    expect(r.files).toEqual(["/B-SAMPLE/costar.md"]);
    expect(r.conflicts).toHaveLength(1);
    expect(r.profile?.building_id).toBe("B-SAMPLE");
    expect(r.error).toBeNull();
    expect(r.done).toBe(true);
  });

  it("flags an error from a failed survey or refuge run", () => {
    expect(reduceTrace([ev(0, "done", "surveyor", "failed", { profile: { error: "timed out" } })]).error).toBe("timed out");
    expect(reduceTrace([ev(0, "done", "refuge", "none", { error: "no option passes" })]).error).toBe("no option passes");
  });

  it("captures the proposal at the approval interrupt", () => {
    expect(reduceTrace([ev(0, "interrupt", "dispatcher", "waiting", { proposal_id: "P-1" })]).proposalId).toBe("P-1");
  });
});

describe("parseSSE", () => {
  it("returns complete events and keeps the partial tail", () => {
    const { events, rest } = parseSSE('data: {"seq":0}\n\ndata: {"seq":1}\n\ndata: {"se');
    expect(events.map((e) => (e as { seq: number }).seq)).toEqual([0, 1]);
    expect(rest).toBe('data: {"se');
  });
});
